"""
Celery task consumed by the worker. This is the "ORCHESTRATOR" stage:

  1. Fetch Code Diff        -> github_client.fetch_pr_diff
  2. Load Repo Patterns     -> query RepoPattern table (past learnings)
  3. LangGraph Review       -> graph.run_review_graph (parallel agents -> merge -> dedupe)
  4. Save Findings          -> persist ReviewFinding rows
  5. Hand off to Reviewer   -> POST to reviewer_service to post GitHub comments
"""
import asyncio
import logging

import httpx
from sqlalchemy import select

from shared.celery_app import celery_app
from shared.config import get_settings
from shared.database import session_scope
from shared.models import PullRequest, ReviewFinding, RepoPattern, PRStatus, AgentType, Severity
from shared.schemas import ReviewJob, PostCommentsRequest, FindingOut
from orchestrator_service.github_client import fetch_pr_diff
from orchestrator_service.graph import run_review_graph

logging.basicConfig(level="INFO")
logger = logging.getLogger("orchestrator_service.tasks")
settings = get_settings()


async def _load_repo_patterns(repo_full_name: str) -> list[dict]:
    async with session_scope() as db:
        result = await db.execute(
            select(RepoPattern).where(RepoPattern.repo_full_name == repo_full_name)
        )
        rows = result.scalars().all()
        return [
            {"pattern_key": r.pattern_key, "pattern_value": r.pattern_value, "frequency": r.frequency}
            for r in rows
        ]


async def _save_findings(pull_request_id: str, merged_findings: list[dict]) -> None:
    async with session_scope() as db:
        for f in merged_findings:
            db.add(ReviewFinding(
                pull_request_id=pull_request_id,
                agent=AgentType(f["agent"]),
                severity=Severity(f["severity"]),
                file_path=f.get("file_path"),
                line_number=f.get("line_number"),
                title=f.get("title", "")[:255],
                message=f.get("message", ""),
                suggestion=f.get("suggestion"),
                content_hash=f["content_hash"],
            ))

        result = await db.execute(select(PullRequest).where(PullRequest.id == pull_request_id))
        pr_row = result.scalar_one_or_none()
        if pr_row:
            pr_row.status = PRStatus.REVIEWED


async def _dispatch_to_reviewer(job: ReviewJob, merged_findings: list[dict], summary: str) -> None:
    payload = PostCommentsRequest(
        repo_full_name=job.repo_full_name,
        pr_number=job.pr_number,
        head_sha=job.head_sha,
        installation_id=job.installation_id,
        findings=[
            FindingOut(
                agent=f["agent"], severity=f["severity"], file_path=f.get("file_path"),
                line_number=f.get("line_number"), title=f.get("title", ""),
                message=f.get("message", ""), suggestion=f.get("suggestion"),
            ) for f in merged_findings
        ],
        summary=summary,
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.reviewer_service_url.strip()}/reviewer/post-comments",
                json=payload.model_dump(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to dispatch findings to reviewer_service: %s", exc)


async def _run_review_pipeline(job_dict: dict) -> None:
    try:
        job = ReviewJob(**job_dict)
        print(f"Starting review for {job.repo_full_name}#{job.pr_number} @ {job.head_sha[:8]}", flush=True)
    
        async with session_scope() as db:
            result = await db.execute(select(PullRequest).where(PullRequest.id == job.pull_request_id))
            pr_row = result.scalar_one_or_none()
            if pr_row:
                pr_row.status = PRStatus.REVIEWING
    
        # 1. Fetch Code Diff
        print("Fetching code diff from GitHub...", flush=True)
        diff = await fetch_pr_diff(job.repo_full_name, job.pr_number, job.installation_id)
        print(f"Diff fetched successfully. Length: {len(diff)} chars.", flush=True)
    
        # 2. Load Repo Patterns
        print("Loading repo patterns...", flush=True)
        repo_patterns = await _load_repo_patterns(job.repo_full_name)
    
        # 3. LangGraph Review (parallel agents -> merge -> dedupe)
        print("Running LangGraph agent pipeline...", flush=True)
        final_state = await run_review_graph(job.repo_full_name, job.pr_number, diff, repo_patterns)
        merged_findings = final_state.get("merged_findings", [])
        summary = final_state.get("summary", "")
        print(f"LangGraph execution finished. Found {len(merged_findings)} review items.", flush=True)
    
        # 4. Save Findings
        print("Saving findings to database...", flush=True)
        await _save_findings(job.pull_request_id, merged_findings)
    
        # 5. Hand off to Reviewer Service to post comments to GitHub
        print(f"Dispatching review findings to reviewer_service: {settings.reviewer_service_url}", flush=True)
        await _dispatch_to_reviewer(job, merged_findings, summary)
    
        print(f"Completed review for {job.repo_full_name}#{job.pr_number}: {len(merged_findings)} findings", flush=True)
    except Exception as exc:
        import traceback
        print("FATAL error in background review pipeline:", flush=True)
        traceback.print_exc()


@celery_app.task(name="orchestrator_service.tasks.run_review", bind=True, max_retries=2, default_retry_delay=30)
def run_review(self, job_dict: dict):
    """Synchronous Celery entrypoint that drives the async pipeline."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            logger.info("Existing event loop detected. Scheduling review pipeline task.")
            loop.create_task(_run_review_pipeline(job_dict))
        else:
            logger.info("No running event loop. Running review pipeline synchronously.")
            asyncio.run(_run_review_pipeline(job_dict))
    except Exception as exc:
        logger.exception("Review pipeline failed for job %s", job_dict)
        raise self.retry(exc=exc)

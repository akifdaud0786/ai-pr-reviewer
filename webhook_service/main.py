"""
Webhook Service
---------------
Receives already-HMAC-verified GitHub `pull_request` events from the Gateway
Service and performs the "WEBHOOK PROCESSING" stage of the pipeline:

  1. Parse PR (number / repo / SHA)                -> parser.parse_pr_event
  2. Deduplicate against existing head SHA          -> `_is_duplicate`
  3. Store PR metadata in Postgres                  -> PullRequest row
  4. Push a ReviewJob onto the Redis/Celery queue    -> orchestrator_service.tasks.run_review

Also handles the "closed & merged" action by notifying the Learner Service
(fire-and-forget) instead of enqueueing a review.
"""
import logging

import httpx
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import select
from prometheus_fastapi_instrumentator import Instrumentator

from shared.config import get_settings
from shared.database import get_db, init_models, session_scope
from shared.models import PullRequest, PRStatus
from shared.schemas import ReviewJob, LearnRequest
from shared.celery_app import celery_app
from webhook_service.parser import parse_pr_event

logging.basicConfig(level="INFO")
logger = logging.getLogger("webhook_service")

settings = get_settings()
app = FastAPI(title="Webhook Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)


@app.on_event("startup")
async def on_startup():
    await init_models()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "webhook_service"}


async def _is_duplicate(repo_full_name: str, pr_number: int, head_sha: str) -> bool:
    """Deduplicate: skip if we've already recorded this exact (repo, PR, SHA)."""
    async with session_scope() as db:
        result = await db.execute(
            select(PullRequest).where(
                PullRequest.repo_full_name == repo_full_name,
                PullRequest.pr_number == pr_number,
                PullRequest.head_sha == head_sha,
            )
        )
        return result.scalar_one_or_none() is not None


@app.post("/webhook/ingest")
async def ingest_event(request: Request):
    raw_payload = await request.json()
    event = parse_pr_event(raw_payload)

    if not event.repo_full_name or not event.head_sha:
        raise HTTPException(status_code=400, detail="Malformed PR payload")

    # --- Handle merge -> hand off to Learner, skip review pipeline ---
    if event.action == "closed" and event.merged:
        logger.info("PR #%s in %s merged. Notifying learner_service.", event.number, event.repo_full_name)
        async with session_scope() as db:
            result = await db.execute(
                select(PullRequest).where(
                    PullRequest.repo_full_name == event.repo_full_name,
                    PullRequest.pr_number == event.number,
                )
            )
            pr_row = result.scalars().first()
            if pr_row:
                pr_row.status = PRStatus.MERGED

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{settings.learner_service_url}/learn/from-merge",
                    json=LearnRequest(
                        repo_full_name=event.repo_full_name,
                        pr_number=event.number,
                        installation_id=event.installation_id,
                    ).model_dump(),
                )
            except httpx.HTTPError as exc:
                logger.warning("Could not reach learner_service: %s", exc)

        return {"status": "merge_processed"}

    # Only trigger reviews on PR opened / synchronize (new commits pushed) / reopened
    if event.action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored_action", "action": event.action}

    # --- Deduplicate ---
    if await _is_duplicate(event.repo_full_name, event.number, event.head_sha):
        logger.info("Duplicate event for %s#%s @ %s -- skipping.", event.repo_full_name, event.number, event.head_sha)
        return {"status": "duplicate_skipped"}

    # --- Store PR metadata ---
    async with session_scope() as db:
        pr_row = PullRequest(
            repo_full_name=event.repo_full_name,
            pr_number=event.number,
            head_sha=event.head_sha,
            base_branch=event.base_branch,
            head_branch=event.head_branch,
            title=event.pr_title,
            author=event.author,
            installation_id=event.installation_id,
            diff_url=event.diff_url,
            status=PRStatus.QUEUED,
        )
        db.add(pr_row)
        await db.flush()
        pr_id = pr_row.id

    # --- Push to Redis Queue (Celery) ---
    job = ReviewJob(
        pull_request_id=pr_id,
        repo_full_name=event.repo_full_name,
        pr_number=event.number,
        head_sha=event.head_sha,
        installation_id=event.installation_id,
        diff_url=event.diff_url,
    )
    from orchestrator_service.tasks import run_review
    run_review.delay(job.model_dump())
    logger.info("Executed review job eagerly for %s#%s", event.repo_full_name, event.number)

    return {"status": "queued", "pull_request_id": pr_id}

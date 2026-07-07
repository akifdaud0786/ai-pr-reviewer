"""
Extract Frequent Issues + Store Repo Patterns
----------------------------------------------
Once a PR is merged, this looks at the (already-saved) ReviewFinding rows for
that PR and rolls them up into durable RepoPattern rows -- e.g. "this repo
frequently gets flagged for missing null checks" or "this repo prefers
snake_case even in TS files". These patterns are then loaded by the
Orchestrator's "Load Repo Patterns" step for every future review, closing
the self-improvement loop described in the architecture diagram.
"""
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.database import session_scope
from shared.models import PullRequest, ReviewFinding, RepoPattern

logger = logging.getLogger("learner_service.extract_patterns")


async def extract_and_store_patterns(repo_full_name: str, pr_number: int) -> dict:
    async with session_scope() as db:
        pr_result = await db.execute(
            select(PullRequest).where(
                PullRequest.repo_full_name == repo_full_name,
                PullRequest.pr_number == pr_number,
            )
        )
        pr_row = pr_result.scalars().first()
        if not pr_row:
            logger.warning("No PullRequest row found for %s#%s -- nothing to learn from", repo_full_name, pr_number)
            return {"patterns_updated": 0}

        findings_result = await db.execute(
            select(ReviewFinding).where(ReviewFinding.pull_request_id == pr_row.id)
        )
        findings = findings_result.scalars().all()

        if not findings:
            return {"patterns_updated": 0}

        # Roll up frequent issue titles per agent -- this is our "learned pattern" signal
        issue_counter = Counter((f.agent.value, f.title.strip().lower()) for f in findings)

        patterns_updated = 0
        for (agent, title), count in issue_counter.items():
            pattern_key = f"frequent_issue:{agent}:{title}"[:255]
            existing = await db.execute(
                select(RepoPattern).where(
                    RepoPattern.repo_full_name == repo_full_name,
                    RepoPattern.pattern_key == pattern_key,
                )
            )
            existing_row = existing.scalars().first()

            if existing_row:
                existing_row.frequency += count
                existing_row.last_seen_pr = pr_number
                existing_row.pattern_value = {"agent": agent, "title": title, "example_pr": pr_number}
            else:
                db.add(RepoPattern(
                    repo_full_name=repo_full_name,
                    pattern_key=pattern_key,
                    pattern_value={"agent": agent, "title": title, "example_pr": pr_number},
                    frequency=count,
                    last_seen_pr=pr_number,
                ))
            patterns_updated += 1

        logger.info("Updated %d repo pattern(s) for %s from PR #%s", patterns_updated, repo_full_name, pr_number)
        return {"patterns_updated": patterns_updated}

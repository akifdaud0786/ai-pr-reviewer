"""
Reviewer Service
----------------
Receives the merged/deduplicated findings from the Orchestrator and posts
them back to the GitHub PR as inline comments + an overall summary review,
using GitHub App installation-token auth.
"""
import logging

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from shared.schemas import PostCommentsRequest
from reviewer_service.comment_poster import post_review

logging.basicConfig(level="INFO")
logger = logging.getLogger("reviewer_service")

app = FastAPI(title="Reviewer Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "reviewer_service"}


@app.post("/reviewer/post-comments")
async def post_comments(payload: PostCommentsRequest):
    try:
        result = await post_review(payload)
    except Exception as exc:
        logger.exception("Failed to post review to GitHub")
        raise HTTPException(status_code=502, detail=f"Failed to post review: {exc}")

    return {
        "status": "posted",
        "repo_full_name": payload.repo_full_name,
        "pr_number": payload.pr_number,
        "review_id": result.get("id"),
        "findings_count": len(payload.findings),
    }

"""
Learner Service
---------------
Triggered by webhook_service whenever a PR is merged. Extracts frequent
issues from that PR's findings and rolls them into per-repo learned patterns,
which future Orchestrator runs load to make reviews smarter over time.
"""
import logging

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from shared.database import init_models
from shared.schemas import LearnRequest
from learner_service.extract_patterns import extract_and_store_patterns

logging.basicConfig(level="INFO")
logger = logging.getLogger("learner_service")

app = FastAPI(title="Learner Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)


@app.on_event("startup")
async def on_startup():
    await init_models()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "learner_service"}


@app.post("/learn/from-merge")
async def learn_from_merge(payload: LearnRequest):
    result = await extract_and_store_patterns(payload.repo_full_name, payload.pr_number)
    return {"status": "learned", **result}

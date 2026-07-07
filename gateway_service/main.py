"""
Gateway Service
---------------
Public-facing FastAPI app that GitHub's webhook actually points at.

Responsibilities (per the architecture diagram's "GATEWAY" stage):
  1. Receive the raw webhook POST from GitHub.
  2. Verify the HMAC-SHA256 signature (`Verify HMAC`).
  3. Reject anything that doesn't verify (`Reject Fakes`).
  4. Forward the verified, parsed event to the Webhook Service (`Forward Event`).

This service intentionally does almost nothing else — it exists purely as a
thin, fast, well-hardened front door so the rest of the system never has to
worry about verifying trust again.
"""
import logging

import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from prometheus_fastapi_instrumentator import Instrumentator

from shared.config import get_settings
from gateway_service.hmac_verify import verify_signature

logging.basicConfig(level="INFO")
logger = logging.getLogger("gateway_service")

settings = get_settings()
app = FastAPI(title="Gateway Service", version="1.0.0")
Instrumentator().instrument(app).expose(app)  # /metrics for Prometheus

# Where verified events get forwarded
WEBHOOK_SERVICE_INGEST_URL = f"{settings.gateway_internal_url}/webhook/ingest"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway_service"}


@app.post("/webhook/github")
async def receive_github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=None),
    x_github_event: str = Header(default=None),
    x_github_delivery: str = Header(default=None),
):
    raw_body = await request.body()

    # --- Verify HMAC ---
    if not verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret):
        logger.warning("Rejected webhook delivery %s: invalid signature", x_github_delivery)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Only forward pull_request events; ack everything else quietly (GitHub
    # sends many event types, e.g. ping, issues, star -- we only care about PRs)
    if x_github_event != "pull_request":
        logger.info("Ignoring non-PR event: %s", x_github_event)
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()

    # --- Forward Event to Webhook Service ---
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                WEBHOOK_SERVICE_INGEST_URL,
                json=payload,
                headers={"X-GitHub-Delivery": x_github_delivery or ""},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to forward event to webhook_service: %s", exc)
            raise HTTPException(status_code=502, detail="Downstream webhook_service unavailable")

    return {"status": "forwarded", "delivery": x_github_delivery}

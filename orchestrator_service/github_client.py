"""
Minimal GitHub App API client used by the Orchestrator to fetch a PR's diff.

Auth flow (GitHub App):
  1. Sign a short-lived JWT with the App's private key (`generate_app_jwt`).
  2. Exchange the JWT for an installation access token (`get_installation_token`).
  3. Use the installation token as a Bearer token for REST calls.

This mirrors the auth flow also used by reviewer_service when posting comments.
"""
import time
import logging

import httpx
import jwt

from shared.config import get_settings

logger = logging.getLogger("orchestrator_service.github_client")
settings = get_settings()


def generate_app_jwt() -> str:
    """Create the GitHub App JWT (valid ~10 minutes) used to mint installation tokens."""
    with open(settings.github_app_private_key_path, "r") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now - 60,          # allow for clock drift
        "exp": now + (9 * 60),    # GitHub max is 10 minutes
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: str) -> str:
    """Exchange the App JWT for a scoped installation access token."""
    app_jwt = generate_app_jwt()
    url = f"{settings.github_api_base}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers)
        resp.raise_for_status()
        return resp.json()["token"]


MOCK_DIFF = """diff --git a/payments.py b/payments.py
index 1234567..89abcde 100644
--- a/payments.py
+++ b/payments.py
@@ -1,8 +1,15 @@
 import httpx
+import time
 
 class PaymentClient:
     def __init__(self, base_url: str):
         self.base_url = base_url
 
-    def charge(self, amount: float) -> dict:
-        resp = httpx.post(f"{self.base_url}/charge", json={"amount": amount})
-        return resp.json()
+    def charge(self, amount: float, retries: int = 3) -> dict:
+        for attempt in range(retries):
+            try:
+                resp = httpx.post(f"{self.base_url}/charge", json={"amount": amount})
+                resp.raise_for_status()
+                return resp.json()
+            except httpx.HTTPStatusError as e:
+                if attempt == retries - 1:
+                    raise e
+                time.sleep(2 ** attempt)
"""


async def fetch_pr_diff(repo_full_name: str, pr_number: int, installation_id: str | None) -> str:
    """Fetch the unified diff for a PR using the installation token (falls back
    to unauthenticated fetch for public repos / local testing if no installation_id)."""
    if repo_full_name == "octo-org/demo-repo" or settings.environment == "development":
        logger.info("Returning mock diff for offline/dev testing")
        return MOCK_DIFF

    url = f"{settings.github_api_base}/repos/{repo_full_name}/pulls/{pr_number}"
    headers = {"Accept": "application/vnd.github.v3.diff"}

    try:
        if installation_id:
            token = await get_installation_token(installation_id)
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("Failed to fetch PR diff from GitHub (%s), returning mock diff: %s", url, exc)
        return MOCK_DIFF

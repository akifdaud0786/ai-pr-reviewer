"""
GitHub App authentication for the Reviewer Service.
Same JWT -> installation-token flow as orchestrator_service.github_client,
duplicated here (intentionally) so this service has no dependency on the
orchestrator package -- each microservice stays independently deployable.
"""
import time

import httpx
import jwt

from shared.config import get_settings

settings = get_settings()


def generate_app_jwt() -> str:
    private_key = settings.github_app_private_key
    if not private_key and settings.github_app_private_key_path:
        with open(settings.github_app_private_key_path, "r") as f:
            private_key = f.read()
            
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + (9 * 60), "iss": settings.github_app_id}
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: str) -> str:
    app_jwt = generate_app_jwt()
    url = f"{settings.github_api_base}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers)
        resp.raise_for_status()
        return resp.json()["token"]

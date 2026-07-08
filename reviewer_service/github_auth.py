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


def sanitize_pem_key(key_str: str) -> str:
    if not key_str:
        return ""
    key_str = key_str.replace("\\n", "\n").replace("\\r", "\n")
    key_str = key_str.strip().replace('"', '').replace("'", '')
    if not key_str:
        return ""
    if "\n" in key_str and "-----BEGIN" in key_str:
        lines = [line.strip() for line in key_str.split("\n") if line.strip()]
        return "\n".join(lines)
    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"
    if "-----BEGIN PRIVATE KEY-----" in key_str:
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
    body = key_str.replace(header, "").replace(footer, "").strip().replace(" ", "").replace("\n", "").replace("\r", "")
    lines = [body[i:i+64] for i in range(0, len(body), 64)]
    return f"{header}\n" + "\n".join(lines) + f"\n{footer}"


def generate_app_jwt() -> str:
    private_key = sanitize_pem_key(settings.github_app_private_key)
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

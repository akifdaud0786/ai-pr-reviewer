"""
Builds and posts a GitHub "Review" (inline comments + overall summary) using
the Pull Request Reviews API:
  POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews

Each finding becomes one inline `comments[]` entry anchored to a file/line;
findings without a resolvable file/line are folded into the summary body
instead (GitHub requires inline comments to reference a valid diff position).
"""
import logging

import httpx

from shared.config import get_settings
from shared.schemas import PostCommentsRequest
from reviewer_service.github_auth import get_installation_token

logger = logging.getLogger("reviewer_service.comment_poster")
settings = get_settings()

SEVERITY_EMOJI = {
    "critical": "🛑",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "info": "🔵",
}


def _format_inline_body(finding) -> str:
    emoji = SEVERITY_EMOJI.get(finding.severity, "🔵")
    agent_label = finding.agent.replace("_", " ").title()
    body = f"{emoji} **[{agent_label} · {finding.severity.upper()}] {finding.title}**\n\n{finding.message}"
    if finding.suggestion:
        body += f"\n\n💡 **Suggestion:** {finding.suggestion}"
    return body


async def post_review(payload: PostCommentsRequest) -> dict:
    owner, repo = payload.repo_full_name.split("/", 1)
    url = f"{settings.github_api_base}/repos/{owner}/{repo}/pulls/{payload.pr_number}/reviews"

    headers = {"Accept": "application/vnd.github+json"}
    if payload.installation_id:
        token = await get_installation_token(payload.installation_id)
        headers["Authorization"] = f"Bearer {token}"

    inline_comments = []
    unanchored_notes = []

    for finding in payload.findings:
        if finding.file_path and finding.line_number:
            inline_comments.append({
                "path": finding.file_path,
                "line": finding.line_number,
                "side": "RIGHT",
                "body": _format_inline_body(finding),
            })
        else:
            unanchored_notes.append(_format_inline_body(finding))

    summary_body = payload.summary
    if unanchored_notes:
        summary_body += "\n\n---\n**Additional findings (no specific line):**\n\n" + "\n\n".join(unanchored_notes)

    # Determine review "event": REQUEST_CHANGES if any high/critical severity found, else COMMENT
    severities = {f.severity for f in payload.findings}
    event = "REQUEST_CHANGES" if severities & {"high", "critical"} else "COMMENT"

    review_payload = {
        "commit_id": payload.head_sha,
        "body": summary_body,
        "event": event,
        "comments": inline_comments,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=review_payload)
        if resp.status_code >= 400:
            logger.error("GitHub review post failed (%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()

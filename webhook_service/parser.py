"""
Parses a raw GitHub `pull_request` webhook payload into our internal
GitHubPREventPayload shape. GitHub's payload is large and deeply nested;
we only pull out what the pipeline needs.
"""
from shared.schemas import GitHubPREventPayload


def parse_pr_event(raw_payload: dict) -> GitHubPREventPayload:
    pr = raw_payload.get("pull_request", {})
    repo = raw_payload.get("repository", {})
    installation = raw_payload.get("installation", {})

    return GitHubPREventPayload(
        action=raw_payload.get("action", "unknown"),
        number=raw_payload.get("number") or pr.get("number"),
        repo_full_name=repo.get("full_name", ""),
        pr_title=pr.get("title"),
        author=(pr.get("user") or {}).get("login"),
        head_sha=(pr.get("head") or {}).get("sha", ""),
        base_branch=(pr.get("base") or {}).get("ref"),
        head_branch=(pr.get("head") or {}).get("ref"),
        diff_url=pr.get("diff_url"),
        installation_id=str(installation.get("id")) if installation.get("id") else None,
        merged=bool(pr.get("merged", False)),
    )

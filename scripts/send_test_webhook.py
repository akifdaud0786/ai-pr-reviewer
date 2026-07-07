"""
Dev helper: sends a fake but properly-HMAC-signed `pull_request` webhook
event to the local Gateway Service, so you can test the full pipeline
without a real GitHub App / live repo.

Usage:
    python scripts/send_test_webhook.py
    python scripts/send_test_webhook.py --action closed --merged
"""
import argparse
import hashlib
import hmac
import json
import os
import time

import httpx

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/webhook/github")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "changeme-webhook-secret")


def build_payload(action: str, merged: bool) -> dict:
    sha = hashlib.sha1(str(time.time()).encode()).hexdigest()
    return {
        "action": action,
        "number": 42,
        "pull_request": {
            "number": 42,
            "title": "Add async retry logic to payment client",
            "user": {"login": "octodev"},
            "head": {"sha": sha, "ref": "feature/retry-logic"},
            "base": {"ref": "main"},
            "diff_url": "https://github.com/octo-org/demo-repo/pull/42.diff",
            "merged": merged,
        },
        "repository": {"full_name": "octo-org/demo-repo"},
        "installation": {"id": 987654},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", default="opened", choices=["opened", "synchronize", "reopened", "closed"])
    parser.add_argument("--merged", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args.action, args.merged)
    body = json.dumps(payload).encode("utf-8")

    signature = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "test-delivery-id",
    }

    resp = httpx.post(GATEWAY_URL, content=body, headers=headers, timeout=15.0)
    print(f"Status: {resp.status_code}")
    print(resp.text)


if __name__ == "__main__":
    main()

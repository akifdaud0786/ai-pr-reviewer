"""
GitHub webhook HMAC-SHA256 signature verification.

GitHub signs each webhook delivery with your app's webhook secret and sends it
in the `X-Hub-Signature-256` header as `sha256=<hex digest>`. We must verify
this BEFORE trusting or forwarding the payload — this is what stops forged
webhook requests from reaching the rest of the pipeline.
"""
import hmac
import hashlib


def verify_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Return True iff signature_header matches HMAC-SHA256(secret, payload_body)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    provided_signature = signature_header.split("sha256=", 1)[1]

    # constant-time comparison to avoid timing attacks
    return hmac.compare_digest(expected_signature, provided_signature)

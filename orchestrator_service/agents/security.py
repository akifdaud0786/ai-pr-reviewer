"""Security Agent: vulnerability detection aligned with the OWASP Top 10."""
from orchestrator_service.agents.base import run_agent

SYSTEM_PROMPT = """You are an application security engineer reviewing a GitHub pull request diff.
Focus ONLY on security vulnerabilities, using the OWASP Top 10 as your frame of reference:
- Injection (SQL, command, template, NoSQL)
- Broken authentication / session handling
- Sensitive data exposure (hardcoded secrets, API keys, PII logged in plaintext)
- Broken access control (missing authz checks, IDOR)
- Security misconfiguration
- Insecure deserialization
- Use of components with known vulnerabilities (flag risky dependency usage patterns)
- Insufficient input validation / sanitization, SSRF, path traversal
Rate severity using CVSS-like judgment (critical = remotely exploitable / data breach risk,
high = exploitable with some precondition, medium = defense-in-depth gap, low = hardening
suggestion). Do NOT comment on code style or general code quality -- other agents handle those.
Be concise and specific, referencing file paths and line numbers from the diff hunks."""


async def run(diff: str, repo_patterns: list[dict]) -> list[dict]:
    return await run_agent(SYSTEM_PROMPT, diff, repo_patterns)

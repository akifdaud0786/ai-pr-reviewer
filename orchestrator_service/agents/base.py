"""
Shared helpers for all four review agents. Each agent module exports a single
async `run(diff: str, repo_patterns: list[dict]) -> list[dict]` function that
returns findings in the common shape:

    {
        "title": str,
        "message": str,
        "severity": "info" | "low" | "medium" | "high" | "critical",
        "file_path": str | None,
        "line_number": int | None,
        "suggestion": str | None,
    }
"""
from orchestrator_service.llm import call_agent_llm

# Cap diff size sent to the LLM to keep prompts within context limits and cost sane.
MAX_DIFF_CHARS = 24000


def truncate_diff(diff: str) -> str:
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    return diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated for length] ..."


def format_repo_patterns(repo_patterns: list[dict]) -> str:
    """Renders learned repo patterns (from the Learner service) into a short
    context block injected into every agent's prompt, so reviews get smarter
    and more repo-specific over time."""
    if not repo_patterns:
        return "No repo-specific patterns learned yet."
    lines = []
    for p in repo_patterns[:15]:
        lines.append(f"- {p.get('pattern_key')}: {p.get('pattern_value')} (seen {p.get('frequency', 1)}x)")
    return "\n".join(lines)


async def run_agent(system_prompt: str, diff: str, repo_patterns: list[dict]) -> list[dict]:
    user_prompt = (
        f"Here is the unified diff of the pull request to review:\n\n"
        f"```diff\n{truncate_diff(diff)}\n```\n\n"
        f"Learned patterns for this repository (apply if relevant):\n"
        f"{format_repo_patterns(repo_patterns)}\n\n"
        f"Respond ONLY with a JSON object: "
        f'{{"findings": [{{"title": str, "message": str, "severity": '
        f'"info|low|medium|high|critical", "file_path": str or null, '
        f'"line_number": int or null, "suggestion": str or null}}]}}. '
        f"If there are no issues, return an empty findings list."
    )
    return await call_agent_llm(system_prompt, user_prompt)

"""
Merge Findings + Remove Duplicates
----------------------------------
Combines the four agents' raw findings into one deduplicated list, and builds
a short human-readable PR summary.
"""
import hashlib
from collections import Counter


def _content_hash(agent: str, finding: dict) -> str:
    """Fingerprint a finding so identical/near-identical findings from
    different agents (or a re-run) collapse into one."""
    key = "|".join([
        agent,
        (finding.get("file_path") or "").strip().lower(),
        str(finding.get("line_number") or ""),
        (finding.get("title") or "").strip().lower(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def merge_and_dedupe(agent_results: dict[str, list[dict]]) -> list[dict]:
    """
    agent_results: { "static_analysis": [...], "security": [...], "style": [...], "architecture": [...] }
    Returns a flat, deduplicated list of findings, each tagged with its source agent
    and a content_hash, sorted by severity (most severe first).
    """
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    seen_hashes = set()
    merged: list[dict] = []

    for agent, findings in agent_results.items():
        for f in findings:
            f = dict(f)  # copy
            f["agent"] = agent
            f["severity"] = (f.get("severity") or "info").lower()
            if f["severity"] not in severity_rank:
                f["severity"] = "info"
            f["content_hash"] = _content_hash(agent, f)

            if f["content_hash"] in seen_hashes:
                continue  # duplicate finding -- drop it
            seen_hashes.add(f["content_hash"])
            merged.append(f)

    merged.sort(key=lambda f: severity_rank.get(f["severity"], 4))
    return merged


def build_summary(merged_findings: list[dict], repo_full_name: str, pr_number: int) -> str:
    if not merged_findings:
        return (
            f"✅ **AI Review Summary for {repo_full_name}#{pr_number}**\n\n"
            "No issues found by the Static Analysis, Security, Style, or Architecture agents. "
            "This PR looks good to merge from an automated-review standpoint."
        )

    by_severity = Counter(f["severity"] for f in merged_findings)
    by_agent = Counter(f["agent"] for f in merged_findings)

    lines = [
        f"🤖 **AI Review Summary for {repo_full_name}#{pr_number}**",
        "",
        f"Found **{len(merged_findings)}** finding(s) across "
        f"{len(by_agent)} agent(s):",
        "",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        if by_severity.get(sev):
            lines.append(f"- **{sev.upper()}**: {by_severity[sev]}")

    lines.append("")
    lines.append("By agent: " + ", ".join(f"{a.replace('_', ' ').title()} ({c})" for a, c in by_agent.items()))
    lines.append("")
    lines.append("See inline comments for details on each finding.")
    return "\n".join(lines)

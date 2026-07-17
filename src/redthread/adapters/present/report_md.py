"""Render a markdown report from a list of curated handoffs."""

from redthread.models import Handoff


def render_report(handoffs: list[Handoff], run_id: str) -> str:
    lines = [f"# Run report — {run_id}", ""]
    if not handoffs:
        lines.append("_No upstream phases have published a handoff yet._")
        return "\n".join(lines) + "\n"

    for handoff in handoffs:
        lines.append(f"## {handoff.from_phase}")
        lines.append("")
        lines.append(handoff.headline)
        lines.append("")
        if handoff.key_results:
            lines.append("| Metric | Value |")
            lines.append("|---|---|")
            for key, value in handoff.key_results.items():
                lines.append(f"| {key} | {value} |")
            lines.append("")
        if handoff.decisions:
            lines.append("**Decisions:**")
            for decision in handoff.decisions:
                lines.append(f"- {decision}")
            lines.append("")
        if handoff.open_questions:
            lines.append("**Open questions:**")
            for question in handoff.open_questions:
                lines.append(f"- {question}")
            lines.append("")

    return "\n".join(lines) + "\n"

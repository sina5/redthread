"""Render a docs-site markdown tree from curated handoffs — a `docs/`
directory ready for MkDocs or any other static-site generator.
"""

from pathlib import Path

from redthread.models import Handoff


def render_docs_tree(handoffs: list[Handoff], run_id: str, output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    index_lines = [f"# Run {run_id}", ""]
    for handoff in handoffs:
        index_lines.append(f"- [{handoff.from_phase}]({handoff.from_phase}.md): {handoff.headline}")
    index_path = output_dir / "index.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    written.append(index_path)

    for handoff in handoffs:
        lines = [f"# {handoff.from_phase}", "", handoff.headline, ""]
        for key, value in handoff.key_results.items():
            lines.append(f"- **{key}**: {value}")
        if handoff.decisions:
            lines.append("")
            lines.append("## Decisions")
            lines.extend(f"- {d}" for d in handoff.decisions)
        phase_path = output_dir / f"{handoff.from_phase}.md"
        phase_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(phase_path)

    return written

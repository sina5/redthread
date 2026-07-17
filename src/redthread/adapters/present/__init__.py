"""The present family: generic renderers that consume ONLY upstream
handoffs (never raw entries), so a report, a deck, and a docs-site tree all
read identically whether upstream was train/eval or build/test.
"""

from pathlib import Path

from redthread.adapters.base import PhaseAdapter
from redthread.adapters.present.common import collect_handoffs
from redthread.adapters.present.deck_pptx import render_deck
from redthread.adapters.present.docs_site import render_docs_tree
from redthread.adapters.present.report_md import render_report
from redthread.models import Handoff
from redthread.store import LocalStore

__all__ = ["collect_handoffs", "render_deck", "render_docs_tree", "render_report", "run_present"]


def run_present(
    store: LocalStore,
    run_id: str,
    output_dir: Path,
    phase: str = "present",
    code_dir: Path | None = None,
) -> Handoff:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with PhaseAdapter(store, run_id, phase, code_dir=code_dir) as adapter:
        handoffs = collect_handoffs(store, run_id, phase)

        report_path = output_dir / "report.md"
        report_path.write_text(render_report(handoffs, run_id), encoding="utf-8")

        deck_path = output_dir / "deck.pptx"
        render_deck(handoffs, run_id).save(str(deck_path))

        docs_dir = output_dir / "docs"
        render_docs_tree(handoffs, run_id, docs_dir)

        report_artifact = adapter.add_artifact(report_path, kind="report")
        deck_artifact = adapter.add_artifact(deck_path, kind="deck")

        adapter.set_summary(f"# present summary\n\nGenerated from {len(handoffs)} phase(s).\n")
        return adapter.publish_handoff(
            headline=f"present generated report + deck from {len(handoffs)} phase(s)",
            key_results={"phases_summarized": len(handoffs)},
            best_artifacts=[report_artifact.artifact_id, deck_artifact.artifact_id],
        )

"""Example app pipeline, phase 2: test.

Consumes ONLY build's handoff, fetches the build artifact by id, and
publishes its own curated result for a present phase to pick up.
"""

from pathlib import Path

from redthread.adapters.base import PhaseAdapter
from redthread.store import LocalStore


def run_tests(store: LocalStore, run_id: str, code_dir: Path | None = None) -> None:
    with PhaseAdapter(store, run_id, "test", code_dir=code_dir) as adapter:
        build_handoff = adapter.upstream("build")
        _, artifact_path = store.resolve_artifact(run_id, build_handoff.best_artifacts[0])

        adapter.log_note(tested_artifact=artifact_path.name)
        coverage_pct = 87
        adapter.log_metric(coverage_pct=coverage_pct, failures=0)

        adapter.publish_handoff(
            headline=f"tests passed, {coverage_pct}% coverage",
            key_results={"coverage_pct": coverage_pct, "failures": 0},
        )

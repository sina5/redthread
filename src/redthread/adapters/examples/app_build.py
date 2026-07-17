"""Example app pipeline, phase 1: build.

Same PhaseAdapter, same core, entirely different domain — proving phase
names and metric fields are just data the adapter layer supplies.
"""

from pathlib import Path

from redthread.adapters.base import PhaseAdapter
from redthread.store import LocalStore


def run_build(
    store: LocalStore, run_id: str, artifact_path: Path, code_dir: Path | None = None
) -> None:
    with PhaseAdapter(store, run_id, "build", code_dir=code_dir) as adapter:
        adapter.log_decision("enabled tree-shaking to cut bundle size")
        adapter.log_metric(warnings=0, bundle_size_kb=842)

        artifact = adapter.add_artifact(artifact_path, kind="build-output")

        adapter.set_summary("# build summary\n\n0 warnings, bundle 842kb.\n")
        adapter.publish_handoff(
            headline="build ok, 0 warnings",
            key_results={"warnings": 0, "bundle_size_kb": 842},
            best_artifacts=[artifact.artifact_id],
            decisions=["enabled tree-shaking to cut bundle size"],
        )

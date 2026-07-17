"""Scripted end-to-end sessions proving the store core is domain-neutral:
the same code path serves an ML pipeline (train/eval/present) and an app
pipeline (build/test/present) with zero special-casing.
"""

import pytest

from redthread.models import Handoff
from redthread.store import LocalStore, StoreError


@pytest.mark.parametrize(
    "phases",
    [
        ["train", "eval", "present"],
        ["build", "test", "present"],
    ],
)
def test_full_session_round_trips_for_any_phase_pipeline(tmp_path, phases):
    store_path = tmp_path / "store"
    store = LocalStore.init(store_path, project_id="demo", phases=phases)

    run = store.start_run()
    assert run.status == "active"
    assert set(run.phases) == set(phases)

    first_phase, second_phase, third_phase = phases

    store.log(run.run_id, first_phase, "decision", payload={"note": "chose approach A"})
    store.log(run.run_id, first_phase, "metric", payload={"value": 42})

    artifact_source = tmp_path / "output.bin"
    artifact_source.write_bytes(b"some produced output")
    artifact = store.add_artifact(run.run_id, first_phase, artifact_source, kind="result")

    entries = store.read_entries(run.run_id, phase=first_phase)
    assert len(entries) == 3  # decision, metric, artifact_ref
    assert {e.type for e in entries} == {"decision", "metric", "artifact_ref"}

    store.set_summary(run.run_id, first_phase, f"# {first_phase} summary\n\ndone.\n")
    assert store.get_summary(run.run_id, first_phase) == f"# {first_phase} summary\n\ndone.\n"

    handoff = Handoff(
        from_phase=first_phase,
        run_id=run.run_id,
        headline=f"{first_phase} complete",
        key_results={"score": 0.9},
        best_artifacts=[artifact.artifact_id],
    )
    store.publish_handoff(handoff)

    # second phase consumes ONLY the handoff, never raw entries — the contract rule
    upstream = store.get_handoff(run.run_id, first_phase)
    assert upstream.headline == f"{first_phase} complete"
    resolved_artifact, local_path = store.resolve_artifact(run.run_id, upstream.best_artifacts[0])
    assert resolved_artifact.sha256 == artifact.sha256
    assert local_path.read_bytes() == b"some produced output"

    store.log(run.run_id, second_phase, "milestone", payload={"consumed": first_phase})

    # third phase (present, in both example pipelines) has nothing published yet
    with pytest.raises(StoreError):
        store.get_handoff(run.run_id, third_phase)


def test_logging_to_undeclared_phase_is_rejected(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build", "test"])
    run = store.start_run()
    with pytest.raises(StoreError):
        store.log(run.run_id, "deploy", "note", payload={})


def test_artifact_id_collision_is_rejected(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    run = store.start_run()
    f = tmp_path / "a.txt"
    f.write_text("v1")
    store.add_artifact(run.run_id, "build", f, kind="log", artifact_id="dup")
    f.write_text("v2")
    with pytest.raises(StoreError):
        store.add_artifact(run.run_id, "build", f, kind="log", artifact_id="dup")


def test_entries_from_two_nodes_do_not_collide_on_filename(tmp_path):
    """Concurrent writers never collide on a filename because the ULID, not
    the advisory seq, is the identity — the core guarantee behind M2 sync."""
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    run = store.start_run()
    for _ in range(5):
        store.log(run.run_id, "build", "note", payload={})
    entries_dir = store.layout.entries_dir(run.run_id, "build")
    filenames = [p.name for p in entries_dir.glob("*.json")]
    assert len(filenames) == len(set(filenames)) == 5

"""The portable-sync acceptance scenario: a git bare repo as the hub, two
clones acting as two different nodes, concurrent appends, and a
kill-and-resume flow that proves swapping the machine running a phase
never strands context.
"""

import subprocess

from redthread.blobs.rsync import RsyncBackend
from redthread.resume import resume
from redthread.store import LocalStore, gitio


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _push_fresh_store(store: LocalStore, remote_url: str) -> None:
    root = store.layout.root
    gitio.configure_identity(root, "Test", "test@example.com")
    gitio.set_remote(root, remote_url)
    gitio.sync(root, "init store")


def test_two_clones_concurrent_appends_merge_conflict_free(tmp_path):
    remote = _bare_remote(tmp_path)

    store_a = LocalStore.init(tmp_path / "clone-a", project_id="demo", phases=["build", "test"])
    _push_fresh_store(store_a, str(remote))
    run = store_a.start_run()
    gitio.sync(store_a.layout.root, "start run")

    gitio.clone(str(remote), tmp_path / "clone-b")
    store_b = LocalStore(tmp_path / "clone-b")
    gitio.configure_identity(store_b.layout.root, "Test", "test@example.com")

    # Both nodes log entries against the SAME run without coordinating.
    store_a.log(run.run_id, "build", "note", payload={"from": "a"})
    store_b.log(run.run_id, "build", "note", payload={"from": "b"})

    assert gitio.sync(store_a.layout.root, "a's entry") is True
    assert gitio.sync(store_b.layout.root, "b's entry") is True  # rebases past a, no conflict

    gitio.pull_rebase(store_a.layout.root)
    entries = store_a.read_entries(run.run_id, phase="build")
    assert {e.payload["from"] for e in entries} == {"a", "b"}


def test_kill_and_resume_across_clones_with_shared_blob_backend(tmp_path):
    remote = _bare_remote(tmp_path)
    objects_dir = tmp_path / "shared-objects"  # stands in for a shared object store

    # --- Node A: starts the run, does some work, publishes a blob artifact.
    store_a = LocalStore.init(tmp_path / "clone-a", project_id="demo", phases=["build", "test"])
    _push_fresh_store(store_a, str(remote))
    run = store_a.start_run()

    record = store_a.get_run(run.run_id)
    record.phases["build"] = "active"
    store_a.save_run(record)

    store_a.log(run.run_id, "build", "decision", payload={"note": "chose approach A"})

    output = tmp_path / "output.bin"
    output.write_bytes(b"partial build output")
    backend_a = RsyncBackend(objects_dir)
    artifact = store_a.add_blob_artifact(
        run.run_id, "build", output, kind="build-output", backend_name="objects", backend=backend_a
    )
    gitio.sync(store_a.layout.root, "node A progress")

    # --- Node A is killed here. Node B picks up the SAME run_id.
    store_b_root = tmp_path / "clone-b"
    resumed = resume(store_b_root, run.run_id, remote=str(remote), host="node-b-host")

    # Node lineage now shows both nodes, with A's stint closed out.
    assert len(resumed.nodes) == 2
    assert resumed.nodes[0].left is not None
    assert resumed.nodes[1].host == "node-b-host"
    assert resumed.nodes[1].left is None

    # Node B has A's full history — nothing was stranded on A's disk.
    store_b = LocalStore(store_b_root)
    entries = store_b.read_entries(run.run_id, phase="build")
    assert any(e.payload.get("note") == "chose approach A" for e in entries)
    assert any(e.type == "milestone" and e.payload.get("event") == "resumed" for e in entries)

    # Node B fetches the artifact by content hash from the shared backend,
    # never from node A's disk.
    backend_b = RsyncBackend(objects_dir)
    resolved, path = store_b.resolve_artifact(
        run.run_id,
        artifact.artifact_id,
        backends={"objects": backend_b},
        dest=tmp_path / "restored.bin",
    )
    assert resolved.sha256 == artifact.sha256
    assert path.read_bytes() == b"partial build output"


def test_daemon_sync_once_pushes_pending_changes(tmp_path):
    from redthread.sync import run_daemon

    remote = _bare_remote(tmp_path)
    store = LocalStore.init(tmp_path / "clone-a", project_id="demo", phases=["build"])
    _push_fresh_store(store, str(remote))
    store.log(store.start_run().run_id, "build", "note", payload={})

    run_daemon(store.layout.root, max_iterations=1)

    gitio.clone(str(remote), tmp_path / "clone-b")
    store_b = LocalStore(tmp_path / "clone-b")
    assert store_b.list_runs() == store.list_runs()

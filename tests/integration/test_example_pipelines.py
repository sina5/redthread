"""M3 acceptance: BOTH example pipelines (ML train/eval, app build/test) run
end to end across two clones on the exact same core, with each phase
consuming only its upstream handoff — never raw entries.
"""

import subprocess

from redthread.adapters.examples.app_build import run_build
from redthread.adapters.examples.app_test import run_tests
from redthread.adapters.examples.ml_eval import run_eval
from redthread.adapters.examples.ml_train import run_training
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


def _clone_b(remote, tmp_path) -> LocalStore:
    gitio.clone(str(remote), tmp_path / "clone-b")
    store_b = LocalStore(tmp_path / "clone-b")
    gitio.configure_identity(store_b.layout.root, "Test", "test@example.com")
    gitio.set_remote(store_b.layout.root, str(remote))
    return store_b


def test_ml_pipeline_across_two_clones(tmp_path):
    remote = _bare_remote(tmp_path)
    store_a = LocalStore.init(
        tmp_path / "clone-a", project_id="ml-demo", phases=["train", "eval", "present"]
    )
    _push_fresh_store(store_a, str(remote))
    run = store_a.start_run()

    run_training(store_a, run.run_id)  # node A: train
    gitio.sync(store_a.layout.root, "train done")

    store_b = _clone_b(remote, tmp_path)
    run_eval(store_b, run.run_id)  # node B: eval, reading train's handoff only
    gitio.sync(store_b.layout.root, "eval done")

    train_handoff = store_b.get_handoff(run.run_id, "train")
    eval_handoff = store_b.get_handoff(run.run_id, "eval")
    assert train_handoff.key_results["val_acc"] > 0
    assert eval_handoff.key_results["test_acc"] < train_handoff.key_results["val_acc"]

    record = store_b.get_run(run.run_id)
    assert record.phases["train"] == "done"
    assert record.phases["eval"] == "done"
    assert record.phases["present"] == "pending"


def test_app_pipeline_across_two_clones_same_core(tmp_path):
    remote = _bare_remote(tmp_path)
    store_a = LocalStore.init(
        tmp_path / "clone-a", project_id="app-demo", phases=["build", "test", "present"]
    )
    _push_fresh_store(store_a, str(remote))
    run = store_a.start_run()

    artifact_source = tmp_path / "app.bin"
    artifact_source.write_bytes(b"compiled app")
    run_build(store_a, run.run_id, artifact_source)  # node A: build
    gitio.sync(store_a.layout.root, "build done")

    store_b = _clone_b(remote, tmp_path)
    run_tests(store_b, run.run_id)  # node B: test, reading build's handoff + artifact
    gitio.sync(store_b.layout.root, "test done")

    build_handoff = store_b.get_handoff(run.run_id, "build")
    test_handoff = store_b.get_handoff(run.run_id, "test")
    assert build_handoff.key_results["warnings"] == 0
    assert test_handoff.key_results["coverage_pct"] == 87

    record = store_b.get_run(run.run_id)
    assert record.phases["build"] == "done"
    assert record.phases["test"] == "done"

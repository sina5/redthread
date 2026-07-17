import pytest
from pydantic import ValidationError

from redthread.adapters.base import PhaseAdapter
from redthread.store import LocalStore, StoreError


def _store(tmp_path):
    return LocalStore.init(tmp_path / "store", project_id="demo", phases=["build", "test"])


def test_enter_rejects_phase_outside_pipeline(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with pytest.raises(StoreError):
        PhaseAdapter(store, run.run_id, "deploy").__enter__()


def test_enter_marks_phase_active(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build"):
        assert store.get_run(run.run_id).phases["build"] == "active"


def test_metrics_are_batched_not_one_entry_per_call(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build", metric_batch_size=100) as adapter:
        for i in range(10):
            adapter.log_metric(i=i)
        # under the batch size, nothing flushed yet
        assert store.read_entries(run.run_id, phase="build", type="metric") == []
    # __exit__ flushes: exactly ONE entry holding all 10 samples
    entries = store.read_entries(run.run_id, phase="build", type="metric")
    assert len(entries) == 1
    assert len(entries[0].payload["samples"]) == 10


def test_metrics_flush_automatically_at_batch_size(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build", metric_batch_size=3) as adapter:
        for i in range(3):
            adapter.log_metric(i=i)
        entries = store.read_entries(run.run_id, phase="build", type="metric")
        assert len(entries) == 1
        assert len(entries[0].payload["samples"]) == 3


def test_publish_handoff_flushes_metrics_and_marks_phase_done(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build", metric_batch_size=100) as adapter:
        adapter.log_metric(x=1)
        adapter.publish_handoff(headline="ok")
    entries = store.read_entries(run.run_id, phase="build", type="metric")
    assert len(entries) == 1  # publish_handoff flushed the pending sample
    assert store.get_run(run.run_id).phases["build"] == "done"


def test_exception_inside_adapter_logs_error_and_marks_phase_failed(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with pytest.raises(RuntimeError), PhaseAdapter(store, run.run_id, "build") as adapter:
        adapter.log_decision("about to fail")
        raise RuntimeError("boom")
    assert store.get_run(run.run_id).phases["build"] == "failed"
    errors = store.read_entries(run.run_id, phase="build", type="error")
    assert len(errors) == 1
    assert "boom" in errors[0].payload["message"]


def test_upstream_returns_handoff_type_only(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build") as adapter:
        adapter.publish_handoff(headline="build ok", key_results={"warnings": 0})
    with PhaseAdapter(store, run.run_id, "test") as adapter:
        upstream = adapter.upstream("build")
        assert upstream.headline == "build ok"
        assert upstream.key_results == {"warnings": 0}


def test_malformed_handoff_fails_fast_and_writes_nothing(tmp_path):
    store = _store(tmp_path)
    run = store.start_run()
    with PhaseAdapter(store, run.run_id, "build") as adapter, pytest.raises(ValidationError):
        adapter.publish_handoff(headline="ok", key_results="not-a-dict")  # wrong type
    with pytest.raises(StoreError):
        store.get_handoff(run.run_id, "build")

import pytest
from pydantic import ValidationError

from redthread.models import Artifact, ContextEntry, Handoff, ProjectManifest, Provenance


def test_context_entry_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ContextEntry(
            entry_id="e1",
            run_id="r1",
            phase="build",
            type="not_a_real_type",
            provenance=Provenance(node_id="n1"),
        )


def test_context_entry_phase_is_free_string_not_enum():
    # Any of these phase names must validate at the model layer; pipeline
    # membership is enforced by LocalStore, not by the schema.
    for phase in ["train", "eval", "present", "build", "test", "deploy"]:
        entry = ContextEntry(
            entry_id="e1",
            run_id="r1",
            phase=phase,
            type="note",
            provenance=Provenance(node_id="n1"),
        )
        assert entry.phase == phase


def test_artifact_requires_valid_sha256():
    with pytest.raises(ValidationError):
        Artifact(
            artifact_id="a1",
            kind="build",
            sha256="not-hex",
            size_bytes=1,
            backend="inline",
            uri="x",
            produced_by_phase="build",
        )


def test_artifact_rejects_unknown_backend():
    with pytest.raises(ValidationError):
        Artifact(
            artifact_id="a1",
            kind="build",
            sha256="0" * 64,
            size_bytes=1,
            backend="ftp",
            uri="x",
            produced_by_phase="build",
        )


def test_project_manifest_rejects_empty_and_duplicate_phases():
    with pytest.raises(ValidationError):
        ProjectManifest(project_id="p", phases=[])
    with pytest.raises(ValidationError):
        ProjectManifest(project_id="p", phases=["build", "build"])


def test_handoff_key_results_is_domain_neutral_free_form():
    ml = Handoff(from_phase="train", run_id="r1", headline="ok", key_results={"val_acc": 0.9})
    app = Handoff(from_phase="build", run_id="r2", headline="ok", key_results={"coverage_pct": 87})
    assert ml.key_results["val_acc"] == 0.9
    assert app.key_results["coverage_pct"] == 87

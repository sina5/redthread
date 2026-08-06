import subprocess
from pathlib import Path

import pytest

from redthread.mcp import tools
from redthread.store import LocalStore, StoreError, gitio


def _store(tmp_path):
    return LocalStore.init(tmp_path / "store", project_id="demo", phases=["build", "test"])


def test_run_start_and_list(tmp_path):
    store = _store(tmp_path)
    record = tools.run_start(store)
    assert record["run_id"] in tools.run_list(store)


def test_context_log_and_read_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    logged = tools.context_log(store, "build", "note", payload={"msg": "hi"}, run_id=run_id)

    read = tools.context_read(store, phase="build", run_id=run_id)
    assert read["run_id"] == run_id
    assert read["count"] == 1
    assert read["entries"][0]["entry_id"] == logged["entry_id"]
    assert read["entries"][0]["payload"] == {"msg": "hi"}


def test_artifact_put_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    source = tmp_path / "f.txt"
    source.write_text("payload", encoding="utf-8")

    put = tools.artifact_put(store, "build", str(source), kind="log", run_id=run_id)
    got = tools.artifact_get(store, put["artifact_id"], run_id=run_id)
    assert got["artifact"]["sha256"] == put["sha256"]
    assert Path(got["path"]).read_text(encoding="utf-8") == "payload"


def test_summary_update_and_get(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    tools.summary_update(store, "build", "# hi\n", run_id=run_id)
    assert tools.summary_get(store, "build", run_id=run_id)["markdown"] == "# hi\n"


def test_handoff_publish_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    published = tools.handoff_publish(
        store, "build", headline="build ok", key_results={"warnings": 0}, run_id=run_id
    )
    fetched = tools.handoff_get(store, "build", run_id=run_id)
    assert fetched == published


def test_memory_write_read_list_roundtrip(tmp_path):
    store = _store(tmp_path)
    written = tools.memory_write(store, "agent", "notes.md", "remember this")
    assert written["key"] == "notes.md"
    assert tools.memory_read(store, "agent", "notes.md") == "remember this"

    index = tools.memory_list(store, "agent")
    assert [i["key"] for i in index] == ["notes.md"]
    assert index[0]["description"] == "remember this"


def test_memory_list_describes_entries_and_spans_namespaces(tmp_path):
    store = _store(tmp_path)
    tools.memory_write(store, "notes", "a.md", "body", description="a conventions note")
    tools.memory_write(store, "sessions", "b.md", "body")

    index = tools.memory_list(store)
    assert {i["namespace"] for i in index} == {"notes", "sessions"}
    assert next(i for i in index if i["key"] == "a.md")["description"] == "a conventions note"


def test_memory_search_finds_entry_by_body(tmp_path):
    store = _store(tmp_path)
    tools.memory_write(store, "notes", "a.md", "we chose rsync for blobs")

    hits = tools.memory_search(store, "rsync")
    assert [h["key"] for h in hits] == ["a.md"]
    assert "rsync" in hits[0]["match"]


def test_context_log_rejects_phase_outside_pipeline(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    with pytest.raises(StoreError):
        tools.context_log(store, "deploy", "note", run_id=run_id)


# ---- context_bootstrap ---------------------------------------------------


def test_context_bootstrap_on_an_empty_store_reports_no_run_and_no_memory(tmp_path):
    store = _store(tmp_path)
    payload = tools.context_bootstrap(store)

    assert payload["project"] == {"project_id": "demo", "name": None, "phases": ["build", "test"]}
    assert payload["current_run"] is None
    assert payload["runs"] == {"total": 0, "recent": []}
    assert payload["memory"] == {"namespaces": [], "total": 0, "entries": []}
    assert "run_start" in payload["_next"]
    assert "no long-term memory yet" in payload["_next"]


def test_context_bootstrap_surfaces_runs_memory_handoffs_and_summaries(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    tools.summary_update(store, "build", "# built\n")
    tools.handoff_publish(store, "build", headline="build ok")
    tools.memory_write(store, "notes", "uv.md", "body", description="Toolchain choice")

    payload = tools.context_bootstrap(store)

    assert payload["current_run"] == run_id
    assert payload["runs"]["total"] == 1
    assert payload["runs"]["recent"][0]["run_id"] == run_id
    assert payload["runs"]["recent"][0]["status"] == "active"
    assert payload["handoffs"] == [{"phase": "build", "headline": "build ok"}]
    assert payload["summaries"] == ["build"]
    assert payload["memory"]["namespaces"] == ["notes"]
    assert payload["memory"]["entries"][0]["description"] == "Toolchain choice"
    assert run_id in payload["_next"]


def test_context_bootstrap_lists_recent_runs_newest_first_within_limit(tmp_path):
    store = _store(tmp_path)
    run_ids = [tools.run_start(store)["run_id"] for _ in range(4)]

    payload = tools.context_bootstrap(store, recent_runs=2)

    assert payload["runs"]["total"] == 4
    assert [r["run_id"] for r in payload["runs"]["recent"]] == run_ids[::-1][:2]


def test_context_bootstrap_caps_the_memory_index(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        tools.memory_write(store, "notes", f"{i}.md", "body")

    payload = tools.context_bootstrap(store, memory_limit=2)
    assert payload["memory"]["total"] == 5
    assert len(payload["memory"]["entries"]) == 2


def test_context_bootstrap_accepts_an_explicit_run(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    tools.run_start(store)
    tools.handoff_publish(store, "build", headline="older build", run_id=older)

    payload = tools.context_bootstrap(store, run_id=older)
    assert payload["current_run"] == older
    assert payload["handoffs"] == [{"phase": "build", "headline": "older build"}]


# ---- implicit current run ------------------------------------------------


def test_run_scoped_tools_default_to_the_active_run(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]

    logged = tools.context_log(store, "build", "note", payload={"msg": "hi"})
    assert logged["run_id"] == run_id

    read = tools.context_read(store, phase="build")
    assert read["run_id"] == run_id
    assert read["entries"][0]["entry_id"] == logged["entry_id"]


def test_omitted_run_id_resolves_to_the_newest_active_run(tmp_path):
    store = _store(tmp_path)
    tools.run_start(store)
    newest = tools.run_start(store)["run_id"]

    assert tools.resolve_run_id(store, None) == newest
    assert tools.context_log(store, "build", "note")["run_id"] == newest


def test_omitted_run_id_skips_runs_that_are_no_longer_active(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    newer = tools.run_start(store)["run_id"]

    record = store.get_run(newer)
    record.status = "done"
    store.save_run(record)

    assert tools.resolve_run_id(store, None) == older


def test_explicit_run_id_always_wins(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    tools.run_start(store)

    assert tools.resolve_run_id(store, older) == older


def test_resolve_run_id_without_any_active_run_says_what_to_do(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(StoreError, match="run_start"):
        tools.resolve_run_id(store, None)


# ---- memory_import -------------------------------------------------------


def _source_tree(tmp_path):
    source = tmp_path / "old-memory"
    (source / "decisions").mkdir(parents=True)
    (source / "sqlite.md").write_text("# Chose SQLite\n", encoding="utf-8")
    (source / "decisions" / "db.md").write_text("nested note\n", encoding="utf-8")
    (source / "logo.png").write_bytes(b"\x89PNG")
    return source


def test_memory_import_ports_a_directory_preserving_structure(tmp_path):
    store = _store(tmp_path)
    source = _source_tree(tmp_path)

    report = tools.memory_import(store, source, namespace="ported", push=False)

    assert report["imported"] == ["decisions/db", "sqlite"]
    assert report["counts"] == {"imported": 2, "skipped": 0, "failed": 0}
    assert store.memory_read("ported", "sqlite") == "# Chose SQLite\n"
    assert store.memory_read("ported", "decisions/db") == "nested note\n"


def test_memory_import_leaves_the_source_files_in_place(tmp_path):
    store = _store(tmp_path)
    source = _source_tree(tmp_path)

    tools.memory_import(store, source, push=False)

    assert (source / "sqlite.md").read_text(encoding="utf-8") == "# Chose SQLite\n"


def test_memory_import_keeps_existing_frontmatter_and_indexes_it(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "note.md").write_text(
        "---\ndescription: Ported from Claude Code\ntags: [migration]\n---\n\nbody\n",
        encoding="utf-8",
    )

    tools.memory_import(store, source, namespace="ported", push=False)

    entry = next(i for i in store.memory_index("ported") if i["key"] == "note")
    assert entry["description"] == "Ported from Claude Code"
    assert entry["tags"] == ["migration"]


def test_memory_import_applies_tags_to_every_entry(tmp_path):
    store = _store(tmp_path)
    source = _source_tree(tmp_path)

    tools.memory_import(store, source, namespace="ported", tags=["legacy"], push=False)

    assert all(i["tags"] == ["legacy"] for i in store.memory_index("ported"))


def test_memory_import_imports_a_single_file(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "one.md"
    source.write_text("solo\n", encoding="utf-8")

    report = tools.memory_import(store, source, namespace="ported", push=False)

    assert report["imported"] == ["one"]


def test_memory_import_skips_existing_keys_unless_overwritten(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "note.md").write_text("new\n", encoding="utf-8")
    store.memory_write("ported", "note", "old\n")

    report = tools.memory_import(store, source, namespace="ported", push=False)
    assert report["imported"] == []
    assert report["skipped"] == [{"key": "note", "reason": "exists"}]
    assert store.memory_read("ported", "note") == "old\n"

    report = tools.memory_import(store, source, namespace="ported", overwrite=True, push=False)
    assert report["imported"] == ["note"]
    assert store.memory_read("ported", "note") == "new\n"


def test_memory_import_reports_unchanged_entries_rather_than_rewriting_them(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "note.md").write_text("same\n", encoding="utf-8")

    tools.memory_import(store, source, namespace="ported", push=False)
    report = tools.memory_import(store, source, namespace="ported", overwrite=True, push=False)

    assert report["imported"] == []
    assert report["skipped"] == [{"key": "note", "reason": "unchanged"}]
    assert "already in this namespace" in report["_next"]


def test_memory_import_reports_unreadable_files_without_failing_the_batch(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "good.md").write_text("fine\n", encoding="utf-8")
    (source / "bad.md").write_bytes(b"\xff\xfe not utf-8")

    report = tools.memory_import(store, source, namespace="ported", push=False)

    assert report["imported"] == ["good"]
    assert [Path(f["path"]).name for f in report["failed"]] == ["bad.md"]


def test_memory_import_raises_for_a_missing_source(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(StoreError, match="does not exist"):
        tools.memory_import(store, tmp_path / "nope", push=False)


def test_memory_import_guides_the_caller_when_nothing_matched(tmp_path):
    store = _store(tmp_path)
    source = tmp_path / "empty"
    source.mkdir()

    report = tools.memory_import(store, source, push=False)

    assert report["counts"]["imported"] == 0
    assert "no text files found" in report["_next"]


def test_memory_import_pushes_once_for_the_whole_batch(tmp_path):
    store, _ = _remote_store(tmp_path)
    source = _source_tree(tmp_path)

    report = tools.memory_import(store, source, namespace="ported")

    assert report["sync"]["status"] == "pushed"
    assert "pushed" in report["_next"]
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=store.layout.root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "import 2 entries into ported" in log


# ---- agents_md_bootstrap -------------------------------------------------


def test_agents_md_bootstrap_creates_file_when_none_exists(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result == {"status": "created", "file": str(project_dir / "AGENTS.md")}
    text = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Agent memory (Redthread)" in text
    assert str(tmp_path / "store") in text


def test_agents_md_bootstrap_appends_to_existing_agents_md(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "AGENTS.md").write_text("# Existing notes\n", encoding="utf-8")

    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result["status"] == "appended"
    text = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# Existing notes\n")
    assert "## Agent memory (Redthread)" in text


def test_agents_md_bootstrap_prefers_existing_claude_md_over_creating_agents_md(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "CLAUDE.md").write_text("# Claude notes\n", encoding="utf-8")

    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result["file"] == str(project_dir / "CLAUDE.md")
    assert not (project_dir / "AGENTS.md").exists()


def test_agents_md_bootstrap_is_idempotent(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    first = tools.agents_md_bootstrap(tmp_path / "store", project_dir)
    assert first["status"] == "created"
    text_after_first = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    second = tools.agents_md_bootstrap(tmp_path / "store", project_dir)
    assert second == {"status": "already_present", "file": str(project_dir / "AGENTS.md")}
    assert (project_dir / "AGENTS.md").read_text(encoding="utf-8") == text_after_first


def _remote_store(tmp_path):
    """A store wired to a bare remote, with a git identity — i.e. the shape a
    real store has once `redthread sync` has been set up."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    store = _store(tmp_path)
    gitio.configure_identity(store.layout.root, "Test", "test@example.com")
    gitio.set_remote(store.layout.root, str(remote))
    return store, remote


def test_memory_write_pushes_to_the_remote_by_default(tmp_path):
    store, remote = _remote_store(tmp_path)

    written = tools.memory_write(store, "notes", "uv.md", "Use uv.", description="Toolchain")

    assert written["sync"] == {"status": "pushed"}
    # Present on the remote, not just committed locally.
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "main"],
        cwd=remote,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "memory/notes/uv.md" in listed


def test_memory_write_with_push_false_leaves_the_entry_uncommitted(tmp_path):
    store, _ = _remote_store(tmp_path)

    written = tools.memory_write(store, "notes", "uv.md", "Use uv.", push=False)

    assert written["sync"] == {"status": "skipped"}
    assert gitio.is_dirty(store.layout.root)


def test_memory_write_reports_a_failed_push_without_losing_the_entry(tmp_path):
    store, _ = _remote_store(tmp_path)
    gitio.set_remote(store.layout.root, str(tmp_path / "does-not-exist.git"))

    written = tools.memory_write(store, "notes", "uv.md", "Use uv.")

    assert written["sync"]["status"] == "failed"
    assert written["sync"]["detail"]
    assert "failed" in written["_next"]
    # The point of not raising: the entry is still readable.
    assert tools.memory_read(store, "notes", "uv.md") == "Use uv."


def test_memory_write_without_a_remote_says_it_never_left_this_machine(tmp_path):
    store = _store(tmp_path)
    gitio.configure_identity(store.layout.root, "Test", "test@example.com")

    written = tools.memory_write(store, "notes", "uv.md", "Use uv.")

    assert written["sync"]["status"] == "committed"
    assert "remote" in written["sync"]["detail"]
    assert not gitio.is_dirty(store.layout.root)


# ---- wrong-store detection ----------------------------------------------
# The failure this guards: a globally-registered MCP server serves project
# A's store while the agent edits project B. Bootstrap is the one call every
# session makes, so it is where the mismatch has to surface.


def test_bootstrap_reports_ok_binding_for_the_workspaces_own_store(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = LocalStore.init(workspace / "redthread-store", project_id="demo", phases=["build"])

    payload = tools.context_bootstrap(store, workspace=workspace)
    assert payload["store"]["binding"] == "ok"
    assert "warning" not in payload


def test_bootstrap_warns_and_halts_on_a_foreign_store(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    own = LocalStore.init(
        workspace / "redthread-store",
        project_id="mine",
        phases=["build"],
        host_repo=workspace,
        publish_marker=False,
    )
    own.memory_write("notes", "conventions", "ours", description="ours")
    foreign = LocalStore.init(tmp_path / "other", project_id="theirs", phases=["build"])
    foreign.memory_write("notes", "conventions", "theirs", description="theirs")

    payload = tools.context_bootstrap(foreign, workspace=workspace)

    assert payload["store"]["binding"] == "mismatch"
    assert "theirs" in payload["warning"]
    # _next must not walk the agent into reading and then writing this store.
    assert payload["_next"].startswith("STOP")
    assert "memory_read" not in payload["_next"]


def test_bootstrap_flags_an_unverified_store_without_halting(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = LocalStore.init(tmp_path / "elsewhere", project_id="other", phases=["build"])

    payload = tools.context_bootstrap(store, workspace=workspace)
    assert payload["store"]["binding"] == "unverified"
    assert "warning" in payload
    assert "confirm with the user" in payload["_next"]


def test_bootstrap_without_a_workspace_leaves_binding_unchecked(tmp_path):
    store = _store(tmp_path)
    payload = tools.context_bootstrap(store)
    assert payload["store"]["binding"] == "unchecked"
    assert "warning" not in payload


def test_memory_write_names_the_project_it_wrote_to(tmp_path):
    store = _store(tmp_path)
    result = tools.memory_write(store, "notes", "k", "body", description="d", push=False)
    assert result["project_id"] == "demo"


def test_agents_md_bootstrap_pins_the_expected_project_id(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    tools.agents_md_bootstrap(tmp_path / "store", project_dir, "demo")

    text = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "`demo`" in text
    assert "STOP" in text

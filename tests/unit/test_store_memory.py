import pytest

from redthread.store import LocalStore


def _store(tmp_path):
    return LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])


def test_memory_write_read_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.memory_write("agent-notes", "preferences.md", "# Preferences\n\nUse uv.\n")
    assert store.memory_read("agent-notes", "preferences.md") == "# Preferences\n\nUse uv.\n"


def test_memory_read_missing_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.memory_read("agent-notes", "missing.md") is None


def test_memory_list_returns_sorted_relative_keys(tmp_path):
    store = _store(tmp_path)
    store.memory_write("agent-notes", "b.md", "b")
    store.memory_write("agent-notes", "a.md", "a")
    store.memory_write("agent-notes", "sub/c.md", "c")
    assert store.memory_list("agent-notes") == ["a.md", "b.md", "sub/c.md"]


def test_memory_list_unknown_namespace_returns_empty(tmp_path):
    store = _store(tmp_path)
    assert store.memory_list("never-used") == []


def test_memory_write_stores_description_as_frontmatter(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "uv.md", "Use uv.\n", description="Toolchain choice")
    text = store.memory_read("notes", "uv.md")
    assert text.startswith("---\n")
    assert "description: Toolchain choice" in text
    assert text.endswith("Use uv.\n")


def test_memory_write_without_description_leaves_content_byte_identical(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "raw.md", "Use uv.\n")
    assert store.memory_read("notes", "raw.md") == "Use uv.\n"


def test_memory_namespaces_lists_only_directories(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "a.md", "a")
    store.memory_write("sessions", "b.md", "b")
    assert store.memory_namespaces() == ["notes", "sessions"]


def test_memory_index_spans_namespaces_with_descriptions(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "a.md", "body\n", description="declared one", tags=["conv"])
    store.memory_write("sessions", "b.md", "# Fell back to heading\n")

    index = store.memory_index()
    by_key = {(i["namespace"], i["key"]): i for i in index}
    assert by_key[("notes", "a.md")]["description"] == "declared one"
    assert by_key[("notes", "a.md")]["tags"] == ["conv"]
    assert by_key[("sessions", "b.md")]["description"] == "Fell back to heading"
    assert by_key[("sessions", "b.md")]["size_bytes"] > 0


def test_memory_index_can_be_scoped_to_one_namespace(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "a.md", "a")
    store.memory_write("sessions", "b.md", "b")
    assert [i["key"] for i in store.memory_index("notes")] == ["a.md"]


def test_memory_search_matches_body_and_reports_matching_line(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "deploy.md", "step one\nuse the staging bucket\n")

    hits = store.memory_search("STAGING")
    assert len(hits) == 1
    assert hits[0]["key"] == "deploy.md"
    assert hits[0]["match"] == "use the staging bucket"


def test_memory_search_matches_description_and_tags(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "a.md", "opaque body\n", description="about caching", tags=["perf"])

    assert [h["key"] for h in store.memory_search("caching")] == ["a.md"]
    assert [h["key"] for h in store.memory_search("perf")] == ["a.md"]


def test_memory_search_honors_limit_and_empty_query(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.memory_write("notes", f"{i}.md", "shared token\n")

    assert len(store.memory_search("shared", limit=2)) == 2
    assert store.memory_search("   ") == []


@pytest.mark.parametrize("namespace", ["..", ".", "a/b", "a\\b", ""])
def test_memory_rejects_unsafe_namespace(tmp_path, namespace):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write(namespace, "k.md", "x")


@pytest.mark.parametrize("key", ["../escape.md", "/etc/passwd", "a\\..\\b", "", "../../x"])
def test_memory_rejects_unsafe_key(tmp_path, key):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write("agent-notes", key, "x")


def test_memory_key_cannot_escape_namespace_dir(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write("agent-notes", "../../outside.md", "x")
    escape_target = tmp_path / "outside.md"
    assert not escape_target.exists()


# ---- actionable errors ---------------------------------------------------


def test_missing_store_error_names_how_to_create_one(tmp_path):
    from redthread.store import StoreError

    with pytest.raises(StoreError, match="store_init"):
        LocalStore(tmp_path / "nope")


def test_unknown_run_error_points_at_run_list(tmp_path):
    from redthread.store import StoreError

    store = _store(tmp_path)
    with pytest.raises(StoreError, match="run_list"):
        store.get_run("no-such-run")


def test_phase_outside_pipeline_error_names_the_valid_phases_and_the_fix(tmp_path):
    from redthread.store import StoreError

    store = _store(tmp_path)
    run_id = store.start_run().run_id
    with pytest.raises(StoreError, match="add-phase"):
        store.log(run_id, "deploy", "note")


def test_missing_handoff_error_suggests_summary_and_raw_log(tmp_path):
    from redthread.store import StoreError

    store = _store(tmp_path)
    run_id = store.start_run().run_id
    with pytest.raises(StoreError, match="summary_get"):
        store.get_handoff(run_id, "build")


def test_unknown_artifact_error_lists_the_ids_that_do_exist(tmp_path):
    from redthread.store import StoreError

    store = _store(tmp_path)
    run_id = store.start_run().run_id
    source = tmp_path / "real.txt"
    source.write_text("x", encoding="utf-8")
    store.add_artifact(run_id, "build", source, "log")

    with pytest.raises(StoreError, match="known ids: real"):
        store.resolve_artifact(run_id, "missing")


def test_memory_search_match_line_ignores_frontmatter(tmp_path):
    store = _store(tmp_path)
    store.memory_write(
        "notes", "uv.md", "we standardized on uv\n", description="Uses uv, not conda"
    )

    hits = store.memory_search("uv")
    assert len(hits) == 1
    # The declared description already comes back as its own field; the match
    # line should point at the body, not echo the frontmatter.
    assert hits[0]["description"] == "Uses uv, not conda"
    assert hits[0]["match"] == "we standardized on uv"


def test_memory_search_still_matches_metadata_only_hits(tmp_path):
    store = _store(tmp_path)
    store.memory_write("notes", "a.md", "opaque body\n", description="about caching")

    hits = store.memory_search("caching")
    assert len(hits) == 1
    assert hits[0]["match"] is None

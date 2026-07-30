from redthread import memory_doc


def test_split_returns_meta_and_body():
    meta, body = memory_doc.split("---\ndescription: a note\ntags: [x]\n---\n\nbody text\n")
    assert meta == {"description": "a note", "tags": ["x"]}
    assert body == "body text\n"


def test_split_leaves_plain_text_untouched():
    assert memory_doc.split("just text\n") == ({}, "just text\n")


def test_split_does_not_treat_unclosed_rule_as_frontmatter():
    text = "---\nthis is a horizontal rule, not frontmatter\n"
    assert memory_doc.split(text) == ({}, text)


def test_split_rejects_non_mapping_frontmatter():
    text = "---\n- a\n- b\n---\nbody\n"
    assert memory_doc.split(text) == ({}, text)


def test_with_frontmatter_is_noop_without_metadata():
    assert memory_doc.with_frontmatter("body\n") == "body\n"


def test_with_frontmatter_adds_description_to_plain_text():
    out = memory_doc.with_frontmatter("body\n", description="what this is")
    assert memory_doc.split(out) == ({"description": "what this is"}, "body\n")


def test_with_frontmatter_merges_into_existing_block_and_unions_tags():
    existing = "---\ndescription: old\ntags:\n- a\n---\n\nbody\n"
    out = memory_doc.with_frontmatter(existing, description="new", tags=["b"])
    meta, body = memory_doc.split(out)
    assert meta["description"] == "new"
    assert meta["tags"] == ["a", "b"]
    assert body == "body\n"


def test_describe_prefers_declared_description():
    text = "---\ndescription: the summary\n---\n\n# A Heading\n"
    assert memory_doc.describe(text) == "the summary"


def test_describe_falls_back_to_first_meaningful_line():
    assert memory_doc.describe("\n\n# Deploy notes\n\nmore\n") == "Deploy notes"


def test_describe_skips_code_fences_and_returns_none_when_empty():
    assert memory_doc.describe("```\n\n") is None


def test_describe_clips_long_values():
    described = memory_doc.describe("x" * 300, max_len=20)
    assert len(described) == 20
    assert described.endswith("…")


def test_tags_of_normalizes_scalar_and_missing():
    assert memory_doc.tags_of("---\ntags: solo\n---\n\nb\n") == ["solo"]
    assert memory_doc.tags_of("plain\n") == []

from redstone import knowledge


def test_knowledge_base_is_well_formed():
    errors = knowledge.lint()
    assert not errors, "\n".join(errors)


def test_unverified_index_is_up_to_date():
    path = knowledge.KNOWLEDGE / "UNVERIFIED.md"
    assert path.exists(), "run: uv run python -m redstone.knowledge index"
    assert path.read_text(encoding="utf-8") == knowledge.index(), "run: uv run python -m redstone.knowledge index"

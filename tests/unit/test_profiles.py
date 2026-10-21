"""
Unit tests for the ingestion profiles (docs/design-rag.md §6.2).

A profile's definition is baked into every vector stored under its name, so
it must never change under that name. test_profile_hashes_pinned turns such a
change into a red pipeline before merge instead of `409`s on the VM during a
grading run.

If this test fails because you changed a profile: don't update the pinned
value. Add a new profile with a new name and ingest it into a new collection.
If you added a profile, add its line here. Either way the change needs the
other teammate's approval in review (§10).
"""

from __future__ import annotations

import dataclasses

import pytest

PINNED_DEFINITION_HASHES = {
    "sliding-window": "32add4d0e3d75b80",
    "type-tailored": "65cea5df4246259e",
    "embedding-alt": "3f00f174b1420b40",
    "embedding-cls": "60da3e724a00c3f9",
}


def test_profile_hashes_pinned():
    from app.services.rag.profiles import PROFILES

    actual = {name: p.definition_hash() for name, p in PROFILES.items()}

    assert actual == PINNED_DEFINITION_HASHES


def test_query_prefix_changes_definition_hash_but_not_ingestion_hash():
    # query_prefix doesn't affect stored vectors, so it must not mark a
    # collection stale, but it does change retrieval results.
    from app.services.rag.profiles import get_profile

    base = get_profile("sliding-window")
    changed = dataclasses.replace(base, query_prefix="query: ")

    assert changed.hash() == base.hash()
    assert changed.definition_hash() != base.definition_hash()


@pytest.mark.parametrize(
    "field, value",
    [
        ("embedding_model", "BAAI/bge-small-en-v1.5"),
        ("embedding_revision", "0" * 40),
        ("document_prefix", "passage: "),
    ],
)
def test_ingestion_side_fields_change_ingestion_hash(field, value):
    from app.services.rag.profiles import get_profile

    base = get_profile("sliding-window")

    assert dataclasses.replace(base, **{field: value}).hash() != base.hash()


def test_chunker_kind_is_part_of_the_hash():
    # Two chunker kinds with coincidentally equal field values must not hash
    # the same.
    from app.services.rag.profiles import PerPage, SlidingWindow, get_profile

    base = get_profile("sliding-window")
    window = SlidingWindow(200, 40)
    pdf_per_page = dict(base.chunkers, repo_pdf=PerPage(oversized=window))

    assert dataclasses.replace(base, chunkers=pdf_per_page).hash() != base.hash()


@pytest.mark.parametrize("name", ["embedding-alt", "embedding-cls"])
def test_embedding_profiles_differ_from_baseline_only_in_the_embedding_model(name):
    # Axis 2 must hold chunking fixed, or it compares two things at once.
    from app.services.rag.profiles import get_profile

    baseline = get_profile("sliding-window")
    alt = get_profile(name)

    assert alt.chunkers == baseline.chunkers
    assert alt.embedding_model != baseline.embedding_model


def test_type_tailored_differs_from_baseline_only_in_chunking():
    # Axis 1 must hold the embedding model fixed.
    from app.services.rag.profiles import get_profile

    baseline = get_profile("sliding-window")
    tailored = get_profile("type-tailored")

    assert tailored.embedding_model == baseline.embedding_model
    assert tailored.embedding_revision == baseline.embedding_revision
    assert tailored.chunkers != baseline.chunkers


def test_window_sizes_fit_minilm_input_limit():
    # MiniLM truncates at 256 word-pieces and the text past it is silently
    # dropped; chunk sizes leave room for a document prefix.
    from app.services.rag.profiles import (
        PROFILES,
        PerPage,
        Semantic,
        SlidingWindow,
    )

    for profile in PROFILES.values():
        for chunker in profile.chunkers.values():
            if isinstance(chunker, PerPage):
                chunker = chunker.oversized
            if isinstance(chunker, SlidingWindow):
                size = chunker.chunk_size
            else:
                assert isinstance(chunker, Semantic)
                size = chunker.max_chunk_size
            assert size <= 200, profile.name


def test_every_profile_covers_every_chunked_resource_type():
    from app.services.rag.profiles import CHUNKED_RESOURCE_TYPES, Profile, get_profile

    base = get_profile("sliding-window")
    missing_pdf = {t: c for t, c in base.chunkers.items() if t != "repo_pdf"}

    with pytest.raises(ValueError):
        Profile(
            name="broken",
            embedding_model=base.embedding_model,
            embedding_revision=base.embedding_revision,
            query_prefix="",
            document_prefix="",
            chunkers=missing_pdf,
        )
    assert set(base.chunkers) == set(CHUNKED_RESOURCE_TYPES)


def test_unknown_profile_raises():
    from app.services.rag.profiles import get_profile

    with pytest.raises(KeyError):
        get_profile("no-such-profile")


def test_collection_name_is_per_course_and_profile():
    from app.services.rag.profiles import get_profile

    assert get_profile("type-tailored").collection_name(7) == "course_7__type-tailored"

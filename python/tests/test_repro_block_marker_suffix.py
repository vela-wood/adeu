"""
A replacement whose new text starts with a block marker ("1. ", "- ", "# ")
and spans a paragraph break stranded the host paragraph's trailing text
before the new paragraphs instead of carrying it along.

    "0 1."  modify "0 1" -> "1. 0\n\n0"   accepted ".\n\n1. 0\n\n0"
    "a b."  modify "a "  -> "1. a\n\n"    accepted "b.\n\n1. a"

Mid-paragraph, the marker is literal text, not a block:

    "0 0 1."  -> "0 1. 0\n\n0."              accepted "0 \n\n1. 0\n\n0."

Hypothesis counterexamples from test_p1_pinned_text_roundtrip_is_exact.
"""

import io

import docx
import pytest

from adeu.diff import generate_edits_via_paragraph_alignment
from adeu.ingest import extract_text_from_stream
from adeu.redline.engine import RedlineEngine


def _roundtrip(original: str, target: str) -> str:
    doc = docx.Document()
    doc.add_paragraph(original)
    stream = io.BytesIO()
    doc.save(stream)

    clean = extract_text_from_stream(io.BytesIO(stream.getvalue()), clean_view=True)
    edits = list(generate_edits_via_paragraph_alignment(clean, target))

    engine = RedlineEngine(io.BytesIO(stream.getvalue()), author="Test")
    stats = engine.process_batch(edits)
    assert stats["edits_skipped"] == 0

    engine.accept_all_revisions(remove_comments=True)
    return extract_text_from_stream(engine.save_to_stream(), clean_view=True)


@pytest.mark.parametrize(
    ("original", "target"),
    [
        ("0 1.", "1. 0\n\n0."),
        ("a b.", "1. a\n\nb."),
        ("a b.", "* a\n\nb."),
        ("a b.", "# a\n\nb."),
    ],
)
def test_block_marker_keeps_suffix_order(original, target):
    assert _roundtrip(original, target) == target


@pytest.mark.parametrize(
    ("original", "target"),
    [
        ("0 0 1.", "0 1. 0\n\n0."),
        ("x a b.", "x 1. a\n\nb."),
        ("x a", "x 1. a\n\nb"),
    ],
)
def test_mid_paragraph_marker_is_literal(original, target):
    assert _roundtrip(original, target) == target

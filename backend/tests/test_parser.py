"""
test_parser.py — Unit tests for rfc_parser.py

Run with: pytest backend/tests/test_parser.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rfc_parser import (
    _strip_page_breaks,
    _strip_boilerplate,
    _split_into_sections,
    _normalise_prose,
    parse_rfc,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

RFC793_SNIPPET = """\
RFC 793                                                   September 1981


   TRANSMISSION CONTROL PROTOCOL

   DARPA INTERNET PROGRAM

Status of This Memo

   This document specifies a standard Internet protocol.

Table of Contents

   1. Introduction ....................................... 1
   2. Philosophy .......................................... 9

1.  Introduction

   The Transmission Control Protocol (TCP) is intended for use as a
   highly reliable host-to-host protocol between hosts in
   packet-switched computer communication networks.

   +--------+                                     +--------+
   |        |<----------(your connection)-------->|        |
   | Client |                                     | Server |
   |        |         TCP Connection              |        |
   +--------+                                     +--------+

2.  Philosophy

   TCP is a connection-oriented, end-to-end reliable protocol designed
   to fit into a layered hierarchy of protocols.
"""

PAGE_BREAK_TEXT = "First line.\n\x0cAuthor Name\nRFC Title\nSecond line."

BOILERPLATE_TEXT = """\
Status of This Memo

   This is the status.

1.  Introduction

   Hello world.
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPageBreakStripping:
    def test_removes_form_feed_and_headers(self):
        result = _strip_page_breaks(PAGE_BREAK_TEXT)
        assert "\x0c" not in result
        assert "Second line." in result

    def test_preserves_content_outside_page_breaks(self):
        text = "No page breaks here.\nJust normal text."
        assert _strip_page_breaks(text) == text


class TestBoilerplateStripping:
    def test_removes_status_of_this_memo(self):
        result = _strip_boilerplate(BOILERPLATE_TEXT)
        assert "This is the status." not in result

    def test_preserves_content_after_boilerplate(self):
        result = _strip_boilerplate(BOILERPLATE_TEXT)
        assert "Hello world." in result

    def test_removes_table_of_contents(self):
        text = "Table of Contents\n   1. Intro ...... 1\n\n1.  Introduction\n\n   Content here."
        result = _strip_boilerplate(text)
        assert "1. Intro" not in result
        assert "Content here." in result


class TestSectionSplitting:
    def test_splits_on_numbered_headings(self):
        text = "1.  Introduction\n\n   First section.\n\n2.  Background\n\n   Second section."
        sections = _split_into_sections(text)
        headings = [s.heading for s in sections]
        assert any("Introduction" in h for h in headings)
        assert any("Background" in h for h in headings)

    def test_preamble_becomes_abstract(self):
        text = "Some preamble text.\n\n1.  Introduction\n\n   Body."
        sections = _split_into_sections(text)
        assert sections[0].heading == "Abstract"

    def test_single_section_document(self):
        text = "Just a plain document with no section headings."
        sections = _split_into_sections(text)
        assert len(sections) == 1
        assert sections[0].id == "s0"


class TestProseNormalisation:
    def test_joins_wrapped_lines(self):
        text = "This is a long\nsentence that was\nsoft wrapped."
        result = _normalise_prose(text)
        assert result == "This is a long sentence that was soft wrapped."

    def test_collapses_multiple_blank_lines(self):
        text = "Para one.\n\n\n\nPara two."
        result = _normalise_prose(text)
        assert "\n\n\n" not in result


class TestFullParser:
    def test_parse_rfc_returns_expected_keys(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        assert "rfcNumber" in result
        assert "title" in result
        assert "sections" in result

    def test_rfc_number_preserved(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        assert result["rfcNumber"] == 793

    def test_figure_detected_in_sections(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        types = [s["type"] for s in result["sections"]]
        assert "figure" in types, "Expected at least one figure section from ASCII art"

    def test_toc_stripped(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        full_text = " ".join(s["content"] for s in result["sections"])
        assert "Introduction ......" not in full_text

    def test_boilerplate_stripped(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        full_text = " ".join(s["content"] for s in result["sections"])
        assert "This document specifies a standard" not in full_text


class TestAbstractPreambleCleanup:
    def test_strips_header_metadata_before_abstract(self):
        text = """\
Internet Engineering Task Force (IETF)                      W. Eddy
Request for Comments: 9293                                   August 2022

                  Transmission Control Protocol (TCP)

Abstract

   This document specifies the TCP protocol.

1.  Purpose and Scope

   TCP is important.
"""
        result = parse_rfc(9293, text)
        abstract_sections = [s for s in result["sections"] if s["heading"] == "Abstract"]
        assert len(abstract_sections) == 1
        abstract_content = abstract_sections[0]["content"]
        # Should NOT contain header metadata
        assert "Internet Engineering Task Force" not in abstract_content
        assert "Request for Comments" not in abstract_content
        # Should contain actual abstract text
        assert "TCP protocol" in abstract_content

    def test_preserves_abstract_without_heading(self):
        """When there is no explicit 'Abstract' heading, keep the full preamble."""
        text = "Some preamble text.\n\n1.  Introduction\n\n   Body."
        sections = _split_into_sections(text)
        assert sections[0].heading == "Abstract"
        assert "Some preamble text" in sections[0].content


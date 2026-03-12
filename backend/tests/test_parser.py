"""
test_parser.py — Unit tests for rfc_parser.py

Run with: pytest backend/tests/test_parser.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rfc_parser import (
    _strip_page_breaks,
    _extract_toc_sections,
    _strip_boilerplate,
    _split_into_sections,
    _strip_rfc_metadata,
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


class TestTOCExtraction:
    def test_extracts_section_ids(self):
        text = """\
Table of Contents

   1. Introduction ....................................... 1
   2. Philosophy .......................................... 9
   2.1.  Philosophy 2 ....................... 10
   A. Appendix ................................. 10
   A.1. Appendix sub ............... 11

1.  Introduction
"""
        result = _extract_toc_sections(text)
        assert result == {"s1", "s2", "s2_1", "sA", "sA_1"}
        
    def test_returns_none_if_no_toc(self):
        text = "1. Introduction\n\n   Content."
        assert _extract_toc_sections(text) is None



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

    def test_preamble_is_discarded(self):
        """Everything before the first numbered heading is dropped."""
        text = "Some preamble text.\n\n1.  Introduction\n\n   Body."
        sections = _split_into_sections(text)
        assert sections[0].id == "s1"
        assert "preamble" not in sections[0].content.lower()

    def test_indented_subsection_headings(self):
        """Subsection headings indented up to 6 spaces should be detected (RFC 2328 style)."""
        text = (
            "1.  Introduction\n\n"
            "   Overview paragraph.\n\n"
            "    1.1.  Protocol overview\n\n"
            "   Details here.\n\n"
            "    1.2.  Definitions\n\n"
            "   More details.\n"
        )
        sections = _split_into_sections(text)
        ids = [s.id for s in sections]
        assert "s1" in ids
        assert "s1_1" in ids
        assert "s1_2" in ids

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
        # Abstract (s0) should be missing because it's filtered out of sections!
        assert not any(s["id"] == "s0" for s in result["sections"])

    def test_boilerplate_stripped(self):
        result = parse_rfc(793, RFC793_SNIPPET)
        full_text = " ".join(s["content"] for s in result["sections"])
        assert "This document specifies a standard" not in full_text


class TestAbstractAndMetadataStripping:
    def test_abstract_stripped_as_boilerplate(self):
        """Abstract section should be stripped by boilerplate removal."""
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
        # No abstract/s0 section should be present
        assert not any(s["id"] == "s0" for s in result["sections"])
        full_text = " ".join(s["content"] for s in result["sections"])
        assert "TCP protocol" not in full_text  # abstract body is stripped
        assert "TCP is important" in full_text  # real content preserved

    def test_no_preamble_section_created(self):
        """Even without explicit Abstract heading, preamble is discarded."""
        text = "Some preamble text.\n\n1.  Introduction\n\n   Body."
        sections = _split_into_sections(text)
        assert sections[0].id == "s1"
        assert "preamble" not in sections[0].content.lower()

    def test_metadata_stripped_for_sectionless_rfc(self):
        """Old RFCs with no numbered sections should have header metadata removed."""
        text = """\
Network Working Group                                        S. Crocker
Request for Comments: 1                                       7 April 1969

                         Title of RFC

This is the actual content.
"""
        sections = _split_into_sections(text)
        assert len(sections) == 1
        assert sections[0].id == "s0"
        assert "Network Working Group" not in sections[0].content
        assert "Request for Comments" not in sections[0].content
        assert "actual content" in sections[0].content

    def test_strip_rfc_metadata_function(self):
        text = """\
Network Working Group                                        Editor
Request for Comments: 42
Category: Informational

                         Some Title

First paragraph of real content.
"""
        result = _strip_rfc_metadata(text)
        assert "Network Working Group" not in result
        assert "Request for Comments" not in result
        assert "First paragraph" in result

    def test_preface_stripped_as_boilerplate(self):
        """PREFACE heading should be stripped like other boilerplate."""
        text = """\
PREFACE

This document is based on earlier editions.

1.  Introduction

   Content here.
"""
        result = _strip_boilerplate(text)
        assert "based on earlier editions" not in result
        assert "Content here" in result


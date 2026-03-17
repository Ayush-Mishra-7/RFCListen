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
    _extract_title,
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

RFC2328_SNIPPET = """\
RFC 2328                                                   April 1998

                             OSPF Version 2

Status of this Memo

    This document specifies an Internet standards track protocol.

Table of Contents

    1        Introduction ........................................... 6
    1.1      Protocol Overview ...................................... 6
    1.2      Definitions of commonly used terms ..................... 8

1.  Introduction

    Intro text.

    1.1.  Protocol overview

        Overview details.

    1.2  Definitions of commonly used terms

        Definition details.
"""

RFC2328_APPENDIX_TOC_TAIL_SNIPPET = """\
Table of Contents

    16.8     Equal-cost multipath ................................. 178
             Footnotes ............................................ 179
             References ........................................... 183
    A        OSPF data formats .................................... 185
    A.1      Encapsulation of OSPF packets ........................ 185
    G.3      Incomplete resolution of virtual next hops ........... 241
    G.4      Routing table lookup ................................. 241
             Security Considerations .............................. 243
             Author's Address ..................................... 243
             Full Copyright Statement ............................. 244

1.  Introduction

    This document is a specification of the Open Shortest Path First
    (OSPF) TCP/IP internet routing protocol.

    1.1.  Protocol overview

        OSPF routes IP packets based solely on the destination IP
        address found in the IP packet header.
"""

OLD_RFC12_PAGE_BREAK_SNIPPET = """\
Network Working Group                                       M. Wingfield
Request for Comments: 12  REVISED                         26 August 1969

                    IMP-HOST INTERFACE FLOW DIAGRAMS

Wingfield                                                       [Page 1]
\f
RFC 12              IMP-HOST INTERFACE FLOW DIAGRAMS      26 August 1969

IMP to HOST Message
                       +----------+
                       |  Start   |
                       +----------+
"""

OLD_RFC13_PAGE_BREAK_SNIPPET = """\
Network Working Group                                          Vint Cerf
Request for Comments: 13                                       UCLA
                                                          20 August 1969

Referring to NWG/RFC: 11, it appears that file transmissions over
auxiliary connections will require some mechanism to specify END-OF-FILE.

                                                                [Page 1]
\f
RFC 13                         ZERO TEXT LENGTH EOF                   1969

Follow-on content line.
"""

RFC9945_TOC_SNIPPET = """\
RFC 9945                                                  February 2026

                             IETF Community Moderation

Table of Contents

    1.  Introduction
      1.1.  Terminology Note
      1.2.  General Philosophy
    2.  IETF Moderator Team
      2.1.  Composition
         2.1.1.  Team Diversity
      2.2.  Training
    8.  References
      8.1.  Normative References
      8.2.  Informative References
    Appendix A.  Motivation
      A.1.  Background
    Appendix B.  Non-Normative Examples of Disruptive Behavior
    Acknowledgments

1.  Introduction

    This memo establishes a policy for the moderation of disruptive
    participation across the IETF's various public contribution channels.

1.1.  Terminology Note

    In this document, the term "administrator" refers to people assigned
    to manage a public participation channel.

1.2.  General Philosophy

    The cornerstone of this policy is that individuals are responsible
    for furthering the goals of the IETF.

2.  IETF Moderator Team

    This memo defines a consistent approach to moderating the IETF's
    various public online fora.

2.1.  Composition

    The IESG appoints and recalls moderators.

2.1.1.  Team Diversity

    Due to the global nature of the IETF, the membership of this team
    should reflect a diversity of time zones.
"""

WRAPPED_TOC_SNIPPET = """\
Table of Contents

    1.  This is a very long section heading that wraps onto
         a continuation line in the table of contents
    2.  Second section

1.  This is a very long section heading that wraps onto

    This is real body prose and not a table of contents entry.

2.  Second section

    More body prose.
"""

RFC9930_TOC_SNIPPET = """\
Table of Contents

     1.  Introduction
         1.1.  Interoperability Issues
         1.2.  Requirements Language
         1.3.  Terminology
     2.  Protocol Overview
         2.1.  Architectural Model
         2.2.  Protocol-Layering Model
         2.3.  Outer TLVs Versus Inner TLVs
     3.  TEAP Protocol
         3.1.  Version Negotiation
         3.2.  TEAP Authentication Phase 1: Tunnel Establishment
         3.3.  Server Certificate Requirements
         3.4.  Server Certificate Validation
             3.4.1.  Client Certificates Sent During Phase 1
         3.5.  Resumption
             3.5.1.  TLS Session Resumption Using Server State
             3.5.2.  TLS Session Resumption Using Client State
         3.6.  TEAP Authentication Phase 2: Tunneled Authentication
             3.6.1.  Inner Method Ordering
             3.6.2.  Inner EAP Authentication
             3.6.3.  Inner Password Authentication
             3.6.4.  EAP-MSCHAPv2
             3.6.5.  Limitations on Inner Methods
             3.6.6.  Protected Termination and Acknowledged Result
                             Indication
         3.7.  Determining Peer-Id and Server-Id
         3.8.  TEAP Session Identifier
     4.  Message Formats
         4.1.  TEAP Message Format
     9.  References
         9.1.  Normative References
         9.2.  Informative References
     Appendix A.  Evaluation Against Tunnel-Based EAP Method
                     Requirements
     Acknowledgments
     Contributors
     Author's Address

1.  Introduction

     A tunnel-based Extensible Authentication Protocol (EAP) method is an
     EAP method that establishes a secure tunnel and executes other EAP
    methods under the protection of that secure tunnel.

    This document also defines cryptographic derivations for use with TLS
    1.2.  When TLS 1.3 is used, the definitions of cryptographic
    derivations in RFC 9427 MUST be used instead of the ones given here.

1.1.  Interoperability Issues

     TEAP is intended to improve interoperability among tunnel-based EAP
     deployments.

1.2.  Requirements Language

     The key words "MUST", "MUST NOT", and "SHOULD" in this document are
     to be interpreted as described in BCP 14.

1.3.  Terminology

     This section defines the terms used throughout TEAP.

2.  Protocol Overview

     This section introduces the TEAP protocol model.
"""

RFC9901_TOC_SNIPPET = """\
Table of Contents

    9.  Security Considerations
      9.8.  Distribution and Rotation of Issuer Signature Verification
                Key
      9.9.  Forwarding Credentials
      9.10. Integrity of SD-JWTs and SD-JWT+KBs
      9.11. Explicit Typing
    10. Privacy Considerations

1.  Introduction

    This specification defines selective disclosure for JSON Web Tokens.

1.1.  Feature Summary

    1.  SD-JWT is a composite structure, consisting of a JWS plus
         optional Disclosures.
"""

RFC9898_TOC_SNIPPET = """\
Table of Contents

    3.  Review of ND Mitigation Solutions
      3.9.  Gratuitous Neighbor Discovery (GRAND)
      3.10. Source Address Validation Improvement (SAVI) and Router
                Advertisement Guard (RA-Guard)
      3.11. Dealing with NCE Exhaustion Attacks per RFC 6583
      3.12. Registering Self-Generated IPv6 Addresses Using DHCPv6 per
                RFC 9686
      3.13. Enhanced DAD
    4.  Guidelines for Prevention of Potential ND Issues

1.  Introduction

    Neighbor Discovery (ND) specifies IPv6 node behavior on a link.

    1.  LLA DAD: The host forms a Link-Local Address (LLA) and performs
         Duplicate Address Detection.
"""

RFC9908_TOC_SNIPPET = """\
Table of Contents

     1.  Introduction
     2.  Terminology
     3.  CSR Attributes Handling
         3.1.  Extensions to RFC 7030, Section 2.6
         3.2.  Extensions to RFC 7030, Section 4.5.2
         3.3.  Update to RFC 9148
         3.4.  Use of CSR Templates
     4.  Coexistence with Existing Implementations
     5.  Examples Using the Original Approach in RFC 7030
         5.1.  Require an RFC 8994 / ACP subjectAltName with Specific
                     otherName
             5.1.1.  Base64-Encoded Example
             5.1.2.  ASN.1 DUMP Output
     6.  Security Considerations

1.  Introduction

     This document updates RFC 7030 and clarifies how the Certificate
     Signing Request (CSR) Attributes Response can be used.
"""

RFC9915_TOC_SNIPPET = """\
Table of Contents

     7.  DHCP Constants
         7.1.  Multicast Addresses
         7.2.  UDP Ports
         7.3.  DHCP Message Types
         7.4.  DHCP Option Codes
         7.5.  Status Codes
         7.6.  Transmission and Retransmission Parameters
         7.7.  Representation of Time Values and \"Infinity\" as a Time
                     Value
     8.  Client/Server Message Formats
     9.  Relay Agent/Server Message Formats
         9.1.  Relay-forward Message
         9.2.  Relay-reply Message
     10. Representation and Use of Domain Names
     11. DHCP Unique Identifier (DUID)
         11.1.  DUID Contents
         11.2.  DUID Based on Link-Layer Address Plus Time (DUID-LLT)
         11.3.  DUID Assigned by Vendor Based on Enterprise Number
                        (DUID-EN)
         11.4.  DUID Based on Link-Layer Address (DUID-LL)
         11.5.  DUID Based on Universally Unique Identifier (DUID-UUID)
     12. Identity Association

1.  Introduction

     This document specifies DHCP for IPv6 (DHCPv6), a client/server
     protocol that provides managed configuration of devices.
"""

RFC9908_TITLE_SNIPPET = """\
Internet Engineering Task Force (IETF)                M. Richardson, Ed.
Request for Comments: 9908                      Sandelman Software Works
Updates: 7030, 9148                                             O. Friel
Category: Standards Track                                          Cisco
ISSN: 2070-1721                                            D. von Oheimb
                                                                                      Siemens
                                                                                  D. Harkins
                                                                    The Industrial Lounge
                                                                                January 2026

    Clarification and Enhancement of the CSR Attributes Definition in
                                          RFC 7030

Abstract
"""

RFC9915_TITLE_SNIPPET = """\
Internet Engineering Task Force (IETF)                      T. Mrugalski
Request for Comments: 9915                                           ISC
STD: 102                                                         B. Volz
Obsoletes: 8415                                   Individual Contributor
Category: Standards Track                                  M. Richardson
ISSN: 2070-1721                                                      SSW
                                                                                     S. Jiang
                                                                                          BUPT
                                                                                  T. Winters
                                                                                      QA Cafe
                                                                                January 2026

            Dynamic Host Configuration Protocol for IPv6 (DHCPv6)

Abstract
"""

APPENDIX_BODY_SNIPPET = """\
1.  Introduction

    Introductory content.

Appendix A.  Supplementary Material

    Appendix content.

A.1.  Background

    Background content.

Appendix B.  Additional Notes

    More appendix content.
"""

VISUAL_SPLIT_SNIPPET = """\
1.  Introduction

    Opening prose.

    +--------+
    | Box 1  |
    +--------+

    Middle prose.

    +--------+
    | Box 2  |
    +--------+

    Closing prose.
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

    def test_extracts_unpaginated_toc_ids(self):
        result = _extract_toc_sections(RFC9945_TOC_SNIPPET)
        assert {"s1", "s1_1", "s1_2", "s2", "s2_1", "s2_1_1", "s2_2", "sA", "sA_1", "sB"} <= result

    def test_extracts_ids_from_rfc9930_wrapped_toc(self):
        result = _extract_toc_sections(RFC9930_TOC_SNIPPET)
        assert {"s1", "s1_1", "s1_2", "s1_3", "s2", "s3_6_6", "s3_7", "s4_1", "s9_2", "sA"} <= result

    def test_extracts_ids_from_rfc9901_short_word_wrapped_toc(self):
        result = _extract_toc_sections(RFC9901_TOC_SNIPPET)
        assert {"s9", "s9_8", "s9_9", "s9_10", "s9_11", "s10"} <= result

    def test_extracts_ids_from_rfc9898_wrapped_toc(self):
        result = _extract_toc_sections(RFC9898_TOC_SNIPPET)
        assert {"s3", "s3_9", "s3_10", "s3_11", "s3_12", "s3_13", "s4"} <= result

    def test_extracts_ids_from_rfc9908_single_word_wrapped_toc(self):
        result = _extract_toc_sections(RFC9908_TOC_SNIPPET)
        assert {"s5", "s5_1", "s5_1_1", "s5_1_2", "s6"} <= result

    def test_extracts_ids_from_rfc9915_punctuation_wrapped_toc(self):
        result = _extract_toc_sections(RFC9915_TOC_SNIPPET)
        assert {"s11", "s11_3", "s11_4", "s11_5", "s12"} <= result

    def test_extracts_ids_from_bare_appendix_toc_entries(self):
        result = _extract_toc_sections(RFC2328_APPENDIX_TOC_TAIL_SNIPPET)
        assert {"s16_8", "sA", "sA_1", "sG_3", "sG_4"} <= result
        
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

    def test_removes_unpaginated_table_of_contents(self):
        result = _strip_boilerplate(RFC9945_TOC_SNIPPET)
        assert "Table of Contents" not in result
        assert "Terminology Note\n     1.2." not in result
        assert result.count("1.1.  Terminology Note") == 1

    def test_removes_wrapped_table_of_contents(self):
        result = _strip_boilerplate(WRAPPED_TOC_SNIPPET)
        assert "continuation line in the table of contents" not in result
        assert "This is real body prose" in result

    def test_removes_rfc9930_wrapped_toc_tail(self):
        result = _strip_boilerplate(RFC9930_TOC_SNIPPET)
        assert "Protected Termination and Acknowledged Result" not in result
        assert "Indication\n     3.7." not in result
        assert result.lstrip().startswith("1.  Introduction")

    def test_removes_rfc9901_wrapped_toc_tail(self):
        result = _strip_boilerplate(RFC9901_TOC_SNIPPET)
        assert "9.9.  Forwarding Credentials" not in result
        assert "9.10. Integrity of SD-JWTs and SD-JWT+KBs" not in result
        assert result.lstrip().startswith("1.  Introduction")

    def test_removes_rfc9898_wrapped_toc_tail(self):
        result = _strip_boilerplate(RFC9898_TOC_SNIPPET)
        assert "3.10. Source Address Validation Improvement (SAVI) and Router" not in result
        assert "3.11. Dealing with NCE Exhaustion Attacks per RFC 6583" not in result
        assert result.lstrip().startswith("1.  Introduction")

    def test_removes_rfc9908_wrapped_toc_tail(self):
        result = _strip_boilerplate(RFC9908_TOC_SNIPPET)
        assert "5.1.1.  Base64-Encoded Example" not in result
        assert "5.1.2.  ASN.1 DUMP Output" not in result
        assert result.lstrip().startswith("1.  Introduction")

    def test_removes_rfc9915_wrapped_toc_tail(self):
        result = _strip_boilerplate(RFC9915_TOC_SNIPPET)
        assert "11.4.  DUID Based on Link-Layer Address (DUID-LL)" not in result
        assert "11.5.  DUID Based on Universally Unique Identifier (DUID-UUID)" not in result
        assert result.lstrip().startswith("1.  Introduction")

    def test_removes_rfc2328_appendix_toc_tail(self):
        result = _strip_boilerplate(RFC2328_APPENDIX_TOC_TAIL_SNIPPET)
        assert "A        OSPF data formats" not in result
        assert "G.4      Routing table lookup" not in result
        assert "Author's Address" not in result
        assert result.lstrip().startswith("1.  Introduction")


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

    def test_subsection_headings_without_trailing_dot(self):
        text = (
            "1.  Introduction\n\n"
            "   Overview paragraph.\n\n"
            "    1.1  Protocol overview\n\n"
            "   Details here.\n\n"
            "    1.2  Definitions\n\n"
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

    def test_indented_numbered_list_items_do_not_become_headings(self):
        text = (
            "1.  Introduction\n\n"
            "   Introductory text.\n\n"
            "   1.  First step in a numbered list\n"
            "       More detail.\n\n"
            "   2.  Second step in a numbered list\n"
            "       More detail.\n\n"
            "1.1.  Details\n\n"
            "   Section details.\n"
        )
        sections = _split_into_sections(text)
        headings = [s.heading for s in sections]
        assert headings == ["1. Introduction", "1.1. Details"]

    def test_appendix_headings_become_sections(self):
        sections = _split_into_sections(APPENDIX_BODY_SNIPPET)
        headings = [s.heading for s in sections]
        assert headings == [
            "1. Introduction",
            "A. Supplementary Material",
            "A.1. Background",
            "B. Additional Notes",
        ]


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

    def test_split_prose_chunks_get_unique_continued_headings_and_ids(self):
        result = parse_rfc(1, VISUAL_SPLIT_SNIPPET)
        text_sections = [s for s in result["sections"] if s["type"] == "text"]
        assert [s["heading"] for s in text_sections] == [
            "1. Introduction",
            "1. Introduction (continued)",
            "1. Introduction (continued 2)",
        ]
        assert [s["id"] for s in text_sections] == ["s1", "s1_cont1", "s1_cont2"]
        assert len({s["id"] for s in result["sections"]}) == len(result["sections"])

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

    def test_rfc2328_subsections_survive_toc_filtering(self):
        result = parse_rfc(2328, RFC2328_SNIPPET)
        ids = [s["id"] for s in result["sections"]]
        assert "s1" in ids
        assert "s1_1" in ids
        assert "s1_2" in ids

    def test_rfc2328_appendix_toc_tail_starts_at_introduction(self):
        result = parse_rfc(2328, RFC2328_APPENDIX_TOC_TAIL_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert headings[:2] == ["1. Introduction", "1.1. Protocol overview"]

    def test_rfc9945_toc_headings_do_not_duplicate_body_sections(self):
        result = parse_rfc(9945, RFC9945_TOC_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert headings.count("1. Introduction") == 1
        assert headings.count("1.1. Terminology Note") == 1
        assert headings.count("1.2. General Philosophy") == 1
        assert headings.count("2.1.1. Team Diversity") == 1

    def test_rfc9945_first_section_contains_real_prose(self):
        result = parse_rfc(9945, RFC9945_TOC_SNIPPET)
        first_section = result["sections"][0]
        assert first_section["heading"] == "1. Introduction"
        assert "This memo establishes a policy" in first_section["content"]

    def test_rfc9930_starts_at_introduction(self):
        result = parse_rfc(9930, RFC9930_TOC_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert headings[:4] == [
            "1. Introduction",
            "1.1. Interoperability Issues",
            "1.2. Requirements Language",
            "1.3. Terminology",
        ]

    def test_rfc9930_does_not_start_with_leftover_toc_tail(self):
        result = parse_rfc(9930, RFC9930_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] != "3.7. Determining Peer-Id and Server-Id"
        assert "Indication" not in first_section["content"]

    def test_rfc9901_starts_at_introduction_after_toc_strip(self):
        result = parse_rfc(9901, RFC9901_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] == "1. Introduction"

    def test_rfc9898_starts_at_introduction_after_toc_strip(self):
        result = parse_rfc(9898, RFC9898_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] == "1. Introduction"

    def test_rfc9908_starts_at_introduction_after_toc_strip(self):
        result = parse_rfc(9908, RFC9908_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] == "1. Introduction"

    def test_rfc9915_starts_at_introduction_after_toc_strip(self):
        result = parse_rfc(9915, RFC9915_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] == "1. Introduction"

    def test_rfc9901_numbered_body_list_does_not_create_false_headings(self):
        result = parse_rfc(9901, RFC9901_TOC_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert "1. SD-JWT is a composite structure, consisting of a JWS plus" not in headings

    def test_rfc9898_numbered_body_list_does_not_create_false_headings(self):
        result = parse_rfc(9898, RFC9898_TOC_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert "1. LLA DAD: The host forms a Link-Local Address (LLA) and performs" not in headings

    def test_rfc9908_does_not_start_with_leftover_toc_tail(self):
        result = parse_rfc(9908, RFC9908_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] != "5.1.1. Base64-Encoded Example"
        assert "5.1.2. ASN.1 DUMP Output" not in first_section["content"]

    def test_rfc9915_does_not_start_with_leftover_toc_tail(self):
        result = parse_rfc(9915, RFC9915_TOC_SNIPPET)
        first_section = next(s for s in result["sections"] if s["type"] == "text")
        assert first_section["heading"] != "11.4. DUID Based on Link-Layer Address (DUID-LL)"
        assert "11.5. DUID Based on Universally Unique Identifier (DUID-UUID)" not in first_section["content"]

    def test_inline_version_numbers_do_not_create_false_headings(self):
        result = parse_rfc(9930, RFC9930_TOC_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert not any(h.startswith("1.2. When TLS 1.3 is used") for h in headings)

    def test_appendix_sections_are_preserved(self):
        result = parse_rfc(9945, APPENDIX_BODY_SNIPPET)
        headings = [s["heading"] for s in result["sections"] if s["type"] == "text"]
        assert "A. Supplementary Material" in headings
        assert "A.1. Background" in headings
        assert "B. Additional Notes" in headings


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


class TestOldRfcPageBreakHandling:
    def test_strip_page_breaks_handles_rfc12_style_footer_and_header(self):
        result = _strip_page_breaks(OLD_RFC12_PAGE_BREAK_SNIPPET)
        assert "[Page 1]" not in result
        assert "RFC 12              IMP-HOST INTERFACE FLOW DIAGRAMS" not in result
        assert "IMP to HOST Message" in result

    def test_strip_page_breaks_handles_rfc13_style_footer_and_header(self):
        result = _strip_page_breaks(OLD_RFC13_PAGE_BREAK_SNIPPET)
        assert "[Page 1]" not in result
        assert "RFC 13                         ZERO TEXT LENGTH EOF" not in result
        assert "Follow-on content line." in result

    def test_parse_rfc_handles_old_rfc12_style_document(self):
        result = parse_rfc(12, OLD_RFC12_PAGE_BREAK_SNIPPET)
        assert result["rfcNumber"] == 12
        assert len(result["sections"]) >= 1
        assert "IMP to HOST Message" in result["sections"][0]["content"]

    def test_parse_rfc_handles_old_rfc13_style_document(self):
        result = parse_rfc(13, OLD_RFC13_PAGE_BREAK_SNIPPET)
        assert result["rfcNumber"] == 13
        assert len(result["sections"]) >= 1
        assert "Follow-on content line." in result["sections"][0]["content"]


class TestTitleExtraction:
    def test_rfc9908_title_extracted_from_multiline_title_block(self):
        result = _extract_title(RFC9908_TITLE_SNIPPET)
        assert result == "Clarification and Enhancement of the CSR Attributes Definition in RFC 7030"

    def test_rfc9915_title_extracted_without_returning_date(self):
        result = _extract_title(RFC9915_TITLE_SNIPPET)
        assert result == "Dynamic Host Configuration Protocol for IPv6 (DHCPv6)"


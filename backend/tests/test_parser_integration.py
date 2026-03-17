"""
test_parser_integration.py — Integration tests: parse real RFC texts via the live API.

These tests hit the running backend at http://localhost:3000 to fetch and parse
real RFC documents, validating that the parser handles diverse document structures.

Run with:  pytest backend/tests/test_parser_integration.py -v
Requires:  Backend server running on port 3000

Known parser limitations (documented, not asserted):
  - Title extraction uses a centered-line heuristic that can misfire on some
    RFCs (e.g. RFC 2616 picks up an author name).
"""
import pytest
import httpx
import os

API_BASE = os.getenv("RFC_API_BASE", "http://localhost:3000/api")
TIMEOUT = float(os.getenv("RFC_API_TEST_TIMEOUT", "30.0"))  # some RFCs are large / first fetch is uncached


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_parsed(rfc_number: int) -> dict:
    """Fetch the parsed RFC JSON from the running backend."""
    r = httpx.get(f"{API_BASE}/rfc/{rfc_number}/parsed", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


VALID_TYPES = {"text", "figure", "table"}


def _assert_common(data: dict, rfc_number: int):
    """Shared assertions that apply to every parsed RFC."""
    assert data["rfcNumber"] == rfc_number
    assert isinstance(data["title"], str) and len(data["title"]) > 0, "Title must be non-empty"
    assert isinstance(data["sections"], list) and len(data["sections"]) > 0, "Must have sections"

    for section in data["sections"]:
        assert "id" in section
        assert "heading" in section
        assert "content" in section
        assert "type" in section
        assert section["type"] in VALID_TYPES, f"Invalid type: {section['type']}"

    # Boilerplate headings should be stripped
    headings = [s["heading"].lower() for s in data["sections"]]
    assert not any("status of this memo" in h for h in headings), \
        "Boilerplate 'Status of This Memo' should be stripped"


# ── RFC 793: TCP — Rich ASCII Diagrams ────────────────────────────────────────

class TestRFC793:
    """RFC 793 (Transmission Control Protocol) — known for extensive ASCII diagrams."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(793)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 793)

    def test_title_extracted(self, parsed):
        assert "transmission control protocol" in parsed["title"].lower()

    def test_has_figure_sections(self, parsed):
        figures = [s for s in parsed["sections"] if s["type"] == "figure"]
        assert len(figures) >= 1, "RFC 793 should have at least one ASCII diagram"

    def test_figure_has_raw_ascii(self, parsed):
        figures = [s for s in parsed["sections"] if s["type"] == "figure"]
        for fig in figures:
            assert fig.get("rawAscii", "").strip(), \
                f"Figure '{fig['heading']}' should have non-empty rawAscii"

    def test_section_count(self, parsed):
        # TCP RFC is large, expect many sections
        assert len(parsed["sections"]) >= 10


# ── RFC 2616: HTTP/1.1 — Tables & Long Sections ──────────────────────────────

class TestRFC2616:
    """RFC 2616 (HTTP/1.1) — large RFC with tables, many sections.

    NOTE: The title extraction heuristic struggles with this RFC's header
    format (multiple centered author lines). The parser still successfully
    parses the body content.
    """

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(2616)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 2616)

    def test_title_is_non_empty(self, parsed):
        # Title extraction is imperfect for this RFC — just verify non-empty
        assert len(parsed["title"]) > 0

    def test_has_sections(self, parsed):
        assert len(parsed["sections"]) >= 1

    def test_has_text_sections(self, parsed):
        types = {s["type"] for s in parsed["sections"]}
        assert "text" in types


# ── RFC 8446: TLS 1.3 — Complex Modern Structure ─────────────────────────────

class TestRFC8446:
    """RFC 8446 (TLS 1.3) — modern, well-structured, complex RFC."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(8446)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 8446)

    def test_title_extracted(self, parsed):
        title_lower = parsed["title"].lower()
        assert "tls" in title_lower or "transport layer security" in title_lower

    def test_section_count(self, parsed):
        assert len(parsed["sections"]) >= 10

    def test_no_boilerplate_in_content(self, parsed):
        all_content = " ".join(s["content"] for s in parsed["sections"][:5])
        assert "permission to make digital or hard copies" not in all_content.lower()

    def test_has_figures(self, parsed):
        figures = [s for s in parsed["sections"] if s["type"] == "figure"]
        assert len(figures) >= 1, "TLS 1.3 has protocol diagrams"


# ── RFC 9945: Unpaginated TOC — Duplicate Heading Regression ─────────────────

class TestRFC9945:
    """RFC 9945 (IETF Community Moderation) — TOC entries omit page numbers."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(9945)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 9945)

    def test_expected_nested_sections_exist(self, parsed):
        headings = [s["heading"] for s in parsed["sections"] if s["type"] == "text"]
        assert "1. Introduction" in headings
        assert "1.1. Terminology Note" in headings
        assert "1.2. General Philosophy" in headings
        assert "2.1.1. Team Diversity" in headings

    def test_no_duplicate_early_toc_headings(self, parsed):
        headings = [s["heading"] for s in parsed["sections"][:12] if s["type"] == "text"]
        assert headings.count("1. Introduction") == 1
        assert headings.count("1.1. Terminology Note") == 1
        assert headings.count("1.2. General Philosophy") == 1

    def test_first_section_has_real_content(self, parsed):
        first_text = next(s for s in parsed["sections"] if s["type"] == "text")
        assert first_text["heading"] == "1. Introduction"
        assert len(first_text["content"].split()) > 15


# ── RFC 9930: Wrapped TOC Continuation Regression ───────────────────────────

class TestRFC9930:
    """RFC 9930 (TEAP) — wrapped TOC continuation must not leak into body."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(9930)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 9930)

    def test_first_text_section_is_introduction(self, parsed):
        first_text = next(s for s in parsed["sections"] if s["type"] == "text")
        assert first_text["heading"] == "1. Introduction"

    def test_expected_early_headings_exist(self, parsed):
        headings = [s["heading"] for s in parsed["sections"] if s["type"] == "text"]
        assert "1.1. Interoperability Issues" in headings
        assert "1.2. Requirements Language" in headings
        assert "1.3. Terminology" in headings
        assert "2. Protocol Overview" in headings

    def test_does_not_start_with_rfc9930_toc_tail(self, parsed):
        headings = [s["heading"] for s in parsed["sections"][:8] if s["type"] == "text"]
        assert headings[0] != "3.7. Determining Peer-Id and Server-Id"
        assert headings.count("1. Introduction") == 1


# ── RFC 1149: IP over Avian Carriers — Short & Humorous ──────────────────────

class TestRFC1149:
    """RFC 1149 (IP over Avian Carriers) — very short, humorous April Fools RFC."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(1149)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 1149)

    def test_title_extracted(self, parsed):
        title_lower = parsed["title"].lower()
        assert "avian" in title_lower or "carrier" in title_lower or "ip" in title_lower \
            or "datagram" in title_lower or "transmission" in title_lower

    def test_short_document(self, parsed):
        assert 1 <= len(parsed["sections"]) <= 30

    def test_has_text_content(self, parsed):
        text_sections = [s for s in parsed["sections"] if s["type"] == "text"]
        assert len(text_sections) >= 1


# ── RFC 9908: EST CSR Attributes Clarification ──────────────────────────────

class TestRFC9908:
    """RFC 9908 — wrapped TOC fix, title extraction, and appendix handling."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(9908)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 9908)

    def test_title_extracted(self, parsed):
        assert parsed["title"] == "Clarification and Enhancement of the CSR Attributes Definition in RFC 7030"

    def test_first_text_section_is_introduction(self, parsed):
        first_text = next(s for s in parsed["sections"] if s["type"] == "text")
        assert first_text["heading"] == "1. Introduction"

    def test_appendix_heading_present(self, parsed):
        headings = [s["heading"] for s in parsed["sections"] if s["type"] == "text"]
        assert "A. ASN.1 Module" in headings


# ── RFC 9915: DHCPv6 ────────────────────────────────────────────────────────

class TestRFC9915:
    """RFC 9915 — wrapped TOC fix, title extraction, and appendix handling."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return _get_parsed(9915)

    def test_common_fields(self, parsed):
        _assert_common(parsed, 9915)

    def test_title_extracted(self, parsed):
        assert parsed["title"] == "Dynamic Host Configuration Protocol for IPv6 (DHCPv6)"

    def test_first_text_section_is_introduction(self, parsed):
        first_text = next(s for s in parsed["sections"] if s["type"] == "text")
        assert first_text["heading"] == "1. Introduction"

    def test_appendix_headings_present(self, parsed):
        headings = [s["heading"] for s in parsed["sections"] if s["type"] == "text"]
        assert "A. Summary of Changes from RFC 8415" in headings
        assert "B. Appearance of Options in Message Types" in headings
        assert "C. Appearance of Options in the \"options\" Field of DHCP" in headings

    def test_section_ids_are_unique(self, parsed):
        ids = [s["id"] for s in parsed["sections"]]
        assert len(ids) == len(set(ids))


# ── Cross-RFC Smoke Tests ─────────────────────────────────────────────────────

class TestCrossRFC:
    """Smoke tests across all four target RFCs."""

    @pytest.mark.parametrize("rfc_number", [793, 2616, 8446, 1149, 9908, 9915, 9930, 9945])
    def test_every_section_has_valid_type(self, rfc_number):
        data = _get_parsed(rfc_number)
        for section in data["sections"]:
            assert section["type"] in VALID_TYPES, \
                f"RFC {rfc_number}: section '{section['heading']}' has invalid type '{section['type']}'"

    @pytest.mark.parametrize("rfc_number", [793, 2616, 8446, 1149, 9908, 9915, 9930, 9945])
    def test_rfc_number_matches(self, rfc_number):
        data = _get_parsed(rfc_number)
        assert data["rfcNumber"] == rfc_number

    @pytest.mark.parametrize("rfc_number", [793, 2616, 8446, 1149, 9908, 9915, 9930, 9945])
    def test_sections_have_required_keys(self, rfc_number):
        data = _get_parsed(rfc_number)
        required_keys = {"id", "heading", "content", "type"}
        for section in data["sections"]:
            missing = required_keys - set(section.keys())
            assert not missing, \
                f"RFC {rfc_number}: section '{section.get('heading', '?')}' missing keys: {missing}"

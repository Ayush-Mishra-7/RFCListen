"""
rfc_parser.py — Parses raw RFC plain-text into a structured JSON object.

Output schema:
{
  "rfcNumber": int,
  "title": str,
  "sections": [
    {
      "id": str,          # e.g. "s1", "s1.2", "fig3"
      "heading": str,     # e.g. "1. Introduction"
      "content": str,     # Speakable content (announcement for figures/tables)
      "type": "text" | "figure" | "table",
      "rawAscii": str,    # (figures only) original ASCII block
      "rawTable": str,    # (tables only) original table block
    }
  ]
}

See Agent.md for full parser specification.
"""
import re
from dataclasses import dataclass, asdict
from typing import Literal

# ── Data model ────────────────────────────────────────────────────────────────

SectionType = Literal["text", "figure", "table"]


@dataclass
class Section:
    id: str
    heading: str
    content: str
    type: SectionType = "text"
    rawAscii: str = ""
    rawTable: str = ""


# ── Regexes ───────────────────────────────────────────────────────────────────

# RFC page break: form-feed followed by header lines (common in older RFCs)
_RE_PAGE_BREAK = re.compile(
    r"\x0c"                            # form-feed character
    r"[^\n]*\n"                        # header line after FF
    r"[^\n]*\n",                       # second header line (author/title)
    re.MULTILINE,
)

# Page footer: entire line containing [Page N] (includes author/status text)
_RE_PAGE_FOOTER = re.compile(r"^.*\[Page\s+\d+\]\s*$", re.MULTILINE)

# Pattern-based page footer + header (no form-feed)
# Matches: footer line with [Page N], optional blank lines, RFC header line
_RE_PAGE_FOOTER_HEADER = re.compile(
    r"^[^\n]*\[Page\s+\d+\]\s*\n"     # footer: "Author   Standards Track   [Page 9]"
    r"(?:\s*\n)*"                       # blank lines between footer and header
    r"RFC\s+\d+[^\n]*\n",             # header: "RFC 2328   OSPF Version 2   April 1998"
    re.MULTILINE,
)

# Numbered section headings: "1.  Title", "2.1.  Title", "A.  Appendix"
_RE_SECTION_HEADING = re.compile(
    r"^(?P<num>(?:\d+\.)+\s{1,3}|[A-Z]\.\s{1,3})"  # section number
    r"(?P<title>[A-Z][^\n]{2,})",                    # title (starts uppercase)
    re.MULTILINE,
)

# Boilerplate section headings to strip entirely
_BOILERPLATE_HEADINGS = re.compile(
    r"^(Status of [Tt]his Memo|Copyright Notice|Copyright \(C\)|"
    r"Table of Contents|Full Copyright Statement)",
    re.MULTILINE,
)

# ASCII diagram detection heuristic:
# A line is "drawing-like" if it contains any box-drawing chars (+, |)
# or its ratio of drawing characters (+, -, |, *, /, \, =, .) to total
# non-space characters exceeds a threshold.
_DRAWING_CHAR_SET = set('+-|*/\\.=')
_BOX_CHARS = re.compile(r'[+|]')  # Definitive box-drawing chars

# Table detection: multiple lines with | separators
_TABLE_LINE = re.compile(r'^\s*\|.+\|', re.MULTILINE)


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_rfc(rfc_number: int, raw_text: str) -> dict:
    """
    Parse a raw RFC plain-text string into a structured JSON-serialisable dict.
    """
    text = _strip_page_breaks(raw_text)
    toc_ids = _extract_toc_sections(text)
    text = _strip_boilerplate(text)
    sections = _split_into_sections(text)

    # If ToC is present, keep only the sections listed in the ToC.
    if toc_ids is not None:
        filtered_sections = []
        for section in sections:
            # We check if the section ID is in toc_ids.
            # Figures and tables haven't been generated yet, so section IDs are top-level like `s1` or `s2_1`.
            if section.id in toc_ids:
                filtered_sections.append(section)
        sections = filtered_sections

    sections = _classify_and_clean(sections)

    return {
        "rfcNumber": rfc_number,
        "title": _extract_title(raw_text),
        "sections": [asdict(s) for s in sections],
    }


# ── Step 1: Page break / footer cleanup ──────────────────────────────────────

def _strip_page_breaks(text: str) -> str:
    """Remove RFC page headers/footers introduced by form-feed page breaks."""
    text = _RE_PAGE_BREAK.sub("\n", text)
    text = _RE_PAGE_FOOTER_HEADER.sub("\n", text)
    text = _RE_PAGE_FOOTER.sub("", text)
    return text


# ── Step 1.5: Table of Contents Extraction ────────────────────────────────────

def _extract_toc_sections(text: str) -> set[str] | None:
    """
    Finds the Table of Contents and extracts the section IDs listed within it.
    Returns a set of section IDs (e.g. {'s1', 's2_1'}), or None if no ToC is found.
    """
    lines = text.splitlines()
    toc_ids = set()
    in_toc = False

    for line in lines:
        stripped = line.strip()
        if not in_toc and stripped.lower() == "table of contents":
            in_toc = True
            continue
        
        if in_toc:
            if not stripped:
                continue
                
            if _BOILERPLATE_HEADINGS.match(stripped) and stripped.lower() != "table of contents":
                break
            
            if _RE_SECTION_HEADING.match(line):
                break
            
            # Extract section numbers. e.g. "   1. Introduction" or "   A. Appendix"
            match = re.match(r"^\s*(?P<num>\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\.?\s+", line)
            if match:
                num = match.group("num")
                toc_ids.add(f"s{num.replace('.', '_')}")

    return toc_ids if toc_ids else None



# ── Step 2: Boilerplate removal ───────────────────────────────────────────────

def _strip_boilerplate(text: str) -> str:
    """
    Remove well-known boilerplate sections (Status of This Memo, ToC, Copyright).
    We find the heading and consume text until the next top-level section.
    """
    lines = text.splitlines()
    result = []
    skip = False

    for line in lines:
        if _BOILERPLATE_HEADINGS.match(line.strip()):
            skip = True
            continue
        # A new numbered section heading ends skip mode
        if skip and _RE_SECTION_HEADING.match(line):
            skip = False
        if not skip:
            result.append(line)

    return "\n".join(result)


# ── Step 3: Section splitting ─────────────────────────────────────────────────

def _split_into_sections(text: str) -> list[Section]:
    """
    Split the cleaned text into sections based on numbered headings.
    Content before the first section heading becomes a preamble section.
    """
    sections: list[Section] = []
    matches = list(_RE_SECTION_HEADING.finditer(text))

    if not matches:
        # No sections found — treat entire text as a single section
        return [Section(id="s0", heading="RFC Content", content=text.strip())]

    # Preamble (abstract / intro before first numbered section)
    preamble = text[: matches[0].start()].strip()
    if preamble:
        # Strip RFC header metadata — keep only text after "Abstract" heading
        abstract_match = re.search(r'^Abstract\s*$', preamble, re.MULTILINE | re.IGNORECASE)
        if abstract_match:
            preamble = preamble[abstract_match.end():].strip()
        sections.append(Section(id="s0", heading="Abstract", content=preamble))

    for i, match in enumerate(matches):
        heading_num = match.group("num").strip().rstrip(".")
        heading_title = match.group("title").strip()
        heading = f"{heading_num}. {heading_title}"

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        section_id = f"s{heading_num.replace('.', '_')}"
        sections.append(Section(id=section_id, heading=heading, content=content))

    return sections


# ── Step 4: Classify figures / tables; normalise paragraphs ──────────────────

def _classify_and_clean(sections: list[Section]) -> list[Section]:
    """
    For each section, detect embedded figures/tables, split them out as child
    sections, and normalise the prose content.
    """
    result: list[Section]  = []
    fig_count = 0
    tbl_count = 0

    for section in sections:
        sub_sections, fig_count, tbl_count = _extract_visual_blocks(
            section, fig_count, tbl_count
        )
        result.extend(sub_sections)

    return result


def _extract_visual_blocks(
    section: Section, fig_count: int, tbl_count: int
) -> tuple[list[Section], int, int]:
    """
    Within a section's content, find ASCII diagram blocks and table blocks,
    replace them with spoken announcements, and emit them as separate child sections.
    """
    lines = section.content.splitlines()
    sub = []
    current_prose: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Detect block figure (5+ consecutive drawing-character lines)
        if _is_drawing_line(line):
            block, i = _consume_block(lines, i, _is_drawing_line)
            if len(block) >= 3:
                fig_count += 1
                # Flush prose so far
                if current_prose:
                    sub.append(_prose_section(section, "\n".join(current_prose)))
                    current_prose = []
                raw = "\n".join(block)
                announcement = (
                    f"[Figure {fig_count} — refer to the application to view this diagram]"
                )
                sub.append(Section(
                    id=f"fig{fig_count}",
                    heading=f"Figure {fig_count}",
                    content=announcement,
                    type="figure",
                    rawAscii=raw,
                ))
                continue
            else:
                current_prose.extend(block)
                continue

        # ── Detect table (3+ consecutive lines with | separators)
        if _TABLE_LINE.match(line):
            block, i = _consume_block(lines, i, lambda l: bool(_TABLE_LINE.match(l)))
            if len(block) >= 3:
                tbl_count += 1
                if current_prose:
                    sub.append(_prose_section(section, "\n".join(current_prose)))
                    current_prose = []
                raw = "\n".join(block)
                announcement = (
                    f"[Table {tbl_count} — refer to the application to view this table]"
                )
                sub.append(Section(
                    id=f"tbl{tbl_count}",
                    heading=f"Table {tbl_count}",
                    content=announcement,
                    type="table",
                    rawTable=raw,
                ))
                continue
            else:
                current_prose.extend(block)
                continue

        current_prose.append(line)
        i += 1

    # Flush remaining prose
    if current_prose:
        sub.append(_prose_section(section, "\n".join(current_prose)))

    # If nothing was split out, return the cleaned original section
    if not sub:
        section.content = _normalise_prose(section.content)
        return [section], fig_count, tbl_count

    return sub, fig_count, tbl_count


def _is_drawing_line(line: str) -> bool:
    """
    Return True if a line looks like part of an ASCII diagram.

    A line qualifies if:
    - It contains at least one definitive box char (+, |), OR
    - The ratio of drawing characters to non-space chars is >= 40%
      (catches lines of dashes, equals signs, etc.)
    - The line has at least 3 non-space characters total.
    """
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    # Definitive box-drawing character present
    if _BOX_CHARS.search(stripped):
        return True
    # Density check: high proportion of drawing chars
    non_space = [c for c in stripped if c != ' ']
    if not non_space:
        return False
    drawing = [c for c in non_space if c in _DRAWING_CHAR_SET]
    return len(drawing) / len(non_space) >= 0.40


def _consume_block(
    lines: list[str], start: int, predicate
) -> tuple[list[str], int]:
    """Consume consecutive lines matching predicate; return block + new index."""
    block = []
    i = start
    while i < len(lines) and (predicate(lines[i]) or lines[i].strip() == ""):
        block.append(lines[i])
        i += 1
    return block, i


def _prose_section(parent: Section, content: str) -> Section:
    """Create a prose sub-section inheriting metadata from the parent."""
    return Section(
        id=parent.id,
        heading=parent.heading,
        content=_normalise_prose(content),
        type="text",
    )


# ── Prose normalisation ───────────────────────────────────────────────────────

def _normalise_prose(text: str) -> str:
    """
    - Join soft-wrapped lines into paragraphs.
    - Collapse multiple blank lines.
    - Detect definition-style blocks (a term on its own less-indented line
      followed by a more-indented description) and preserve them as
      separate paragraphs.
    """
    paragraphs = re.split(r"\n{2,}", text)
    joined = []
    for para in paragraphs:
        raw_lines = para.splitlines()
        non_empty = [(l, len(l) - len(l.lstrip())) for l in raw_lines if l.strip()]
        if not non_empty:
            continue

        # Check if this paragraph is a definition list:
        # Pattern: a short term line with less indent, followed by
        # a description with deeper indent, repeating.
        if _is_definition_block(non_empty):
            joined.append(_format_definition_block(non_empty))
        else:
            lines = [l.strip() for l, _ in non_empty]
            joined.append(" ".join(lines))
    return "\n\n".join(p for p in joined if p)


def _is_definition_block(lines: list[tuple[str, int]]) -> bool:
    """
    Return True if lines look like a definition list:
    a term with indent N followed by body text with indent > N.
    """
    if len(lines) < 2:
        return False

    i = 0
    found_def = False
    while i < len(lines):
        text, indent = lines[i]
        # Look for a term: a relatively short line
        if i + 1 < len(lines):
            next_text, next_indent = lines[i + 1]
            # Term line is shorter and next line is more indented
            if next_indent > indent and len(text.strip().split()) <= 6:
                found_def = True
                i += 1
                # Skip body lines (same or deeper indent)
                while i < len(lines) and lines[i][1] >= next_indent:
                    i += 1
                continue
        i += 1
    return found_def


def _format_definition_block(lines: list[tuple[str, int]]) -> str:
    """
    Format a definition block, preserving term/body structure.
    Each term starts a new paragraph; body lines are joined.
    """
    result = []
    i = 0
    while i < len(lines):
        text, indent = lines[i]
        # Check if this is a term line (short, followed by more-indented body)
        if i + 1 < len(lines):
            next_text, next_indent = lines[i + 1]
            if next_indent > indent and len(text.strip().split()) <= 6:
                # Emit term
                result.append(text.strip())
                i += 1
                # Collect and join body lines
                body_lines = []
                while i < len(lines) and lines[i][1] >= next_indent:
                    body_lines.append(lines[i][0].strip())
                    i += 1
                result.append(" ".join(body_lines))
                continue
        # Regular line — just append stripped
        result.append(text.strip())
        i += 1
    return "\n\n".join(result)


# ── Title extraction ──────────────────────────────────────────────────────────

def _extract_title(raw_text: str) -> str:
    """
    RFC titles are typically the most prominent centered line in the first
    ~20 lines.  We skip metadata, short phrases, and common non-title text.
    """
    _META_PATTERNS = re.compile(
        r"^("
        r"RFC[\s:]+\d|Request for Comments|Network Working Group|"
        r"Internet Engineering Task Force|Category:|ISSN:|STD:|BCP:|"
        r"Updates:|Obsoletes:|Status of|Copyright|"
        r"prepared\s+for|by\s+|"
        r"\w+\s+\w+\s+\d{4}$"  # "Author Name  Month YYYY"
        r")",
        re.IGNORECASE,
    )
    candidates = []
    for line in raw_text.splitlines()[:25]:
        stripped = line.strip()
        if not stripped or len(stripped) < 8:
            continue
        if _META_PATTERNS.match(stripped):
            continue
        # Compute "centeredness" — highly indented lines are likely titles
        leading = len(line) - len(line.lstrip())
        # Only consider reasonably indented lines (likely centered titles)
        if leading >= 10:
            candidates.append((leading, stripped))

    if not candidates:
        # Fallback: first long non-metadata line in the first 30 lines
        for line in raw_text.splitlines()[:30]:
            stripped = line.strip()
            if len(stripped) > 10 and not _META_PATTERNS.match(stripped):
                return stripped
        return ""

    # Among centered candidates, prefer the first one (titles appear before
    # subtitles / author info lines which may be even more centered)
    for _, text in candidates:
        if len(text) > 10:
            return text
    return candidates[0][1]



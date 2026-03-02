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

# Trailing page footer like "   [Page 12]"
_RE_PAGE_FOOTER = re.compile(r"\s+\[Page\s+\d+\]\s*$", re.MULTILINE)

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
    text = _strip_boilerplate(text)
    sections = _split_into_sections(text)
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
    text = _RE_PAGE_FOOTER.sub("", text)
    return text


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
    """
    paragraphs = re.split(r"\n{2,}", text)
    joined = []
    for para in paragraphs:
        lines = [l.strip() for l in para.splitlines() if l.strip()]
        joined.append(" ".join(lines))
    return "\n\n".join(p for p in joined if p)


# ── Title extraction ──────────────────────────────────────────────────────────

def _extract_title(raw_text: str) -> str:
    """
    RFC titles appear on the first few lines of the document.
    Heuristic: find the first non-blank, non-metadata line in the header.
    """
    for line in raw_text.splitlines()[:30]:
        stripped = line.strip()
        # Skip short lines, lines that look like dates/categories/numbers
        if (
            len(stripped) > 10
            and not re.match(r"^\d|^RFC|^Network|^Request|^Category|^ISSN|^\w+\s+\w+\s+\d{4}", stripped)
        ):
            return stripped
    return "Unknown Title"

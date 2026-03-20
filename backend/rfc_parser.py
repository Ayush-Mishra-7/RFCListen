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
from bisect import bisect_right
from dataclasses import dataclass, asdict, field
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


@dataclass
class TocAnalysis:
    start_offset: int
    end_offset: int
    toc_text: str
    toc_ids: set[str] = field(default_factory=set)
    confidence: float = 0.0
    reason: str = ""


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

# Shared section number pattern used by both body heading detection and
# ToC extraction. Supports styles such as "1.", "1.1.", "1.1", "A.",
# and "A.1".
_SECTION_NUMBER_PATTERN = r"(?:\d+(?:\.\d+)*\.?|[A-Z]\.|[A-Z](?:\.\d+)+\.?)"

# Pattern-based page footer + header (no form-feed)
# Matches: footer line with [Page N], optional blank lines, RFC header line
_RE_PAGE_FOOTER_HEADER = re.compile(
    r"^[^\n]*\[Page[ \t]+\d+\][ \t]*\n"  # footer: "Author   Standards Track   [Page 9]"
    r"(?:[ \t]*\n)*"                         # blank lines between footer and header
    r"RFC[ \t]+\d+[^\n]*\n",               # header: "RFC 2328   OSPF Version 2   April 1998"
    re.MULTILINE,
)

# Numbered section headings: "1.  Title", "2.1.  Title", "A.  Appendix"
# Allow indented sub-section headings and both dotted/undotted numbering
# variants that appear across RFC body text and tables of contents.
_RE_SECTION_HEADING = re.compile(
    r"^[ \t]{0,8}"                                   # optional leading indent
    rf"(?P<num>{_SECTION_NUMBER_PATTERN})"             # section number
    r"\s{1,3}"
    r"(?P<title>[A-Za-z][^\n]{2,})",                  # title (starts letter)
    re.MULTILINE,
)

_RE_TOC_HEADING = re.compile(r"^\s*Table of Contents\s*$", re.IGNORECASE)
_RE_APPENDIX_HEADING = re.compile(
    r"^[ \t]*Appendix\s+(?P<num>[A-Z](?:\.\d+)*)\.?\s+(?P<title>[^\n]{2,})$",
    re.IGNORECASE | re.MULTILINE,
)
_RE_TOC_PAGE_NUMBER = re.compile(r'(?:\.[\s\.]*\.|\s{3,})\s*\d+\s*$')
_RE_RESIDUAL_PAGE_ARTIFACT = re.compile(
    r"^\s*(?:RFC\s+\d+.*|.*\[Page\s+\d+\].*)\s*$",
    re.IGNORECASE,
)
_RE_TOC_APPENDIX_ENTRY = re.compile(r"^\s*(?P<num>[A-Z])\.?\s{2,}(?P<title>[A-Za-z][^\n]{2,})$")

# Boilerplate section headings to strip entirely
_BOILERPLATE_HEADINGS = re.compile(
    r"^(Status of [Tt]his Memo|Copyright Notice|Copyright \(C\)|"
    r"Table of Contents|Full Copyright Statement|Abstract|PREFACE)",
    re.MULTILINE | re.IGNORECASE,
)

_NON_TOC_BOILERPLATE_HEADINGS = re.compile(
    r"^(Status of [Tt]his Memo|Copyright Notice|Copyright \(C\)|"
    r"Full Copyright Statement|Abstract|PREFACE)",
    re.MULTILINE | re.IGNORECASE,
)

_TOC_BACKMATTER_HEADINGS = {
    "acknowledgments",
    "acknowledgements",
    "contributors",
    "references",
    "normative references",
    "informative references",
    "security considerations",
    "iana considerations",
    "authors' addresses",
    "author's address",
    "authors' address",
    "footnotes",
    "index",
    "full copyright statement",
}

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
    toc_analysis = _analyze_toc(text)
    if toc_analysis is not None:
        text = _strip_span(text, toc_analysis.start_offset, toc_analysis.end_offset)
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
    text = _RE_PAGE_FOOTER_HEADER.sub("\n", text)
    text = _RE_PAGE_FOOTER.sub("", text)
    return text


# ── Step 1.5: Table of Contents Extraction ────────────────────────────────────

def _strip_span(text: str, start_offset: int, end_offset: int) -> str:
    """Remove a character span from text and normalise the join boundary."""
    return f"{text[:start_offset].rstrip()}\n\n{text[end_offset:].lstrip()}"


def _is_plausible_section_number(num: str) -> bool:
    """Reject wrapped RFC numbers and similar metadata that look like headings."""
    stripped = num.rstrip(".")
    if not stripped:
        return False
    if stripped[0].isalpha():
        return True
    try:
        parts = [int(part) for part in stripped.split(".") if part]
    except ValueError:
        return False
    if not parts:
        return False
    return all(part <= 99 for part in parts)


def _match_section_id(line: str) -> str | None:
    match = re.match(rf"^\s*(?P<num>{_SECTION_NUMBER_PATTERN})\s+", line)
    if not match:
        return None
    num = match.group("num").rstrip(".")
    if not _is_plausible_section_number(num):
        return None
    return f"s{num.replace('.', '_')}"


def _match_appendix_section_id(line: str) -> str | None:
    match = _RE_APPENDIX_HEADING.match(line.strip())
    if not match:
        return None
    num = match.group("num").rstrip(".")
    return f"s{num.replace('.', '_')}"


def _match_toc_section_id(line: str) -> str | None:
    section_id = _match_section_id(line) or _match_appendix_section_id(line)
    if section_id is not None:
        return section_id
    if _RE_TOC_PAGE_NUMBER.search(line) is None:
        return None
    match = _RE_TOC_APPENDIX_ENTRY.match(line)
    if not match:
        return None
    return f"s{match.group('num')}"


def _leading_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _parse_section_path(num: str) -> tuple[int | str, ...]:
    parts: list[int | str] = []
    for part in num.rstrip(".").split("."):
        if not part:
            continue
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part.upper())
    return tuple(parts)


def _is_next_section_part(previous: int | str, current: int | str) -> bool:
    if isinstance(previous, int) and isinstance(current, int):
        return current == previous + 1
    if isinstance(previous, str) and isinstance(current, str):
        return len(previous) == 1 and len(current) == 1 and ord(current) == ord(previous) + 1
    return False


def _is_plausible_heading_transition(
    previous_path: tuple[int | str, ...] | None,
    current_path: tuple[int | str, ...],
    indent: int,
) -> bool:
    if not current_path:
        return False
    if len(current_path) == 1 and indent > 0:
        return False
    if previous_path is None:
        return True

    previous_depth = len(previous_path)
    current_depth = len(current_path)

    if current_depth == previous_depth + 1:
        return current_path[:-1] == previous_path and current_path[-1] == 1

    max_shared_depth = min(previous_depth, current_depth)
    for shared_depth in range(max_shared_depth, 0, -1):
        if previous_path[:shared_depth - 1] != current_path[:shared_depth - 1]:
            continue
        if not _is_next_section_part(previous_path[shared_depth - 1], current_path[shared_depth - 1]):
            continue
        if current_depth != shared_depth:
            continue
        return True

    if isinstance(previous_path[0], int) and isinstance(current_path[0], str):
        return current_path == ("A",)

    return False


def _iter_section_heading_matches(text: str) -> list[re.Match[str]]:
    """Return only plausible numbered-section matches from the RFC body."""
    lines_with_endings = text.splitlines(keepends=True)
    line_starts: list[int] = []
    cursor = 0
    for line in lines_with_endings:
        line_starts.append(cursor)
        cursor += len(line)

    def has_blank_line_before(match_start: int) -> bool:
        if match_start == 0:
            return True
        line_idx = bisect_right(line_starts, match_start) - 1
        if line_idx <= 0:
            return True
        return lines_with_endings[line_idx - 1].strip() == ""

    matches: list[re.Match[str]] = []
    previous_path: tuple[int | str, ...] | None = None

    for match in _RE_SECTION_HEADING.finditer(text):
        num = match.group("num")
        if not _is_plausible_section_number(num):
            continue
        if not has_blank_line_before(match.start()):
            continue

        line_idx = bisect_right(line_starts, match.start()) - 1
        indent = _leading_indent(lines_with_endings[line_idx]) if line_idx >= 0 else 0
        current_path = _parse_section_path(num)
        if not _is_plausible_heading_transition(previous_path, current_path, indent):
            continue

        matches.append(match)
        previous_path = current_path

    return matches


def _is_toc_backmatter_entry(line: str) -> bool:
    cleaned = _RE_TOC_PAGE_NUMBER.sub("", line)
    stripped = cleaned.strip().rstrip(":.").lower()
    return stripped in _TOC_BACKMATTER_HEADINGS


def _looks_like_toc_title_fragment(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if not bool(re.search(r"[A-Za-z]", stripped)):
        return False
    if stripped.endswith((".", ";", ":")):
        return False

    words = stripped.split()
    if len(words) >= 2:
        return True

    token = words[0].strip("([{<'\"")
    token = token.rstrip(")]}>,'\"")
    if len(token) < 3:
        return False
    return token[0].isalpha()


def _is_toc_continuation_line(
    line: str,
    previous_was_toc_entry: bool,
    previous_entry_indent: int | None = None,
) -> bool:
    if not previous_was_toc_entry:
        return False
    stripped = line.strip()
    if not stripped:
        return False
    if _match_toc_section_id(line) or _is_toc_backmatter_entry(line):
        return False
    if _RE_RESIDUAL_PAGE_ARTIFACT.match(stripped):
        return False
    indent = _leading_indent(line)
    if indent < 2:
        return False
    if previous_entry_indent is not None and indent < previous_entry_indent + 4:
        return False
    return _looks_like_toc_title_fragment(line)


def _looks_like_body_prose(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _match_toc_section_id(line) or _match_appendix_section_id(line) or _is_toc_backmatter_entry(line):
        return False
    if _RE_RESIDUAL_PAGE_ARTIFACT.match(stripped):
        return False
    word_count = len(stripped.split())
    if word_count < 2:
        return False
    if not bool(re.search(r"[a-z]", stripped)):
        return False
    if stripped.endswith((".", ";", ":", ")")) and len(stripped) >= 10:
        return True
    return len(stripped) >= 32 and word_count >= 4


def _next_nonblank_lines(lines: list[str], start_idx: int, limit: int = 3) -> list[tuple[int, str]]:
    result = []
    for idx in range(start_idx, len(lines)):
        if lines[idx].strip():
            result.append((idx, lines[idx]))
            if len(result) >= limit:
                break
    return result


def _looks_like_body_start(lines: list[str], idx: int) -> bool:
    line = lines[idx]
    if not (_match_toc_section_id(line) or _match_appendix_section_id(line) or _is_toc_backmatter_entry(line)):
        return False
    entry_indent = _leading_indent(line)

    look_idx = idx + 1
    saw_blank = False
    while look_idx < len(lines) and not lines[look_idx].strip():
        saw_blank = True
        look_idx += 1

    if look_idx >= len(lines):
        return True

    first_following = lines[look_idx]
    if saw_blank and not (
        _match_toc_section_id(first_following)
        or _match_appendix_section_id(first_following)
        or _is_toc_backmatter_entry(first_following)
        or _RE_RESIDUAL_PAGE_ARTIFACT.match(first_following.strip())
    ):
        return True

    for _, next_line in _next_nonblank_lines(lines, idx + 1, limit=3):
        if _RE_RESIDUAL_PAGE_ARTIFACT.match(next_line.strip()):
            continue
        if _match_toc_section_id(next_line) or _match_appendix_section_id(next_line) or _is_toc_backmatter_entry(next_line):
            return False
        if _is_toc_continuation_line(
            next_line,
            previous_was_toc_entry=True,
            previous_entry_indent=entry_indent,
        ):
            return False
        if _looks_like_body_prose(next_line):
            return True
    return False


def _analyze_toc(text: str) -> TocAnalysis | None:
    """Find the Table of Contents block and extract any listed section IDs."""
    lines_with_endings = text.splitlines(keepends=True)
    if not lines_with_endings:
        return None

    lines = [line.rstrip("\r\n") for line in lines_with_endings]
    offsets: list[int] = []
    cursor = 0
    for line in lines_with_endings:
        offsets.append(cursor)
        cursor += len(line)

    toc_start_idx = None
    for idx, line in enumerate(lines):
        if _RE_TOC_HEADING.match(line.strip()):
            toc_start_idx = idx
            break
    if toc_start_idx is None:
        return None

    toc_ids: set[str] = set()
    toc_end_idx = toc_start_idx + 1
    previous_was_toc_entry = False
    previous_entry_indent: int | None = None

    for idx in range(toc_start_idx + 1, len(lines)):
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            toc_end_idx = idx + 1
            continue

        if _RE_RESIDUAL_PAGE_ARTIFACT.match(stripped):
            toc_end_idx = idx + 1
            continue

        section_id = _match_toc_section_id(line) or _match_appendix_section_id(line)
        is_backmatter = _is_toc_backmatter_entry(line)

        if section_id or is_backmatter:
            if _looks_like_body_start(lines, idx):
                break
            if section_id:
                toc_ids.add(section_id)
            toc_end_idx = idx + 1
            previous_was_toc_entry = True
            previous_entry_indent = _leading_indent(line)
            continue

        if _is_toc_continuation_line(
            line,
            previous_was_toc_entry=previous_was_toc_entry,
            previous_entry_indent=previous_entry_indent,
        ):
            toc_end_idx = idx + 1
            previous_was_toc_entry = True
            continue

        break

    start_offset = offsets[toc_start_idx]
    end_offset = offsets[toc_end_idx] if toc_end_idx < len(offsets) else len(text)
    toc_text = text[start_offset:end_offset]
    confidence = 1.0 if toc_ids else 0.6
    reason = "detected TOC block" if toc_ids else "detected TOC heading without numbered entries"
    return TocAnalysis(
        start_offset=start_offset,
        end_offset=end_offset,
        toc_text=toc_text,
        toc_ids=toc_ids,
        confidence=confidence,
        reason=reason,
    )

def _extract_toc_sections(text: str) -> set[str] | None:
    """
    Finds the Table of Contents and extracts the section IDs listed within it.
    Returns a set of section IDs (e.g. {'s1', 's2_1'}), or None if no ToC is found.
    """
    analysis = _analyze_toc(text)
    return analysis.toc_ids if analysis and analysis.toc_ids else None



# ── Step 2: Boilerplate removal ───────────────────────────────────────────────

def _strip_boilerplate(text: str) -> str:
    """
    Remove well-known boilerplate sections (Status of This Memo, Copyright,
    Abstract, etc.). Table of Contents removal is handled by _analyze_toc.
    """
    toc_analysis = _analyze_toc(text)
    if toc_analysis is not None:
        text = _strip_span(text, toc_analysis.start_offset, toc_analysis.end_offset)

    lines = text.splitlines()
    result = []
    skip = False

    for line in lines:
        if _NON_TOC_BOILERPLATE_HEADINGS.match(line.strip()):
            skip = True
            continue
        # A new numbered section heading ends skip mode
        if skip and (_match_section_id(line) or _RE_APPENDIX_HEADING.match(line.strip())):
            skip = False
        if not skip:
            result.append(line)

    return "\n".join(result)


# ── Step 3: Section splitting ─────────────────────────────────────────────────

# Common RFC header metadata lines that appear before the first section.
_RE_RFC_METADATA = re.compile(
    r"^("
    r"RFC[\s:\-]+\d|Request for Comments|Network Working Group|"
    r"Internet Engineering Task Force|Category:|ISSN:|STD:|BCP:|"
    r"Updates:|Obsoletes:|Status of|Copyright|"
    r"prepared\s+for|by\s+"
    r")",
    re.IGNORECASE,
)


def _strip_rfc_metadata(text: str) -> str:
    """
    Remove RFC header metadata lines (Network Working Group, Request for
    Comments, Category, etc.) from the beginning of *text*.  Stops as soon
    as a non-metadata, non-blank line is encountered.
    """
    lines = text.splitlines()
    first_content = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _RE_RFC_METADATA.match(stripped):
            first_content = i + 1
            continue
        # Centered title-like short lines (highly indented) are still metadata
        leading = len(line) - len(line.lstrip())
        if leading >= 10 and len(stripped) < 80:
            first_content = i + 1
            continue
        break
    return "\n".join(lines[first_content:]).strip()


def _split_into_sections(text: str) -> list[Section]:
    """
    Split the cleaned text into sections based on numbered headings.
    Everything before the first numbered heading is discarded (preamble /
    abstract / metadata) — the user only cares about the actual content
    starting from section 1.
    """
    sections: list[Section] = []
    matches = _iter_body_heading_matches(text)

    if not matches:
        # No sections found — treat entire text as a single section
        # but strip leading RFC metadata so the user doesn't hear it.
        cleaned = _strip_rfc_metadata(text)
        return [Section(id="s0", heading="RFC Content", content=cleaned.strip())]

    # Skip everything before the first numbered section heading.

    for i, match in enumerate(matches):
        heading_num = match[2].strip().rstrip(".")
        heading_title = match[3].strip()
        heading = f"{heading_num}. {heading_title}"

        start = match[1]
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        section_id = f"s{heading_num.replace('.', '_')}"
        sections.append(Section(id=section_id, heading=heading, content=content))

    return sections


def _iter_body_heading_matches(text: str) -> list[tuple[int, int, str, str]]:
    """Return plausible body headings including appendix headings."""
    lines_with_endings = text.splitlines(keepends=True)
    line_starts: list[int] = []
    cursor = 0
    for line in lines_with_endings:
        line_starts.append(cursor)
        cursor += len(line)

    def has_blank_line_before(match_start: int) -> bool:
        if match_start == 0:
            return True
        line_idx = bisect_right(line_starts, match_start) - 1
        if line_idx <= 0:
            return True
        return lines_with_endings[line_idx - 1].strip() == ""

    candidates: list[tuple[int, int, str, str]] = []
    for match in _RE_SECTION_HEADING.finditer(text):
        candidates.append((match.start(), match.end(), match.group("num"), match.group("title")))
    for match in _RE_APPENDIX_HEADING.finditer(text):
        candidates.append((match.start(), match.end(), match.group("num"), match.group("title")))
    candidates.sort(key=lambda item: item[0])

    matches: list[tuple[int, int, str, str]] = []
    previous_path: tuple[int | str, ...] | None = None

    for start, end, num, title in candidates:
        if not _is_plausible_section_number(num):
            continue
        if not has_blank_line_before(start):
            continue

        line_idx = bisect_right(line_starts, start) - 1
        indent = _leading_indent(lines_with_endings[line_idx]) if line_idx >= 0 else 0
        current_path = _parse_section_path(num)
        if not _is_plausible_heading_transition(previous_path, current_path, indent):
            continue

        matches.append((start, end, num, title))
        previous_path = current_path

    return matches


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
    prose_chunk_index = 0
    i = 0

    def flush_current_prose() -> None:
        nonlocal current_prose, prose_chunk_index
        if not current_prose:
            return
        sub.append(_prose_section(section, "\n".join(current_prose), prose_chunk_index))
        prose_chunk_index += 1
        current_prose = []

    while i < len(lines):
        line = lines[i]

        # ── Detect block figure (5+ consecutive drawing-character lines)
        if _is_drawing_line(line):
            block, i = _consume_block(lines, i, _is_drawing_line)
            if len(block) >= 3:
                fig_count += 1
                # Flush prose so far
                flush_current_prose()
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
                flush_current_prose()
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
    flush_current_prose()

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


def _prose_section(parent: Section, content: str, prose_chunk_index: int = 0) -> Section:
    """Create a prose sub-section inheriting metadata from the parent."""
    if prose_chunk_index == 0:
        section_id = parent.id
        heading = parent.heading
    else:
        section_id = f"{parent.id}_cont{prose_chunk_index}"
        if prose_chunk_index == 1:
            heading = f"{parent.heading} (continued)"
        else:
            heading = f"{parent.heading} (continued {prose_chunk_index})"
    return Section(
        id=section_id,
        heading=heading,
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
        r"RFC\s+\d+\b.*\d{4}$|Request for Comments|Network Working Group|"
        r"Internet Engineering Task Force|Category:|ISSN:|STD:|BCP:|"
        r"Updates:|Obsoletes:|Status of|Copyright|"
        r"prepared\s+for|by\s+|"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$"
        r")",
        re.IGNORECASE,
    )
    heading_markers = {"abstract", "status of this memo", "table of contents", "copyright notice"}
    lines = raw_text.splitlines()[:40]
    cutoff = len(lines)
    for idx, line in enumerate(lines):
        if line.strip().lower() in heading_markers:
            cutoff = idx
            break

    blocks: list[list[tuple[str, int]]] = []
    current_block: list[tuple[str, int]] = []
    for line in lines[:cutoff]:
        stripped = line.strip()
        if not stripped:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
        if _META_PATTERNS.match(stripped):
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
        current_block.append((stripped, len(line) - len(line.lstrip())))
    if current_block:
        blocks.append(current_block)

    def score_block(block: list[tuple[str, int]]) -> tuple[int, int, int]:
        text_parts = [text for text, _ in block]
        full_text = " ".join(text_parts)
        total_length = sum(len(text) for text in text_parts)
        max_length = max((len(text) for text in text_parts), default=0)
        avg_indent = sum(indent for _, indent in block) // len(block)
        short_indented_lines = sum(
            1
            for text, indent in block
            if indent >= 20 and len(text.split()) <= 4 and len(text) <= 30
        )
        has_date = any(_META_PATTERNS.match(text) for text in text_parts)
        score = total_length
        if max_length >= 30:
            score += 15
        if len(block) <= 3:
            score += 8
        if avg_indent >= 3:
            score += 6
        if re.search(r"[a-z]", full_text):
            score += 10
        score -= short_indented_lines * 12
        if has_date:
            score -= 20
        return score, max_length, -len(block)

    if blocks:
        best_block = max(blocks, key=score_block)
        best_text = " ".join(text for text, _ in best_block).strip()
        if len(best_text) > 10:
            return best_text

    for line in raw_text.splitlines()[:30]:
        stripped = line.strip()
        if len(stripped) > 10 and not _META_PATTERNS.match(stripped):
            return stripped
    return ""



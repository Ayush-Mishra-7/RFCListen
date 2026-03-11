import re
import json

_RE_SECTION_HEADING = re.compile(
    r'^(?P<num>(?:\d+\.)+\s{1,3}|[A-Z]\.\s{1,3})'  # section number
    r'(?P<title>[A-Z][^\n]{2,})',                    # title (starts uppercase)
    re.MULTILINE,
)

_BOILERPLATE_HEADINGS = re.compile(
    r'^(Status of [Tt]his Memo|Copyright Notice|Copyright \(C\)|'
    r'Table of Contents|Full Copyright Statement)',
    re.MULTILINE,
)

def _extract_toc_ids(text: str) -> set[str] | None:
    lines = text.splitlines()
    toc_ids = set()
    in_toc = False

    for line in lines:
        stripped = line.strip()
        if not in_toc and stripped.lower() == 'table of contents':
            in_toc = True
            continue
        
        if in_toc:
            if not stripped:
                continue
                
            if _BOILERPLATE_HEADINGS.match(stripped) and stripped.lower() != 'table of contents':
                break
            
            if _RE_SECTION_HEADING.match(line):
                break
            
            # Extract section numbers. e.g. "   1. Introduction" or "   A. Appendix"
            match = re.match(r"^\s*(?P<num>\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\.?\s+", line)
            if match:
                num = match.group("num")
                toc_ids.add(f"s{num.replace('.', '_')}")

    return toc_ids if toc_ids else None

text = '''
Status of This Memo

   This is status

Table of Contents

   1. Introduction ....................................... 1
   2. Philosophy .......................................... 9
   2.1.  Philosophy 2 ....................... 10
   A. Appendix ................................. 10
   A.1. Appendix sub ............... 11

1.  Introduction
'''

result = _extract_toc_ids(text)
print(json.dumps(list(result)))

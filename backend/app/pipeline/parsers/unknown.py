import re
from typing import Tuple, List
from ..schemas import UnknownDocumentFields


def parse_unknown(text: str) -> Tuple[UnknownDocumentFields, List[str]]:
    warnings = ["Document type could not be categorized. Raw text preserved in separate debug file."]
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Extract any prominent title/heading lines
    headings = []
    for line in lines[:10]:
        if len(line) < 60 and (line.isupper() or line.istitle() or ":" in line):
            headings.append(line)

    summary = lines[0] if lines else "Unclassified document content"
    return UnknownDocumentFields(summary=summary, extracted_headings=headings), warnings

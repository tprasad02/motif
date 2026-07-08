import re


NAV_PATTERNS = [
    r"subscribe\s+now",
    r"sign\s+in",
    r"advertisement",
    r"cookie\s+policy",
    r"privacy\s+policy",
    r"all\s+rights\s+reserved",
]


def clean_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lowered = line.lower()
        if any(re.search(pattern, lowered) for pattern in NAV_PATTERNS):
            continue
        if len(line) <= 2:
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


import hashlib
import re
from dataclasses import dataclass

try:
    import tiktoken
except ImportError:
    tiktoken = None


@dataclass
class TextChunk:
    chunk_id: str
    chunk_index: int
    text: str
    token_count: int
    start_char: int
    end_char: int
    section_title: str
    chunk_role: str


def count_tokens(text: str) -> int:
    if tiktoken:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    return max(1, len(re.findall(r"\S+", text)))


def stable_chunk_id(source_key: str, content_hash: str, chunk_index: int) -> str:
    seed = f"{source_key}:{content_hash}:structural:{chunk_index}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:32]


def _clean_lines(text: str) -> str:
    cleaned = []
    seen_short = set()
    boilerplate_markers = [
        "advertisement",
        "about us",
        "archive:",
        "around the internet",
        "contact us",
        "cookie policy",
        "do not sell",
        "dmca policy",
        "featured videos",
        "latest articles",
        "latest news",
        "log in",
        "newsletter",
        "now playing",
        "now streaming",
        "privacy policy",
        "related stories",
        "recent posts",
        "reuse this content",
        "share this",
        "sign up",
        "subscribe",
        "terms of use",
        "trending now",
        "watch on",
    ]
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            cleaned.append("")
            continue
        lowered = line.lower()
        if lowered.startswith(("http://", "https://", "www.")):
            continue
        if lowered in {"in repo", "sponsored"}:
            continue
        if any(marker in lowered for marker in boilerplate_markers):
            continue
        if re.fullmatch(r"(powered by|search|menu|comments?|movies?|reviews?|interviews?|features?|more)[\W_]*", lowered):
            continue
        if len(line) < 80:
            key = line.lower()
            if key in seen_short:
                continue
            seen_short.add(key)
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def _paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if len(parts) <= 2 and len(text) > 3000:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        parts = []
        current = []
        current_words = 0
        for line in lines:
            words = len(line.split())
            if current and (current_words + words > 180 or re.match(r"^\s*(?:[A-Z][A-Za-z ]{2,80}|[IVX]+\.)\s*$", line)):
                parts.append(" ".join(current))
                current = [line]
                current_words = words
            else:
                current.append(line)
                current_words += words
        if current:
            parts.append(" ".join(current))
    return [part for part in parts if not _is_boilerplate_paragraph(part)]


def _is_boilerplate_paragraph(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    if not lowered:
        return True
    if len(lowered) < 20 and lowered in {"cast", "credits", "more", "search", "share"}:
        return True
    markers = [
        "all content",
        "around the internet",
        "be the first to comment",
        "click here to report",
        "do you feel this content is inappropriate",
        "do not sell",
        "featured videos",
        "find articles by",
        "leave a comment",
        "log in",
        "more about",
        "powered by",
        "privacy policy",
        "recent posts",
        "related stories",
        "reuse this content",
        "search keywords",
        "sign up",
        "terms of use",
        "trending now",
    ]
    if any(marker in lowered for marker in markers):
        return True
    citation_lines = len(re.findall(r"(?:^|\n)\s*\[?\d+\]?[\).]", text))
    if len(text) < 5000 and citation_lines >= 5 and not any(term in lowered for term in ["shot", "scene", "camera", "sound", "performance"]):
        return True
    if lowered.count(" doi:") > 2 or lowered.count(" journal ") > 6:
        return True
    return False


def _section_role(source_type: str, text: str) -> str:
    lowered = text.lower()
    if source_type == "screenplay":
        return "scene_evidence"
    if source_type in {"interview", "festival_qa", "director_commentary", "cast_interview"}:
        return "creator_commentary"
    if any(term in lowered for term in ["camera", "shot", "cut", "editing", "sound", "score", "color", "lighting", "frame", "close-up"]):
        return "formal_observation"
    if any(term in lowered for term in ["suggests", "argues", "reading", "interpret", "theme", "symbol", "means"]):
        return "interpretive_claim"
    if any(term in lowered for term in ["goes to", "discovers", "finds", "tells", "returns", "kills", "meets"]):
        return "plot_summary"
    return "interpretive_claim"


def _split_long_section(section: str, max_tokens: int) -> list[str]:
    paras = _paragraphs(section) or [section]
    groups = []
    current = []
    current_tokens = 0
    for para in paras:
        para_tokens = count_tokens(para)
        if current and current_tokens + para_tokens > max_tokens:
            groups.append("\n\n".join(current))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens
    if current:
        groups.append("\n\n".join(current))

    split = []
    for group in groups:
        if count_tokens(group) <= max_tokens:
            split.append(group)
            continue
        words = re.findall(r"\S+\s*", group)
        start = 0
        while start < len(words):
            token_total = 0
            end = start
            while end < len(words) and token_total < max_tokens:
                token_total += count_tokens(words[end])
                end += 1
            split.append("".join(words[start:end]).strip())
            start = end
    return [part for part in split if part]


def _screenplay_sections(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?m)^(?P<title>(?:INT\.|EXT\.|INT/EXT\.|I/E\.)[^\n]{0,90})$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [("Screenplay section", section) for section in _split_long_section(text, 650)]
    sections = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group("title").strip()
        body = text[start:end].strip()
        if count_tokens(body) >= 40:
            sections.append((title, body))
    return sections


def _qa_sections(text: str) -> list[tuple[str, str]]:
    paras = _paragraphs(text)
    sections = []
    current_title = "Interview exchange"
    current = []
    for para in paras:
        is_question = "?" in para and count_tokens(para) < 80
        speaker_question = re.match(r"^(q|interviewer|audience|question)\s*[:\-]", para, re.I)
        if (is_question or speaker_question) and current:
            sections.append((current_title, "\n\n".join(current)))
            current = [para]
            current_title = para[:90]
        else:
            current.append(para)
            if is_question or speaker_question:
                current_title = para[:90]
    if current:
        sections.append((current_title, "\n\n".join(current)))
    return sections or [("Interview exchange", text)]


def _prose_sections(text: str) -> list[tuple[str, str]]:
    paras = _paragraphs(text)
    sections = []
    current_title = "Main argument"
    current = []
    current_tokens = 0
    for para in paras:
        para_tokens = count_tokens(para)
        looks_like_heading = para_tokens <= 12 and not para.endswith(".")
        if looks_like_heading and current:
            sections.append((current_title, "\n\n".join(current)))
            current_title = para[:90]
            current = []
            current_tokens = 0
            continue
        if current and current_tokens + para_tokens > 620:
            sections.append((current_title, "\n\n".join(current)))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens
    if current:
        sections.append((current_title, "\n\n".join(current)))
    return sections


def _structural_sections(text: str, source_type: str) -> list[tuple[str, str]]:
    if source_type == "screenplay":
        return _screenplay_sections(text)
    if source_type in {"interview", "festival_qa", "director_commentary", "cast_interview", "video_essay_transcript"}:
        return _qa_sections(text)
    return _prose_sections(text)


def chunk_text(
    source_key: str,
    content_hash: str,
    text: str,
    source_type: str = "essay",
    max_tokens: int = 720,
) -> list[TextChunk]:
    cleaned_text = _clean_lines(text)
    chunks: list[TextChunk] = []
    chunk_index = 0
    cursor = 0
    for section_title, section in _structural_sections(cleaned_text, source_type):
        for part in _split_long_section(section, max_tokens):
            token_count = count_tokens(part)
            if token_count < 35:
                continue
            start_char = cleaned_text.find(part[:80], cursor)
            if start_char < 0:
                start_char = cursor
            end_char = start_char + len(part)
            chunks.append(
                TextChunk(
                    chunk_id=stable_chunk_id(source_key, content_hash, chunk_index),
                    chunk_index=chunk_index,
                    text=part,
                    token_count=token_count,
                    start_char=start_char,
                    end_char=end_char,
                    section_title=section_title[:120],
                    chunk_role=_section_role(source_type, part),
                )
            )
            chunk_index += 1
            cursor = end_char
    return chunks

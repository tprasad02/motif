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


def count_tokens(text: str) -> int:
    if tiktoken:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    return max(1, len(re.findall(r"\S+", text)))


def stable_chunk_id(source_key: str, content_hash: str, chunk_index: int) -> str:
    seed = f"{source_key}:{content_hash}:{chunk_index}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:32]


def chunk_text(source_key: str, content_hash: str, text: str, max_tokens: int = 850, overlap_tokens: int = 130) -> list[TextChunk]:
    words = re.findall(r"\S+\s*", text)
    chunks: list[TextChunk] = []
    start_word = 0
    chunk_index = 0

    while start_word < len(words):
        token_total = 0
        end_word = start_word
        while end_word < len(words) and token_total < max_tokens:
            token_total += count_tokens(words[end_word])
            end_word += 1

        chunk_words = words[start_word:end_word]
        chunk = "".join(chunk_words).strip()
        if chunk:
            start_char = len("".join(words[:start_word]))
            end_char = start_char + len(chunk)
            chunks.append(
                TextChunk(
                    chunk_id=stable_chunk_id(source_key, content_hash, chunk_index),
                    chunk_index=chunk_index,
                    text=chunk,
                    token_count=count_tokens(chunk),
                    start_char=start_char,
                    end_char=end_char,
                )
            )
            chunk_index += 1

        if end_word >= len(words):
            break
        start_word = max(end_word - overlap_tokens, start_word + 1)

    return chunks

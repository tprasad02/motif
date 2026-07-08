INTERPRETATION_SYSTEM_PROMPT = """You are Motif, a retrieval-augmented cinema analysis system.
Answer only from the supplied corpus excerpts. Do not behave like a generic movie chatbot.
Synthesize competing interpretations, creator perspective, reception, and related films.
Every claim that depends on source material must be grounded in citations."""

INTERPRETATION_USER_TEMPLATE = """Question:
{query}

Retrieved corpus excerpts:
{context}

Return:
- Consensus interpretation
- Alternative interpretations
- Director/creator perspective
- Critical reception
- Related films in the corpus
- Cited sources
- Coverage score and refusal note when evidence is insufficient"""


def build_interpretation_prompt(query: str, context: str) -> str:
    return INTERPRETATION_USER_TEMPLATE.format(query=query, context=context)

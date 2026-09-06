"""Generate and publish film-specific, evidence-gated Sentence-BERT lens profiles."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.film_config import FILM_TITLES
from app.models import GuidedAnswerRequest
from app.services.analysis import answer_guided
from app.services.recommendations import load_recommendation_chunks
from app.services.lens_vocabulary import lenses


ROLE_PRIORITY = {"screenplay", "scene_evidence", "formal_observation", "creator_commentary"}


def representative_chunks(film_slug: str, limit: int = 18) -> list[dict]:
    chunks = [chunk for chunk in load_recommendation_chunks() if chunk.get("film_slug") == film_slug]
    chunks.sort(
        key=lambda chunk: (
            chunk.get("source_role") in ROLE_PRIORITY,
            chunk.get("chunk_role") in ROLE_PRIORITY,
            chunk.get("quality_score") == "high",
        ),
        reverse=True,
    )
    selected = []
    seen_roles = set()
    for chunk in chunks:
        role = str(chunk.get("source_role", ""))
        if role and role not in seen_roles:
            selected.append(chunk)
            seen_roles.add(role)
    selected.extend(chunk for chunk in chunks if chunk not in selected)
    return selected[:limit]


def propose_lenses(client, model: str, film_slug: str, chunks: list[dict], candidate_limit: int) -> list[dict]:
    evidence = [
        {"chunk_id": chunk["chunk_id"], "source_role": chunk.get("source_role"), "chunk_role": chunk.get("chunk_role"), "text": chunk.get("text", "")[:700]}
        for chunk in chunks
    ]
    prompt = {
        "film": FILM_TITLES[film_slug],
        "task": "Propose distinct, concise film-specific angles that can sustain a close reading.",
        "rules": [
            "Use only the supplied evidence.",
            "Do not use generic labels such as Lens, Society, or Human Nature.",
            "An angle is supporting text under a one-word lens button, not a plot summary. Use 2 to 5 words; name an interpretive framing such as 'Performed selves' or 'Unreliable self-narration'. Do not use character names, film titles, scenes, objects, events, or exact plot mechanisms.",
            "Return 4 to 6 candidates. Each needs a one-sentence definition and at least three supporting chunk IDs.",
            "Use this exact JSON shape: {\"lenses\": [{\"angle\": \"...\", \"definition\": \"...\", \"supporting_chunk_ids\": [\"...\"]}]}.",
        ],
        "evidence": evidence,
    }
    result = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You create evidence-bound film close-reading lenses. Return valid JSON only."},
            {"role": "user", "content": json.dumps(prompt)},
        ],
        temperature=0.2,
    )
    payload = json.loads(result.choices[0].message.content or "{}")
    rows = payload.get("lenses", [])
    return [row for row in rows if isinstance(row, dict) and row.get("angle") and row.get("definition")][:candidate_limit]


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def semantic_evidence(candidate: dict, chunks: list[dict]) -> tuple[float, list[dict]]:
    query = f"{candidate['angle']}. {candidate['definition']}"
    vectors = embedding_model().encode([query, *[str(chunk.get("text", ""))[:900] for chunk in chunks]], normalize_embeddings=True)
    scored = sorted(((float(vectors[0] @ vector), chunk) for vector, chunk in zip(vectors[1:], chunks)), reverse=True, key=lambda item: item[0])
    eligible = [(score, chunk) for score, chunk in scored if score >= 0.18]
    supporting = []
    seen_roles = set()
    for _, chunk in eligible:
        role = str(chunk.get("source_role", ""))
        if role and role not in seen_roles:
            supporting.append(chunk)
            seen_roles.add(role)
    supporting.extend(chunk for _, chunk in eligible if chunk not in supporting)
    supporting = supporting[:8]
    semantic_score = sum(score for score, _ in scored[:3]) / min(3, len(scored)) if scored else 0.0
    return round(semantic_score, 4), supporting


def valid_angle(angle: str, film_slug: str) -> bool:
    words = angle.split()
    if not 2 <= len(words) <= 5:
        return False
    forbidden = {word.lower() for word in FILM_TITLES[film_slug].replace("-", " ").split()}
    forbidden.update({"scene", "sequence", "opening", "ending", "chronology", "photograph", "photographs", "tattoo", "tattoos"})
    return not any(word.strip(".,:;!?\u2019'").lower() in forbidden for word in words)


def map_to_lens(candidate: dict) -> tuple[dict | None, float, float]:
    vocabulary = lenses()
    if not vocabulary:
        return None, 0.0, 0.0
    query = f"{candidate['angle']}. {candidate['definition']}"
    vectors = embedding_model().encode([query, *[f"{lens['lens']}. {lens['definition']}" for lens in vocabulary]], normalize_embeddings=True)
    scores = sorted(((float(vectors[0] @ vector), lens) for vector, lens in zip(vectors[1:], vocabulary)), reverse=True, key=lambda item: item[0])
    best_score, best_lens = scores[0]
    margin = best_score - scores[1][0] if len(scores) > 1 else best_score
    return best_lens, round(best_score, 4), round(margin, 4)


def passes_evidence_gate(supporting: list[dict]) -> bool:
    roles = {str(chunk.get("source_role", "")) for chunk in supporting}
    preferred = [chunk for chunk in supporting if chunk.get("source_role") in ROLE_PRIORITY or chunk.get("chunk_role") in ROLE_PRIORITY]
    return len(supporting) >= 3 and len(roles) >= 2 and len(preferred) >= 2


def passes_answer_gate(client, model: str, film_slug: str, lens: str) -> tuple[bool, dict]:
    from evals.test_answer_quality import judge_passes_gate, judge_with_llm

    case = {"id": f"profile_{film_slug}", "mode": "analyze_film", "film_a": film_slug, "lens": lens}
    response = answer_guided(GuidedAnswerRequest(mode="analyze_film", film_a=film_slug, lens=lens, include_debug=True), allow_unpublished_lens=True)
    retrieved_ids = {chunk.chunk_id for chunk in response.debug_chunks}
    card_ids = []
    for card in response.evidence_cards:
        try:
            card_ids.extend(json.loads(card.get("chunk_ids") or "[]"))
        except json.JSONDecodeError:
            pass
    failures = {"overall": []}
    if len(response.evidence_cards) != 4:
        failures["overall"].append("four_card_contract_failed")
    if not card_ids or not set(card_ids).issubset(retrieved_ids):
        failures["overall"].append("evidence_link_contract_failed")
    try:
        judge = judge_with_llm(client, model, case, response)
    except Exception as error:
        return False, {"failures": failures, "judge_error": f"{type(error).__name__}: {error}"}
    passed = not response.refused and not any(failures.values()) and judge_passes_gate(judge) is True
    return passed, {"faithfulness": judge.faithfulness, "answer_relevance": judge.answer_relevance, "failures": failures}


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Build published Sentence-BERT lens profiles from film-specific evidence.")
    parser.add_argument("--film", action="append", choices=sorted(FILM_TITLES))
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--resume", action="store_true", help="Keep completed films in an existing output profile.")
    parser.add_argument("--force", action="store_true", help="Regenerate the requested film profiles even if they are already checkpointed.")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--output", default="backend/app/corpus/lens_profiles.json")
    args = parser.parse_args()
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required to generate and validate film-specific lenses.")
    client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
    output = Path(args.output)
    profiles = {"version": 2, "generated_at": datetime.now(timezone.utc).isoformat(), "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "films": {}}
    if args.resume and output.exists():
        try:
            profiles = json.loads(output.read_text(encoding="utf-8"))
            if profiles.get("version") != 2:
                profiles = {"version": 2, "generated_at": datetime.now(timezone.utc).isoformat(), "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "films": {}}
        except (OSError, json.JSONDecodeError):
            pass
    requested_films = args.film or sorted(FILM_TITLES)
    films = [film for film in requested_films if args.force or film not in profiles.get("films", {})]
    for film_slug in films:
        chunks = representative_chunks(film_slug)
        published = []
        diagnostics = []
        for candidate in propose_lenses(client, args.model, film_slug, chunks, args.candidate_limit):
            if not valid_angle(str(candidate["angle"]), film_slug):
                diagnostics.append({"angle": candidate["angle"], "status": "rejected", "reason": "invalid_angle"})
                continue
            lens, lens_similarity, lens_margin = map_to_lens(candidate)
            # Calibrated on the corpus vocabulary: MiniLM scores a concise angle
            # against an abstract lens lower than paraphrase pairs do.
            if not lens or lens_similarity < 0.22 or lens_margin < 0.05:
                diagnostics.append({"angle": candidate["angle"], "status": "rejected", "reason": "ambiguous_lens_mapping", "mapping_similarity": lens_similarity, "mapping_margin": lens_margin})
                continue
            semantic_score, supporting = semantic_evidence(candidate, chunks)
            if not passes_evidence_gate(supporting):
                diagnostics.append({"angle": candidate["angle"], "status": "rejected", "reason": "insufficient_semantic_evidence", "semantic_score": semantic_score, "support_count": len(supporting)})
                continue
            answer_passed, gate = passes_answer_gate(client, args.model, film_slug, str(lens["lens"]))
            if not answer_passed:
                diagnostics.append({"angle": candidate["angle"], "status": "rejected", "reason": "answer_gate_failed", "semantic_score": semantic_score, "answer_gate": gate})
                continue
            published.append({
                "lens_id": str(lens["id"]), "lens": str(lens["lens"]), "lens_definition": str(lens["definition"]),
                "angle": str(candidate["angle"]).strip(), "definition": str(candidate["definition"]).strip(),
                "mapping_similarity": lens_similarity, "mapping_margin": lens_margin,
                "semantic_score": semantic_score, "supporting_chunk_ids": [str(chunk["chunk_id"]) for chunk in supporting[:5]],
                "source_roles": sorted({str(chunk.get("source_role", "")) for chunk in supporting}), "answer_gate": gate, "status": "published",
            })
        profiles["films"][film_slug] = {"title": FILM_TITLES[film_slug], "lenses": sorted(published, key=lambda row: row["semantic_score"], reverse=True), "diagnostics": diagnostics}
        output.write_text(json.dumps(profiles, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{film_slug}: published={len(published)}", flush=True)
    print(f"profiles={output}")


if __name__ == "__main__":
    main()

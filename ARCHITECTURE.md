# Motif Architecture

Motif is a guided RAG application for film close reading. The architecture is designed around one question: can the app turn a user-selected film/theme path into a grounded, specific interpretation without exposing retrieval mechanics in the public UI?

## System Flow

```text
manual source collection
→ ingestion
→ cleaning
→ structure-aware chunking
→ metadata labeling
→ embeddings
→ PostgreSQL + Weaviate
→ button-driven user input
→ metadata-filtered retrieval
→ vector + BM25 search
→ merge + dedupe
→ reranking + source balancing
→ LLM evidence planning
→ structured frontend rendering
```

## Components

| Component | Role |
| --- | --- |
| `frontend/` | Next.js guided interface with Analyze, Compare, and Explore workflows. |
| `backend/` | FastAPI app, retrieval services, answer generation, recommendation endpoints. |
| `ingestion/` | Source loading, text extraction, cleaning, chunking, embedding, PostgreSQL/Weaviate writes. |
| `infra/` | PostgreSQL schema and local Docker infrastructure. |
| `backend/app/corpus/` | Checked-in JSONL runtime corpus for local fallback and deployment portability. |
| `evals/` | Corpus, chunk, retrieval, answer, and aggregate metrics scripts. |

## Data Stores

PostgreSQL stores the relational metadata:

- films
- sources
- documents
- chunks
- source quality
- source role
- chunk role
- lens tags

PostgreSQL also supports BM25-style full-text search through `websearch_to_tsquery`, `to_tsvector`, and `ts_rank_cd`.

Weaviate stores vectorized chunks for semantic retrieval. If Weaviate is unavailable, Motif can fall back to local JSONL corpus search for development and testing.

## Request Contract

The frontend does not send a vague open-ended prompt as the main interaction. It sends structured workflow fields:

```json
{
  "mode": "analyze_film",
  "film_a": "memento",
  "film_b": null,
  "lens": "Memory",
  "top_k": 12,
  "include_debug": false
}
```

The backend uses `mode`, `film_a`, `film_b`, and `lens` to control retrieval. This makes the system easier to test because intent is explicit.

## Retrieval

Motif retrieves candidates with two complementary methods.

Vector retrieval finds semantic matches. This helps when a source discusses a concept without using the exact UI lens word.

BM25 retrieval finds exact keyword matches. This helps when the user-selected lens maps to concrete words in criticism or screenplays, such as `memory`, `tattoo`, `photograph`, or `confession`.

The retrieval service retrieves up to 25 vector chunks and 25 BM25 chunks, merges them, deduplicates by chunk ID, and sends the merged set into reranking.

## Reranking

Reranking gives each candidate a new score based on:

- lexical overlap with the expanded query
- BM25 score
- vector score
- source quality
- source role
- chunk role
- lens/theme match
- penalties for front matter, references, navigation, or other junk

The reranker intentionally favors chunks that can support a close reading:

- `scene_evidence`
- `formal_observation`
- `creator_commentary`
- `interpretive_claim`

It penalizes `plot_summary` when plot summary would crowd out analysis.

## Comparison Balancing

Comparison mode has an additional failure mode: retrieval can accidentally pull strong evidence for only one film. Motif guards against that by checking film counts and supplementing underrepresented films before the final top chunks are returned.

The answer prompt also requires every evidence card to mention both films, so the output cannot silently become “two cards about one film and two cards about the other.”

## LLM Generation

The LLM does not see the whole corpus. It receives only the selected chunks and a strict output contract:

```text
thesis
Scene
Character
Pattern
Counterreading
```

The model must attach chunk IDs to each evidence card internally. Those chunk IDs are hidden in the public UI but visible in debug mode.

If the OpenAI key is missing or generation fails, Motif refuses instead of pasting retrieved chunks into the answer.

## Dynamic Recommendation Services

Motif includes backend recommendation endpoints:

- `GET /recommendations`
- `GET /recommendations/compare`
- `GET /recommendations/pairings`

These compute:

- film-specific supported lenses
- secondary angles extracted from corpus text
- comparison lens suggestions for two films
- suggested pairings after an Analyze Film reading

The public primary lens vocabulary remains controlled for UX stability. The film-specific ranking of those lenses is dynamic.

## Debug Mode

Debug mode is available at:

```text
http://localhost:3000/debug
http://localhost:3000/?debug=1
```

It shows retrieved chunks, source title, source role, chunk role, vector/BM25/rerank scores, selection reason, and evidence-card usage. This makes the backend accountable without turning the public UI into a research dashboard.

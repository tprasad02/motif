# Motif Dataset

Motif uses a curated film-analysis corpus rather than an open web crawl. The goal is not broad movie trivia coverage. The goal is to support close readings from sources that can actually explain artistic intent, reception, form, interpretation, and production context.

## Active Film Collection

The current corpus contains 18 films:

- The Shawshank Redemption
- Fight Club
- One Flew Over the Cuckoo's Nest
- Se7en
- The Silence of the Lambs
- The Prestige
- Memento
- Taxi Driver
- Shutter Island
- Black Swan
- The Sixth Sense
- Prisoners
- Gone Girl
- Requiem for a Dream
- Donnie Darko
- The Machinist
- Mulholland Drive
- The Truman Show

This is a fixed collection so retrieval, comparison, refusal behavior, and evaluation can be tested seriously.

## Source Strategy

Each film should ideally have a mix of:

- screenplays
- director interviews
- festival Q&As
- production notes or press kits
- academic papers
- educational essays
- video essay transcripts
- director commentary when legally available
- cast interviews
- cinematography or craft articles
- film history articles

The corpus favors high-signal sources over a larger pile of scraped fragments. A smaller set of strong sources is better for this project than noisy coverage from blogs, copied plot pages, and SEO summaries.

## Source Metadata

Source metadata lives in:

```text
data/manual_sources.csv
backend/app/corpus/sources.jsonl
```

Important fields:

| Field | Purpose |
| --- | --- |
| `film_slug` | Connects a source to one active film. |
| `source_key` | Stable source identifier. |
| `source_type` | Review, interview, academic, screenplay, production notes, etc. |
| `quality_score` | `high`, `medium`, or `low`; low-quality sources are excluded by default. |
| `source_role` | Internal role used for balancing and reranking. |
| `lens_tags` | Source-level theme hints. |
| `credibility_score` | Numeric source confidence used during corpus review. |

## Source Roles

Motif separates source type from source role. A `source_type` describes the file or publication type. A `source_role` describes how the source should function inside interpretation.

| Source role | Meaning |
| --- | --- |
| `creator_voice` | Director/cast interviews, festival Q&As, commentary-like material. |
| `criticism` | Reviews, essays, educational criticism, video essays. |
| `scholarship` | Academic or university/repository material. |
| `screenplay` | Script or screenplay evidence. |
| `production_context` | Press kits, production notes, craft/industry context. |

This helps retrieval avoid over-relying on one kind of material.

## Chunk Metadata

Chunks live in:

```text
backend/app/corpus/chunks.jsonl
```

Important fields:

| Field | Purpose |
| --- | --- |
| `chunk_id` | Stable identifier for retrieval and debug tracing. |
| `film_slug` | Film attached to the chunk. |
| `source_key` | Source attached to the chunk. |
| `text` | Cleaned chunk text. |
| `lens_tags` | Theme hints for retrieval. |
| `section_title` | Section or structural label when available. |
| `chunk_role` | How the chunk functions for analysis. |

Chunk roles include:

- `scene_evidence`
- `formal_observation`
- `creator_commentary`
- `interpretive_claim`
- `plot_summary`

The reranker prefers chunks that can support a concrete evidence card and penalizes plot summary when it crowds out interpretation.

## Lenses

The primary public lens vocabulary is controlled:

- Memory
- Identity
- Obsession
- Reality vs Illusion
- Control
- Freedom
- Isolation
- Guilt
- Performance
- Violence
- Justice
- Trauma

This part is intentionally curated. A stable lens vocabulary keeps the UI understandable and makes evaluation possible.

Film-specific lens support is dynamic. Motif scores lenses per film from:

- chunk lens tags
- raw chunk text
- source quality
- source role
- chunk role
- source diversity

Secondary angles are narrower concepts. Examples:

- Marriage
- Media
- Surveillance
- Doubles
- Masculinity
- Truth

These are discovered from corpus text with TF-IDF/ngram extraction, then filtered and mapped back to primary lenses when strongly supported. Known mappings still exist as guardrails so the app does not surface random names or noisy terms as user-facing angles.

## Quality Filtering

Low-quality sources are ignored by default. A source may be low quality if it is:

- scraped junk
- generic plot summary
- weak blog material
- mislabeled
- front matter or navigation-heavy
- not useful for interpretation

The system is designed to refuse weak paths rather than generate an overconfident reading from poor evidence.

## Rebuilding The Corpus

Run a full ingestion reset when manual source files change:

```bash
DATABASE_URL=postgresql://motif:motif@localhost:5433/motif \
WEAVIATE_URL=http://localhost:8080 \
python -m ingestion.cli ingest --sources data/manual_sources.csv --reset
```

Rebuild the checked-in JSONL runtime corpus:

```bash
python -m ingestion.build_backend_corpus \
  --sources data/manual_sources.csv \
  --output-dir backend/app/corpus
```

## Dataset Limitations

The corpus is only as strong as the source material available for each film. Some films have more creator commentary, scholarship, or formal analysis than others. Motif should be judged by whether it recognizes those limits, retrieves the best available evidence, and refuses unsupported readings when necessary.

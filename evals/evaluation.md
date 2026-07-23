# Motif Evaluation Plan

This folder evaluates Motif in four layers:

1. Corpus coverage
2. Chunk quality
3. Retrieval quality
4. Final answer quality

The layers are intentionally separate. A bad final answer can come from weak source coverage, bad chunking, poor retrieval, or weak generation. These scripts are designed to locate the failure point instead of treating the app as one black box.

## Setup

Install the evaluator-only dependencies before running LLM-judged evals:

```bash
pip install -r evals/requirements.txt
```

The deterministic checks can run without an OpenAI key. The LLM-judged chunk and answer evals require:

```env
OPENAI_API_KEY=your_key
```

## Layer 1: Corpus Coverage

Script:

```bash
python evals/verify_corpus.py --sources data/manual_sources.csv --min-per-film 4
```

Goal: decide whether each film has enough usable material to support real analysis.

Output columns:

```text
film
source_count
source_roles
source_role_count
source_type_diversity
local_file_exists_rate
chunk_count
avg_chunk_score
coverage_level
warnings
```

### Metrics

`source_count`

Number of source rows for the film in `data/manual_sources.csv`.

`source_roles`

Internal roles represented by the film's sources:

```text
creator_voice
criticism
scholarship
screenplay
production_context
```

`source_type_diversity`

Number of different source types represented, such as screenplay, interview, academic, production notes, educational essay, or craft article.

`local_file_exists_rate`

Percent of the film's source rows whose local files exist on disk.

`chunk_count`

Number of indexed chunks for that film in `backend/app/corpus/chunks.jsonl`.

`avg_chunk_score`

Average LLM chunk score for that film if a chunk eval report exists. Blank means no chunk-score report was available for that film's chunks.

`coverage_level`

High / medium / low estimate of whether the film has enough material for good answers.

### Coverage Level Meaning

High coverage means the film likely has enough material for strong readings:

- 6 or more sources
- several source roles
- several source types
- local files exist
- enough chunks
- chunk scores are good if available

Medium coverage means the film can probably support basic readings but has gaps.

Low coverage means the film is likely under-supported and may produce weak answers.

This is not an intellectual quality score for a source. It is a practical coverage score for the film.

## Layer 2: Chunk Quality

Script:

```bash
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl --limit 200 --model gpt-4.1-mini
```

Use this to decide whether chunking is good enough for retrieval.

### Chunk Eval Command Options

The first positional argument is the input JSONL file:

```bash
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl
```

Useful options:

```bash
--limit 200
```

Evaluate only the first N chunks. Use this for smoke tests before running a larger sample.

```bash
--skip-llm
```

Run only deterministic checks. This does not require `OPENAI_API_KEY`.

```bash
--model gpt-4.1-mini
```

Choose the OpenAI model used for LLM chunk judging.

```bash
--min-tokens 700 --max-tokens 900
```

Flag chunks outside a desired token range.

```bash
--output chunk_evaluation_results.json
```

Set the output filename. Reports are written under:

```text
evals/Reports/
```

```bash
--max-retries 2
```

Set retry count for each LLM judge call.

Examples:

```bash
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl --skip-llm --limit 20
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl --limit 200 --model gpt-4.1-mini
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl --min-tokens 700 --max-tokens 900 --skip-llm
```

### How Chunks Are Rated

The LLM score is about chunk usefulness as a retrieval unit, not final answer quality.

`5`

Excellent. The chunk is coherent, self-contained, focused, useful, and starts/ends naturally.

`4`

Good. Mostly self-contained and useful, with one minor issue.

`3`

Usable but flawed. It contains useful material but may need context, have weak boundaries, or cover too many topics.

`2`

Poor. Badly split, hard to understand, or strongly dependent on neighboring chunks.

`1`

Unusable. Empty, meaningless, boilerplate, severely incomplete, or not useful for retrieval.

### Chunk Metrics

`average_score`

Average LLM score across evaluated chunks.

`bad_chunk_rate`

Percent of chunks scoring 1 or 2.

`strong_chunk_rate`

Percent of chunks scoring 4 or 5.

`invalid_start_rate`

Percent of chunks that appear to start mid-sentence, with closing punctuation, or with continuation words.

`invalid_ending_rate`

Percent of chunks that appear to end unnaturally or with an incomplete trailing clause.

`average_adjacent_similarity`

Lexical similarity between adjacent chunks. Very high values can indicate too much overlap or duplicate chunking.

`average_tokens`

Average token count per chunk.

`boilerplate_or_reference_junk_rate`

Percent of chunks containing likely references, navigation, copyright, DOI, subscription, or other non-analysis junk.

`likely_plot_summary_rate`

Percent of chunks that look like plot summary instead of interpretive or formal analysis.

### Rechunking Decision Rules

Chunking is probably okay if:

- average score is above 4.0
- bad chunk rate is under 10%
- invalid start/end rates are low
- boilerplate/reference junk rate is low
- plot-summary rate is not dominating retrieval results

Rechunk if:

- many chunks score 1 or 2
- adjacent similarity is very high
- many chunks start mid-sentence
- chunks are mostly plot summary
- top retrieval results are intros/references instead of useful analysis

## Layer 3: Retrieval Quality

Script:

```bash
python evals/test_retrieval_quality.py
```

Goal: test whether retrieval pulls useful evidence before the LLM writes.

Benchmark cases live in:

```text
evals/benchmark_cases.json
```

### Retrieval Metrics

`film_match_rate`

For Analyze and Compare, the percent of top chunks from the expected film or films.

For Theme, the percent of chunks from films allowed by the curated theme map.

`theme_match_rate`

Percent of chunks that appear connected to the selected theme, either through lens tags or text overlap.

`concrete_evidence_rate`

Percent of chunks with useful roles such as:

```text
scene_evidence
formal_observation
creator_commentary
interpretive_claim
```

`plot_summary_rate`

Percent of chunks marked as plot summary.

`source_diversity`

Number of distinct sources represented in the retrieved chunks.

`source_role_diversity`

Number of source roles represented.

`comparison_balance_pass`

For comparison cases, requires both films to appear substantially in retrieved chunks.

### Retrieval Pass Rules

Analyze Film:

- at least 8 of top 12 chunks should be from the selected film

Compare Films:

- at least 4 chunks from Film A
- at least 4 chunks from Film B

Theme:

- returned films should be allowed by the curated theme map

General:

- at least 6 of top 12 chunks should match the theme
- plot-summary chunks should be 40% or less
- at least 2 source roles should appear when available

## Layer 4: Final Answer Quality

Script:

```bash
python evals/test_answer_quality.py
```

This calls the real `/answer` pipeline internally and evaluates the final app output.

If no API key is available, run deterministic checks only:

```bash
python evals/test_answer_quality.py --skip-llm
```

With LLM judging:

```bash
OPENAI_API_KEY=your_key python evals/test_answer_quality.py --model gpt-4.1-mini
```

### Answer Dimensions

The LLM judge scores each dimension from 1 to 5:

`thesis_specificity`

Does the thesis name the film and make a specific claim, instead of a broad theme statement?

`evidence_distinctness`

Are the four evidence cards actually different from each other?

`concrete_film_detail`

Does each card mention something visible or audible: scene, image, cut, sound, prop, performance, setting, structure?

`non_dumping`

Does the answer explain evidence instead of directly dumping screenplay or source text?

`anti_plot_summary`

Does the answer avoid retelling the plot?

`anti_generic_language`

Does the answer avoid vague phrases like "complex exploration," "the human condition," or "at its core"?

`groundedness_to_chunks`

Are the claims supported by the retrieved chunks?

`film_lens_relevance`

Does the answer stay focused on the selected film and selected theme?

`unsupported_claim_risk`

High score means low risk of claims unsupported by retrieved evidence.

`overall_reading_depth`

Does the answer feel like a thoughtful close reading rather than a search summary?

### Final Answer Pass Rule

```text
answer_quality_score = average of the 10 dimensions
pass if score >= 4.0 and no critical failures
```

Critical failures:

- fewer than four evidence cards
- answer discusses the wrong film
- answer ignores the selected theme
- answer invents unsupported claims
- answer dumps raw source or screenplay text
- comparison mode retrieves heavily from only one film
- source/system-facing language appears in the public answer

## Theme Mode Eval

Theme mode is evaluated separately because it returns ranked film cards, not an essay.

For each theme, the answer-quality script checks:

- only active 18 corpus films appear
- returned films are allowed by the curated theme map
- each card has title/year/director
- each card has one-line non-spoiler theme relevance
- summaries are not repeated
- summaries are not huge chunks
- no source/system-facing language appears

Theme mode passes if:

- 100% returned films are in corpus
- 100% returned films are allowed for that theme
- 0 repeated summaries
- 0 source/system phrases

## Recommended Run Order

Run the layers in this order:

```bash
python evals/verify_corpus.py --sources data/manual_sources.csv --min-per-film 4
python evals/chunk_eval.py backend/app/corpus/chunks.jsonl --limit 200 --model gpt-4.1-mini
python evals/test_retrieval_quality.py
python evals/test_answer_quality.py --model gpt-4.1-mini
```

If the final answer eval fails, inspect earlier layers before changing prompts:

- low corpus coverage means gather better sources
- low chunk scores mean rechunk or clean documents
- weak retrieval means fix metadata, lens tags, chunk roles, or reranking
- good retrieval but bad answers means fix prompting or answer planning

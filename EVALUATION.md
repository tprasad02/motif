# Motif Evaluation

Motif is evaluated as a retrieval-augmented product. The evaluation goal is to answer: did the system retrieve the right evidence, and did the final answer use that evidence to produce a specific close reading?

The eval stack is layered because a bad answer can come from several different places:

```text
weak corpus coverage
→ poor chunk boundaries
→ bad retrieval
→ bad reranking
→ weak LLM generation
→ unclear frontend rendering
```

## Benchmark Cases

Benchmark cases live in:

```text
evals/benchmark_cases.json
```

Current suite:

| Workflow | Cases |
| --- | ---: |
| Analyze a Film | 24 |
| Compare Films | 64 |
| Explore a Theme | 12 |
| Total | 100 |


## Layer 1: Corpus Coverage

Script:

```bash
python -m evals.verify_corpus --sources data/manual_sources.csv --min-per-film 4
```

Purpose: check whether each film has enough usable material.

Metrics:

- source count per film
- source role diversity
- source type diversity
- local file exists rate
- chunk count per film
- average chunk score when chunk eval reports exist
- coverage level: high / medium / low
- warnings

This helps distinguish “retrieval failed” from “the corpus is thin.”

## Layer 2: Chunk Quality

Script:

```bash
python -m evals.chunk_eval backend/app/corpus/chunks.jsonl --limit 200 --model gpt-4.1-mini
```

Purpose: evaluate whether chunks are good retrieval units.

Chunk score meaning:

| Score | Meaning |
| ---: | --- |
| 5 | Excellent: coherent, focused, self-contained, useful. |
| 4 | Good: useful with a minor boundary/context issue. |
| 3 | Usable but flawed: may need context or cover too many ideas. |
| 2 | Poor: badly split or hard to understand. |
| 1 | Unusable: empty, boilerplate, cut off, or not useful. |

Chunk metrics:

- average chunk score
- bad chunk rate
- strong chunk rate
- invalid start/end rates
- adjacent similarity
- average tokens
- boilerplate/reference junk rate
- likely plot-summary rate

This score is not final answer quality. It only asks whether a chunk is useful for retrieval.

## Layer 3: Retrieval Quality

Script:

```bash
python -m evals.test_retrieval_quality
```

Purpose: check whether retrieval returns useful evidence before the LLM writes.

This layer reports one `retrieval_guardrails_pass` result for each case. It
combines the product requirements that ranked-retrieval metrics cannot express:
correct film scope, text-level lens connection, evidence quality rather than
plot recap, source diversity, comparison coverage, and no excessive duplicates.

The component values remain in the per-case diagnostic artifact so a failed
guardrail can be fixed, but they are not headline metrics.

Pass rules:

- Analyze Film: at least 8 of 12 chunks should come from the selected film.
- Compare Films: at least 4 chunks should come from each film.
- Lens match: at least 6 of 12 chunks should connect to the selected lens.
- Lens relevance is checked against chunk text, not `lens_tags`, so ranker metadata cannot certify itself.
- At least half of retrieved chunks must be concrete evidence; at least three sources must be represented; and retrieval must return the requested number of chunks with no system-facing text or excessive near-duplicates.
- Plot-summary chunks should stay under 40%.
- At least two source roles should appear when available.

## Layer 4: Judgment-Backed Ranking Quality

Script:

```bash
python -m evals.rag_metrics
```

The benchmark cases in `evals/benchmark_cases.json` are assessed against
independent chunk judgments in `evals/relevance_judgments.csv`. Each candidate
chunk receives a relevance grade: 3 = essential evidence, 2 = strong support,
1 = relevant but peripheral, and 0 = not useful.

This is the retrieval-quality measurement layer.

| Metric | Meaning |
| --- | --- |
| `Precision@k` | Share of assessed retrieved chunks that are relevant. |
| `Recall@k` | Share of all judged relevant evidence included in the context. |
| `MRR` | Rank quality of the first relevant chunk. |
| `nDCG@k` | Graded ranking quality; rewards essential evidence near the top. |
| `judgment_coverage_at_k` | Validity check: share of retrieved chunks that have been assessed. |

These are the four canonical retrieval metrics.

## Layer 5: Answer Quality

Script:

```bash
python -m evals.test_answer_quality
```

Purpose: call the real `/answer` pipeline and evaluate the final app output.

The LLM judge uses two canonical RAG answer metrics:

- `faithfulness`: every substantive thesis/card claim is assessed only against
  retrieved evidence excerpts; each card must carry valid supporting chunk IDs.
  The judge may not use outside film knowledge.
- `answer_relevance`: assessed from the benchmark request and public answer,
  rather than retrieved chunks, to ensure the answer responds to the selected
  film(s) and lens.

They are evaluated in separate judge calls. This prevents retrieval context
from making an off-target answer appear relevant, while preventing external
film knowledge from making an unsupported answer appear faithful.

Both must score at least 4/5. Format, source dumping, generic phrasing, card
specificity, and comparison integration are deterministic validity checks—not
additional subjective judge metrics. Theme mode remains deterministically
evaluated because it returns ranked film cards rather than an evidence-board
reading.

Critical failures:

- fewer than four evidence cards
- wrong film discussed
- selected lens ignored
- unsupported claims
- raw source or screenplay dumping
- comparison only discusses one film
- comparison cards do not mention both films

Theme mode is evaluated separately because it returns ranked film cards rather than an evidence-board reading.

## Aggregate Metrics

Script:

```bash
python -m evals.run_evaluation --trials 3 --latency-case-limit 5
```

Outputs:

```text
evals/Reports/corpus_coverage.csv
evals/Reports/retrieval_quality_results.json
evals/Reports/rag_ranking_metrics.json
evals/Reports/answer_quality_results.json
evals/final_metrics/metrics_summary.json
evals/final_metrics/metrics_trials.csv
evals/final_metrics/metrics_case_summary.csv
evals/final_metrics/evaluation_manifest.json
```

`run_evaluation.py` runs a representative chunk-quality sample, corpus coverage, the benchmark and supported-pair retrieval guardrails, judgment-backed ranking, answer evaluation, and aggregation in one run. It stops at a failed layer, so an attractive answer score cannot conceal missing corpus coverage or unassessed retrieval quality.

| Metric | Value |
| --- | ---: |
| Films | 18 |
| Documents | 140 |
| Chunks | 2,427 |
| Benchmark cases | 50 (pre-expansion) |
| Retrieval trials | 150 (pre-expansion) |
| Retrieval guardrails | 100.0% (pre-expansion) |
| Judgment-backed ranking metrics | Not yet assessed |
| Answer checked cases | 50 |
| Answer validity / quality | Legacy — regenerate |
| LLM-judged answer cases | 41 |
| Faithfulness / answer relevance | Legacy — regenerate |
| Average response latency | 12.486s |

Latency is measured on a bounded sample of 5 benchmark cases x 3 OpenAI-backed trials. The full 100-case x 3 latency run is supported but intentionally not used for routine checks because it requires 300 paid generations.

## Running and Diagnosing the Suite

Install evaluator dependencies before LLM-judged checks:

```bash
pip install -r evals/requirements.txt
```

`OPENAI_API_KEY` is required for chunk and answer judging. The suite’s
offline-only options, `--skip-chunk-judge` and `--skip-answer-judge`, are
recorded in the run manifest and must not be used for a headline quality claim.

Run individual layers only when diagnosing a failure:

```bash
python -m evals.verify_corpus --sources data/manual_sources.csv --min-per-film 4
python -m evals.chunk_eval backend/app/corpus/chunks.jsonl --limit 200 --model gpt-4.1-mini
python -m evals.test_retrieval_quality
python -m evals.test_supported_retrieval_sweep --scope primary
python -m evals.test_supported_retrieval_sweep --scope secondary
python -m evals.rag_metrics
python -m evals.test_answer_quality --model gpt-4.1-mini
```

Useful chunk-evaluation options are `--skip-llm` for deterministic smoke
checks, `--min-tokens` and `--max-tokens` for chunk-size constraints, and
`--limit` for sampling. The supported-pair sweep has `primary`, `secondary`,
and `all` scopes; `primary` is the selectable product surface and `secondary`
is diagnostic coverage for expansion logic.

The answer evaluator measures first-pass output by default. Its optional
`--retry-card-failures` flag performs one diagnostic retry after deterministic
card failures, but never changes the first-pass result. Theme mode is checked
deterministically for active-corpus membership, enough unique film cards,
non-repeated non-spoiler summaries, appropriate summary length, and no
source-facing language.

When a run fails, investigate in this order:

1. Low corpus coverage: acquire or repair source material.
2. Weak chunk quality: clean documents or rechunk.
3. Guardrail or ranking failure: inspect retrieval, metadata, and reranking.
4. Good retrieval but weak faithfulness/relevance: revise answer planning or prompts.

## What Failed And Improved

Earlier failures:

- Answers sometimes looked like pasted chunks.
- The model produced generic essay language instead of concrete film analysis.
- Comparison mode sometimes retrieved heavily from one film and barely from the other.
- Weak source material could dominate retrieval.
- Frontend source trails exposed too much backend language to users.

Improvements:

- Changed output from essay-style prose to thesis + four evidence cards.
- Added chunk roles and source roles.
- Added source quality filtering.
- Added hybrid retrieval with vector search and BM25.
- Added reranking with quality, role, lens, and junk penalties.
- Added comparison balancing and compare-prompt constraints.
- Added theme-mode restrictions to the active film collection.
- Added refusal behavior for weak paths.
- Added hidden debug mode for accountability.
- Added clean metrics artifacts for portfolio review.

## How To Use The Eval Results

Use retrieval results when a path pulls weak or irrelevant chunks. Do not treat metadata-only lens matches as evidence of relevance.

Use answer-quality results when retrieval is good but the final writing is vague, unsupported, or too plot-heavy.

Use chunk evals when top retrieval results contain boilerplate, references, chopped paragraphs, or repeated plot summaries.

Use corpus coverage when a film simply lacks enough strong sources.

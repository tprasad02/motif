# Motif Evaluation

Motif is evaluated as a retrieval-augmented product. The evaluation goal is to answer: did the system retrieve the right evidence, and did the final answer use that evidence to produce a specific close reading?

The eval stack is intentionally layered because a bad answer can come from several different places:

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
| Analyze a Film | 12 |
| Compare Films | 30 |
| Explore a Theme | 8 |
| Total | 50 |

The comparison set is deliberately larger because comparison mode was the most failure-prone workflow. Earlier versions sometimes retrieved enough material for only one film, or produced cards that divided the two films instead of comparing them directly.

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

Metrics:

| Metric | Meaning |
| --- | --- |
| `film_match_rate` | Percent of top chunks from the selected film(s). |
| `theme_match_rate` / `lens_match_rate` | Percent of chunks connected to the selected lens. |
| `concrete_evidence_rate` | Percent of chunks with useful roles such as scene evidence or formal observation. |
| `plot_summary_rate` | Percent of chunks marked as plot summary. |
| `source_diversity` | Number of distinct sources represented. |
| `source_role_diversity` | Number of source roles represented. |
| `comparison_balance_pass` | Whether comparison retrieval included enough chunks from both films. |

Pass rules:

- Analyze Film: at least 8 of 12 chunks should come from the selected film.
- Compare Films: at least 4 chunks should come from each film.
- Lens match: at least 6 of 12 chunks should connect to the selected lens.
- Plot-summary chunks should stay under 40%.
- At least two source roles should appear when available.

## Layer 4: Answer Quality

Script:

```bash
python -m evals.test_answer_quality
```

Purpose: call the real `/answer` pipeline and evaluate the final app output.

Answer dimensions:

- thesis specificity
- evidence distinctness
- concrete film detail
- non-dumping
- anti-plot-summary behavior
- anti-generic language
- groundedness to chunks
- film/lens relevance
- unsupported-claim risk
- overall reading depth

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
python -m evals.build_metrics_summary --trials 3 --latency-case-limit 5
```

Outputs:

```text
evals/Reports/metrics_summary.json
evals/Reports/metrics_trials.csv
evals/Reports/metrics_case_summary.csv
```

The metrics artifacts intentionally avoid answer text, retrieved text, and long source excerpts. They are meant to be clean measurement files, not another debug dump.

Current snapshot:

| Metric | Value |
| --- | ---: |
| Films | 18 |
| Documents | 140 |
| Chunks | 2,427 |
| Benchmark cases | 50 |
| Retrieval trials | 150 |
| Film retrieval accuracy | 1.000 |
| Lens retrieval accuracy | 0.965 |
| Comparison balance | 100.0% |
| Retrieval pass rate | 100.0% |
| Answer checked cases | 50 |
| Answer pass rate | 100.0% |
| LLM-judged answer cases | 41 |
| Average answer quality | 4.854 / 5 |
| Average response latency | 12.486s |

Latency is measured on a bounded sample of 5 benchmark cases x 3 OpenAI-backed trials. The full 50-case x 3 latency run is supported but intentionally not used for routine checks because it requires 150 paid generations.

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

Use retrieval results when a path pulls weak or irrelevant chunks.

Use answer-quality results when retrieval is good but the final writing is vague, unsupported, or too plot-heavy.

Use chunk evals when top retrieval results contain boilerplate, references, chopped paragraphs, or repeated plot summaries.

Use corpus coverage when a film simply lacks enough strong sources.

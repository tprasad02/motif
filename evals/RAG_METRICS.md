# Judgment-Backed RAG Metrics

`test_retrieval_quality.py` is a useful guardrail, but its scope, lens-term,
role, diversity, and duplication checks are not retrieval relevance metrics.
Use `rag_metrics.py` after human assessment to make retrieval changes
measurable.

## Annotation protocol

Generate a candidate pool (use a larger pool than the serving `top_k`):

```bash
python -m evals.rag_metrics --write-annotation-pool evals/Reports/relevance_pool.csv --pool-k 30
```

Copy reviewed rows into `evals/relevance_judgments.csv`. For every benchmark
case, independently grade each candidate chunk:

| Grade | Meaning |
| ---: | --- |
| 3 | Essential, direct evidence for the requested film/lens reading. |
| 2 | Strong supporting evidence. |
| 1 | Relevant but peripheral or weak. |
| 0 | Irrelevant, misleading, duplicate, or unusable. |

Annotate the union of candidates returned by each retriever/configuration being
compared; otherwise an improved retriever can retrieve an unjudged good chunk
and receive no credit. Two reviewers should independently label an overlap of
at least 20% of the pool, reconcile differences, and record agreement (for
example weighted Cohen's kappa) in the evaluation report.

## Run and interpret

```bash
python -m evals.rag_metrics
```

The evaluator writes per-case and aggregate results to `evals/Reports/`.

- `Recall@k`: how much of the known useful evidence made the context window.
- `Precision@k`: how much judged context is useful. It is shown with judgment
  coverage, rather than quietly treating unjudged chunks as irrelevant.
- `MRR`: position of the first useful chunk; sensitive to rank-one failures.
- `nDCG@k`: ranking quality using the 0–3 grades, rewarding essential evidence
  near the top.

Treat `judgment_coverage_at_k` as a validity gate. Expand the pool before
trusting a regression conclusion if it is materially below 1.0.

Hit Rate is omitted because it is already represented by MRR: no relevant chunk
means MRR is zero. MAP is omitted because nDCG captures graded evidence quality
and rank position without duplicating the same headline story.

## Scope

The current suite intentionally stops at the four retrieval metrics above plus
faithfulness and answer relevance for generation. Claim-level citation metrics
would require the product to emit claim-to-chunk citations first; until that
instrumentation exists, reporting them would create another incomplete and
potentially misleading score.

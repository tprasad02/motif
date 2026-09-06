# Motif Limitations

Motif is intentionally narrow. It is not trying to be a universal film chatbot, a general movie database, or a replacement for full scholarly research.

## Scope Limits

Motif is strongest on:

- the active 18-film corpus
- supported film/lens combinations
- close-reading questions that can be grounded in the curated sources
- comparison questions where both films have enough evidence under the selected lens

Motif is weaker on:

- arbitrary films outside the collection
- questions requiring sources that were not ingested
- very narrow production-history claims without source coverage
- broad claims about all cinema
- speculative interpretation with no retrieved support

## Corpus Limits

The corpus is curated manually. This improves quality but also means coverage is uneven. Some films have stronger academic or creator-interview coverage than others.

Source availability also varies by film. A film with strong screenplay access, director interviews, and scholarship will usually support better answers than a film with mostly reviews or limited craft discussion.

## Lens Limits

The primary lens vocabulary is controlled so the app can be tested and the UI stays coherent. This means Motif will not expose every possible lens a user might imagine.

Secondary angles are discovered from corpus text and filtered back to supported primary lenses, but they are still limited by the terms and arguments present in the source material.

## Retrieval Limits

Hybrid retrieval improves coverage, but it does not guarantee perfect evidence. Common failure modes include:

- exact keyword matches that retrieve boilerplate
- semantic matches that are relevant but too broad
- source imbalance
- chunks that need more surrounding context
- plot summary competing with interpretation

Debug mode exists so these issues can be inspected instead of hidden.

## Generation Limits

The LLM writes from retrieved chunks. It can still:

- phrase something awkwardly
- overgeneralize
- miss a better interpretation
- fail to attach the best chunk ID
- produce a weaker card on one run and a stronger card on another

The app uses structured prompts, retry logic, refusal behavior, and answer-quality evaluation to reduce these problems, not pretend they do not exist.

## Evaluation Limits

The benchmark suite is not every possible film/lens/pairing combination. It focuses on:

- representative Analyze Film paths
- a larger set of comparison paths
- the main lens exploration paths
- cases that previously exposed retrieval or generation failures

The supported-lens sweeps test more film/lens coverage, but they are still limited to supported combinations.

## Product Limits

Motif hides citations and source labels from the normal user interface to preserve a clean reading experience. This is a product choice, not a lack of traceability. Debug mode exposes the retrieval path for development and review.

## Deployment Limits

The deployed app requires a working backend, database/vector configuration, and `OPENAI_API_KEY`. If the key is missing or generation fails, Motif should refuse instead of presenting retrieved chunks as an answer.

## Future Improvements

Useful next improvements:

- stronger semantic concept extraction with sentence-transformers, KeyBERT, or BERTopic
- open-ended question answering capabilities instead of button-only workflow
- more source coverage for weaker films
- better structure-aware chunking for long academic PDFs
- persistent retrieval comparison UI in debug mode
- fuller latency and cost tracking
- human review notes for benchmark cases
- observability for deployed retrieval/generation failures

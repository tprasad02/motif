# Chunk Evaluation Script

This script evaluates chunks stored in a JSONL file using:

1. Deterministic checks, such as token count and boundary heuristics.
2. An optional OpenAI model that assigns:

   * an overall score from 1 to 5
   * a short reason for the score
   * a short suggestion for improving the chunk

The evaluator does not test vector retrieval or final answer generation. It evaluates the quality of the generated chunks themselves.

---

TL;DR
try `python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 10` from project root

---
## Project structure

The examples in this README assume the following Motif project structure:

```text
motif/
├── .venv/
├── backend/
│   └── app/
│       ├── models.py
│       └── corpus/
│           └── chunks.jsonl
└── evals/
    ├── chunk_eval.py
    └── reports/
        └── chunks_evaluation.json
```

The `reports` directory is created automatically if it does not already exist.

---

## Input format

The input file must use JSON Lines format.

Each line must contain one JSON object with:

* `chunk_id`: a unique identifier for the chunk
* `text`: the chunk content

Example `chunks.jsonl`:

```json
{"chunk_id": "b934539726424a99c670791bae313308", "text": "The hotel functions as a psychological maze."}
{"chunk_id": "c145640837535b00d781802cbf424419", "text": "Jack's isolation gradually changes his relationship with his family."}
{"chunk_id": "d256751948646c11e892913dc053520", "text": "The final chase externalizes the conflict established earlier in the film."}
```

Important requirements:

* Each chunk must appear on one line.
* Each `chunk_id` must be unique.
* Blank lines are ignored.
* Every nonblank line must contain valid JSON.
* The `text` field cannot be empty.

---

## Installation

Create and activate your Python virtual environment before installing dependencies.

Install the required packages:

```bash
pip install openai python-dotenv pydantic tiktoken
```

The script is intended for Python 3.10 or newer.

To activate the backend virtual environment on Windows:

```bat
backend\.venv\Scripts\activate
```

You can also run the script directly with the virtual environment’s Python executable:

```bat
backend\.venv\Scripts\python.exe evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

---

## Environment variables

Create a `.env` file in the Motif project root or another location that `python-dotenv` can discover.

Example:

```dotenv
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

### `OPENAI_API_KEY`

Your OpenAI API key.

This variable is required unless you use the `--skip-llm` option.

Do not commit your `.env` file to Git.

Add this to `.gitignore`:

```gitignore
.env
evals/reports/
```

### `OPENAI_MODEL`

The OpenAI model used to evaluate each chunk.

A reasonable default is:

```dotenv
OPENAI_MODEL=gpt-4.1-mini
```

The model can also be supplied with the `--model` command-line option. A model passed through the command line overrides the model in `.env`.

Example alternatives:

```dotenv
# Higher-quality evaluation
OPENAI_MODEL=gpt-4.1

# Lower-cost and faster evaluation
OPENAI_MODEL=gpt-4.1-nano

# Stronger reasoning, generally slower and more expensive
OPENAI_MODEL=o4-mini

# Strong reasoning model
OPENAI_MODEL=o3

# Older general-purpose model
OPENAI_MODEL=gpt-4o

# Lower-cost GPT-4o model
OPENAI_MODEL=gpt-4o-mini
```

Model access may differ between OpenAI projects and API accounts. Use a model available to the API key stored in your `.env` file.

---

## Basic usage

Run all commands from the Motif project root:

```bat
cd C:\Users\grape\Documents\motif
```

Run the complete evaluation:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

This performs:

* deterministic evaluation
* OpenAI LLM evaluation

The default output is written to:

```text
evals/reports/chunks_evaluation.json
```

The location is based on the location of `chunk_eval.py`, not the current working directory.

---

# Command-line options

## Input file

The first positional argument is the path to the JSONL file.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

You can also provide an absolute path:

```bat
python evals\chunk_eval.py "C:\Users\grape\Documents\motif\backend\app\corpus\chunks.jsonl"
```

For paths containing spaces, use quotation marks.

The input file must contain one chunk object per line.

---

## `--output`

Set the output filename.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --output test.json
```

The output file is always saved inside:

```text
evals/reports/
```

Therefore, the command above creates:

```text
evals/reports/test.json
```

Only the filename portion is used.

For example:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --output results\test.json
```

still creates:

```text
evals/reports/test.json
```

because the script uses:

```python
arguments.output.name
```

When `--output` is omitted, the script creates the filename from the input file stem.

For example:

```text
backend/app/corpus/chunks.jsonl
```

produces:

```text
evals/reports/chunks_evaluation.json
```

The output contains:

* input-file information
* evaluation time
* configured token limits
* aggregate summary
* individual chunk results
* deterministic measurements
* OpenAI score, reason, and suggestion
* any error returned while evaluating a chunk

---

## `--min-tokens`

Set the minimum desired token count for each chunk.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --min-tokens 100
```

A chunk containing fewer than 100 tokens will have:

```json
"below_min_tokens": true
```

This option does not modify, remove, or reject the chunk. It only marks the chunk in the evaluation output.

Use this option when your chunking strategy is expected to produce chunks above a particular size.

---

## `--max-tokens`

Set the maximum desired token count for each chunk.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --max-tokens 600
```

A chunk containing more than 600 tokens will have:

```json
"above_max_tokens": true
```

This option does not truncate the chunk. It only records that the chunk exceeds the expected maximum.

---

## Using token limits together

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --min-tokens 100 --max-tokens 600
```

This evaluates whether every chunk falls within the expected range of 100 to 600 tokens.

The summary includes:

* below-minimum token rate
* above-maximum token rate
* average token count
* median token count
* minimum token count
* maximum token count
* token-count standard deviation

The script rejects invalid ranges such as:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --min-tokens 700 --max-tokens 600
```

because the minimum cannot be greater than the maximum.

---

## `--limit`

Evaluate only the first specified number of chunks.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 5
```

This evaluates only the first five nonblank JSONL records.

This option is useful for:

* confirming that the script works
* testing your `.env` configuration
* inspecting the output format
* estimating API usage before evaluating the complete file
* debugging model or prompt changes

Example:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 10
```

The limit is applied after the input file has been loaded and validated.

---

## `--skip-llm`

Run only the deterministic evaluation and make no OpenAI API requests.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --skip-llm
```

This mode does not require `OPENAI_API_KEY`.

It still calculates:

* character count
* word count
* token count
* whether the chunk starts with lowercase text
* whether the chunk begins with a continuation word
* whether the chunk begins with closing punctuation
* whether the chunk ends with terminal punctuation
* whether the chunk appears to end with an incomplete clause
* lexical similarity with neighboring chunks
* minimum-token violations
* maximum-token violations
* whether the chunk is nearly empty

The LLM result for every chunk will be:

```json
"llm": null
```

Use this option when:

* testing input loading
* checking chunk sizes
* debugging deterministic logic
* avoiding API cost
* confirming that the script runs before enabling OpenAI evaluation

---

## `--model`

Override the model configured in `.env`.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1-mini
```

Other examples:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1
```

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1-nano
```

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model o4-mini
```

The command-line model takes priority over `OPENAI_MODEL`.

For example, given:

```dotenv
OPENAI_MODEL=gpt-4.1-mini
```

this command still uses `gpt-4.1`:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1
```

---

## `--max-retries`

Control how many times the script retries a failed OpenAI request.

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --max-retries 2
```

Default:

```text
2
```

The total possible number of attempts is:

```text
1 initial attempt + maximum retries
```

Therefore:

```text
--max-retries 2
```

allows up to three total attempts.

The script uses increasing delays between retries.

Use a larger value for temporary network or rate-limit problems:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --max-retries 4
```

Disable retries:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --max-retries 0
```

If all attempts fail, the error is stored in the affected chunk result and the script continues evaluating later chunks.

---

# Combined examples

## Evaluate the complete file

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

## Evaluate with expected token limits

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --min-tokens 100 --max-tokens 600
```

## Test the first five chunks

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 5
```

## Test five chunks with token limits

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 5 --min-tokens 100 --max-tokens 600
```

## Run without OpenAI API calls

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --skip-llm
```

## Use a specific OpenAI model

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1
```

## Choose an output filename

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --output gpt-4.1-results.json
```

This creates:

```text
evals/reports/gpt-4.1-results.json
```

## Use a model, token limits, and a chunk limit

Windows Command Prompt:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl ^
  --model gpt-4.1-mini ^
  --min-tokens 100 ^
  --max-tokens 600 ^
  --limit 20 ^
  --output test-run.json
```

PowerShell:

```powershell
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl `
  --model gpt-4.1-mini `
  --min-tokens 100 `
  --max-tokens 600 `
  --limit 20 `
  --output test-run.json
```

Both commands create:

```text
evals/reports/test-run.json
```

---

# Understanding the OpenAI result

Each successfully evaluated chunk contains an LLM result similar to:

```json
{
  "score": 3,
  "reason": "The chunk is coherent but depends on context from the previous chunk.",
  "suggestion": "Include the missing subject or merge it with the previous chunk."
}
```

## `score`

The overall chunk-quality score.

### Score 5

The chunk is:

* coherent
* self-contained
* focused
* naturally bounded
* useful as an independent retrieval unit

### Score 4

The chunk is strong but has a minor issue.

Examples:

* a slightly unclear pronoun
* a minor transition problem
* a small amount of unnecessary content

### Score 3

The chunk is usable but has a meaningful issue.

Examples:

* missing context
* a weak start or ending
* multiple loosely connected topics
* unclear references

### Score 2

The chunk is poor.

Examples:

* strongly depends on neighboring chunks
* is badly split
* is difficult to understand
* starts or ends in the middle of an important idea

### Score 1

The chunk is unusable.

Examples:

* empty or nearly empty content
* meaningless text
* severe incompleteness
* metadata or formatting without useful information

## `reason`

One short sentence explaining the main reason for the score.

Example:

```json
"reason": "The chunk starts with an unexplained pronoun and requires the previous chunk."
```

## `suggestion`

One short actionable recommendation.

Example:

```json
"suggestion": "Merge the chunk with the previous section or repeat the missing subject."
```

---

# Understanding deterministic results

## `character_count`

The number of characters in the chunk.

## `word_count`

The number of normalized words detected in the chunk.

## `token_count`

The estimated number of tokens used by the selected model tokenizer.

Token count is usually more relevant than character or word count when the chunking configuration is based on model tokens.

## `starts_with_lowercase`

`true` when the first alphabetic character is lowercase.

This may indicate that the chunk starts in the middle of a sentence. However, lowercase starts may also be valid in some formatting situations.

## `starts_with_continuation_word`

`true` when the first word is a continuation word such as:

```text
and
but
however
therefore
which
this
they
```

This may indicate that the chunk depends on preceding context.

It is a heuristic and should not automatically be treated as an error.

## `starts_with_closing_punctuation`

`true` when the chunk begins with punctuation such as:

```text
,
;
:
)
]
}
```

This often indicates a poor chunk boundary.

## `ends_with_terminal_punctuation`

`true` when the chunk ends with punctuation commonly associated with a completed sentence or structure.

Examples:

```text
.
!
?
"
)
]
```

A `false` result may indicate that the chunk ends in the middle of a sentence.

## `contains_incomplete_trailing_clause`

`true` when the final word suggests an unfinished clause.

Examples:

```text
and
because
although
which
if
unless
```

This is a heuristic and may produce false positives.

## `previous_chunk_similarity`

Lexical similarity between the current chunk and the previous chunk.

The value ranges from 0 to 1.

* A value near 0 means little shared vocabulary.
* A higher value means more shared vocabulary.
* An unusually high value may indicate excessive overlap or duplication.

This uses word-frequency cosine similarity, not embedding similarity.

## `next_chunk_similarity`

Lexical similarity between the current chunk and the next chunk.

Like `previous_chunk_similarity`, this can help detect excessive overlap between neighboring chunks.

## `below_min_tokens`

`true` when the chunk contains fewer tokens than the value supplied through `--min-tokens`.

When no minimum is provided, this remains `false`.

## `above_max_tokens`

`true` when the chunk contains more tokens than the value supplied through `--max-tokens`.

When no maximum is provided, this remains `false`.

## `near_empty`

`true` when the chunk contains fewer than 10 tokens.

A nearly empty chunk may be:

* a heading separated from its content
* page metadata
* an ingestion artifact
* a fragment created by poor boundary handling

---

# Understanding the summary

The output contains an aggregate `summary`.

Example:

```json
{
  "model": "gpt-4.1-mini",
  "chunk_count": 100,
  "successful_count": 98,
  "failed_count": 2,
  "total_characters": 250000,
  "total_tokens": 62000,
  "average_tokens": 620.0,
  "median_tokens": 588.0,
  "token_standard_deviation": 140.5,
  "minimum_tokens": 34,
  "maximum_tokens": 1015,
  "below_min_token_rate": 0.03,
  "above_max_token_rate": 0.08,
  "invalid_start_rate": 0.05,
  "invalid_ending_rate": 0.04,
  "average_adjacent_similarity": 0.18,
  "average_score": 4.12
}
```

## `chunk_count`

The total number of evaluated chunks.

## `successful_count`

The number of chunks for which OpenAI returned a valid structured response.

When using `--skip-llm`, this value will normally be zero.

## `failed_count`

The number of chunks that encountered an OpenAI evaluation error.

This does not include deterministic warnings such as invalid starts or token-limit violations.

## `average_tokens`

The mean number of tokens per chunk.

## `median_tokens`

The middle token count after sorting all chunks by size.

The median is useful because a few extremely large chunks can distort the average.

## `token_standard_deviation`

A measure of how much chunk sizes vary.

A low value means chunk sizes are relatively consistent.

A high value means the strategy produces chunks with widely varying sizes.

Variation is not automatically bad. Heading-aware or semantic chunking may naturally produce more variation than fixed-token chunking.

## `below_min_token_rate`

The proportion of chunks below the configured minimum.

Example:

```json
"below_min_token_rate": 0.12
```

means 12% of chunks were below the minimum.

## `above_max_token_rate`

The proportion of chunks above the configured maximum.

## `invalid_start_rate`

The proportion of chunks that triggered at least one start-boundary heuristic.

A chunk counts as having a likely invalid start when it:

* starts with lowercase text
* starts with a continuation word
* starts with closing punctuation

## `invalid_ending_rate`

The proportion of chunks that triggered at least one ending-boundary heuristic.

A chunk counts as having a likely invalid ending when it:

* does not end with terminal punctuation
* appears to end with an incomplete clause

## `average_adjacent_similarity`

The average lexical similarity between neighboring chunks.

A high value may indicate excessive overlap, but the appropriate value depends on the chunking configuration.

## `average_score`

The average OpenAI chunk-quality score across successful evaluations.

Use this primarily to compare chunking strategies under the same conditions.

Example:

```text
fixed-token, 500 tokens:  3.62
recursive, 500 tokens:    3.94
heading-aware:            4.21
semantic:                 4.08
```

Do not treat this score as absolute ground truth. It is an LLM judgment based on the evaluation prompt and selected model.

---

# Recommended workflow

Start with deterministic evaluation:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --skip-llm --limit 20
```

Then test OpenAI evaluation on a small sample:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --limit 5
```

Inspect:

* score
* reason
* suggestion
* token count
* invalid-boundary flags

When the output looks correct, evaluate the complete file:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --min-tokens 100 --max-tokens 600
```

For different chunking experiments, use different filenames:

```bat
python evals\chunk_eval.py chunks-fixed.jsonl --output fixed.json
```

```bat
python evals\chunk_eval.py chunks-recursive.jsonl --output recursive.json
```

```bat
python evals\chunk_eval.py chunks-semantic.jsonl --output semantic.json
```

These create:

```text
evals/reports/fixed.json
evals/reports/recursive.json
evals/reports/semantic.json
```

Compare:

* average score
* invalid-start rate
* invalid-ending rate
* token-size variation
* below-minimum rate
* above-maximum rate
* individual suggestions

---

# Troubleshooting

## `OPENAI_API_KEY is missing`

Example:

```text
OPENAI_API_KEY is missing. Add it to your .env file.
```

Confirm that `.env` contains:

```dotenv
OPENAI_API_KEY=your_api_key
```

Run the script from a directory where `load_dotenv()` can locate the file.

The Motif project root is a suitable location for `.env`.

---

## No OpenAI model was provided

Example:

```text
No OpenAI model was provided.
```

Add this to `.env`:

```dotenv
OPENAI_MODEL=gpt-4.1-mini
```

or pass the model directly:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl --model gpt-4.1-mini
```

---

## Input file not found

Example:

```text
Input file not found: backend\app\corpus\chunks.jsonl
```

Confirm the file exists:

```bat
dir backend\app\corpus\chunks.jsonl
```

Then run the script from the Motif project root:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

---

## Invalid JSON on a line

Example:

```text
Invalid JSON on line 12
```

Open the specified line in `chunks.jsonl`.

Every line must be an independent valid JSON object.

Correct:

```json
{"chunk_id": "abc123", "text": "Example text."}
```

Incorrect:

```text
{'chunk_id': 'abc123', 'text': 'Example text.'}
```

JSON requires double quotation marks.

---

## Duplicate chunk ID

Example:

```text
Duplicate chunk_id on line 20
```

Every chunk must have a unique `chunk_id`.

Search the input file for the repeated identifier and fix the chunk-generation process or regenerate the IDs.

---

## `No module named app`

Confirm the expected structure:

```text
motif/
├── backend/
│   └── app/
│       └── models.py
└── evals/
    └── chunk_eval.py
```

The script should contain:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))
```

Then import models with:

```python
from app.models import (
    ChunkEvaluationResult,
    ChunkLLMEvaluation,
    DeterministicEvaluation,
    EvaluationOutput,
    EvaluationSummary,
    InputChunk,
)
```

Run the script from the Motif root:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl
```

---

## Pydantic attribute error

Example:

```text
AttributeError: 'EvaluationSummary' object has no attribute 'average_coherence'
```

This means the script still references an older model field.

The simplified LLM result uses:

```text
score
reason
suggestion
```

The simplified summary uses:

```text
average_score
```

Remove old references such as:

```text
coherence
completeness
boundary_quality
atomicity
reference_clarity
average_coherence
overall_llm_score
```

Search on Windows:

```bat
findstr /n /i "average_coherence coherence completeness boundary_quality atomicity reference_clarity overall_llm_score" evals\chunk_eval.py
```

The command should return no remaining old references.

---

## Output appears in the wrong location

The script should build the output path from the location of `chunk_eval.py`, not from the current working directory.

Inside `main()`, use:

```python
evals_directory = Path(__file__).resolve().parent
reports_directory = evals_directory / "reports"

reports_directory.mkdir(
    parents=True,
    exist_ok=True,
)

if arguments.output is not None:
    output_filename = arguments.output.name
else:
    output_filename = f"{arguments.input.stem}_evaluation.json"

output_path = reports_directory / output_filename
```

The save call must use:

```python
save_results(
    output_path=output_path,
    input_path=arguments.input,
    minimum_tokens=arguments.min_tokens,
    maximum_tokens=arguments.max_tokens,
    summary=summary,
    results=results,
)
```

The final print statement must use:

```python
print(f"Results written to: {output_path.resolve()}")
```

Do not use:

```python
print(f"Results written to: {arguments.output.resolve()}")
```

because `arguments.output` may be `None` and may not represent the final reports path.

---

# Limitations

The evaluator provides useful comparative signals, but it does not prove that a chunking strategy is objectively correct.

The deterministic checks use heuristics and may produce false positives.

Examples:

* a valid heading may not end with punctuation
* a valid paragraph may begin with “However”
* neighboring chunks may legitimately share vocabulary
* lowercase text may be intentional formatting
* quoted material may have unusual boundaries

The OpenAI score is also an evaluator-model judgment.

Scores may change when you change:

* the evaluator model
* the system prompt
* neighboring context
* the script version
* chunk ordering
* token limits

For reliable comparisons, keep these settings constant across chunking strategies.

---

# Full command reference

```text
python evals\chunk_eval.py INPUT
    [--output FILENAME]
    [--model MODEL]
    [--min-tokens NUMBER]
    [--max-tokens NUMBER]
    [--skip-llm]
    [--max-retries NUMBER]
    [--limit NUMBER]
```

Example:

```bat
python evals\chunk_eval.py backend\app\corpus\chunks.jsonl ^
  --output results.json ^
  --model gpt-4.1-mini ^
  --min-tokens 100 ^
  --max-tokens 600 ^
  --max-retries 2 ^
  --limit 50
```

This creates:

```text
evals/reports/results.json
```

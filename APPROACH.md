# Approach: Conversational SHL Assessment Recommender

## Objective

The service exposes a stateless FastAPI conversational agent for selecting SHL assessments. It is intentionally grounded to `app/data/shl_catalog.json`; every returned recommendation is copied from that file, and the file is restricted to SHL Individual Test Solutions.

## Data Ingestion

The ingestion script is `scripts/ingest_shl_catalog.py`. It downloads the official assignment catalog JSON from SHL and normalizes each Individual Test Solution into:

- assessment name
- catalog URL
- SHL test type code
- description
- job levels
- languages
- assessment length

The runtime uses the JSON snapshot rather than live network access so `/chat` stays fast and reliable under the 30 second timeout. The normalized catalog currently contains 377 SHL Individual Test Solutions from the provided JSON.

## Agent Design

The agent is implemented as a small RAG pipeline and remains stateless. It rebuilds context from the supplied `messages` array on every request.

The pipeline is:

- scope and injection guard
- intent detection
- structured constraint extraction
- hybrid retrieval
- reranking and diversity enforcement
- optional Groq grounded formatting
- Pydantic schema validation

The router is deterministic:

- **Refuse** when the latest user turn is outside SHL assessment selection, asks for legal/general hiring advice, or resembles prompt injection.
- **Compare** when the user asks for differences or comparisons. The response uses only catalog descriptions and returns no recommendations.
- **Clarify** when the first turn is too vague, such as "I need an assessment."
- **Recommend/Refine** when role, skill, or test-type signals are present. Refinement works by re-ranking against the full supplied history, so edits like "Actually, add personality tests" update the shortlist without stored server state.

## Retrieval

Retrieval is hybrid. The production-safe default uses lexical retrieval plus structured business reranking. The code also supports `sentence-transformers` and FAISS when `ENABLE_SEMANTIC_RETRIEVAL=1` and `requirements-ml.txt` is installed. Catalog titles, descriptions, job levels, languages, duration, and metadata are embedded as retrieval documents. This avoids URL hallucination because only catalog rows can become recommendations.

## Prompting and LLM Use

No external LLM is required for retrieval or schema production. If `GROQ_API_KEY` is set, the app uses Groq only as a grounded formatter for richer prose and comparisons. The prompt instructs the model to use only retrieved catalog context, and the structured recommendation array still comes from catalog rows rather than model output.

## Evaluation Strategy

Validation focuses on hard evals:

- Pydantic response models enforce strict output shape.
- Recommendation arrays are empty for clarify/refusal/compare paths.
- Shortlists contain only objects from the catalog snapshot.
- The request model caps message count at 16 messages, representing up to 8 user/assistant exchange pairs.
- Local probes cover vague clarification, recommendation, refinement, comparison, and off-topic refusal.
- `tests/evaluate.py` reports mean Recall@10, hallucination rate, and guardrail pass rate.
- The public trace harness in `tests/trace_regression.py` reached final-state mean Recall@10 of 1.00 across the 10 provided traces.

The main remaining improvement path is holdout breadth: the public traces are now covered, but unseen personas may still benefit from more synonym expansion, ranking calibration, and enabling the optional semantic index on a larger deployment target.

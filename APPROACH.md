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

The agent is implemented in `app/agent.py` and remains stateless. It rebuilds context from the supplied `messages` array on every request.

The router is deterministic:

- **Refuse** when the latest user turn is outside SHL assessment selection, asks for legal/general hiring advice, or resembles prompt injection.
- **Compare** when the user asks for differences or comparisons. The response uses only catalog descriptions and returns no recommendations.
- **Clarify** when the first turn is too vague, such as "I need an assessment."
- **Recommend/Refine** when role, skill, or test-type signals are present. Refinement works by re-ranking against the full supplied history, so edits like "Actually, add personality tests" update the shortlist without stored server state.

## Retrieval

Retrieval is lightweight lexical scoring over structured catalog fields. The scorer expands common role phrases with assessment-relevant terms, boosts explicitly requested SHL test-type families, and returns a diverse top 1 to 10 shortlist. This avoids URL hallucination because only catalog rows can become recommendations.

## Prompting and LLM Use

No external LLM is required at runtime. This choice improves repeatability for automated evaluation, removes API-key deployment friction, and guarantees schema compliance. The conversational behavior is encoded as transparent routing and retrieval rules rather than hidden model prompts.

## Evaluation Strategy

Validation focuses on hard evals:

- Pydantic response models enforce strict output shape.
- Recommendation arrays are empty for clarify/refusal/compare paths.
- Shortlists contain only objects from the catalog snapshot.
- The request model caps message count at 16 messages, representing up to 8 user/assistant exchange pairs.
- Local probes cover vague clarification, recommendation, refinement, comparison, and off-topic refusal.
- The public trace harness in `tests/trace_regression.py` reached mean Recall@10 of 0.99 across the 10 provided traces. The one apparent miss is REST in C9, which the user later explicitly removes, so the final-state battery remains aligned.

The main remaining improvement path is holdout breadth: the public traces are now covered, but unseen personas may still benefit from more synonym expansion and ranking calibration.

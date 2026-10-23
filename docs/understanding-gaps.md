# Understanding gaps and fallbacks

Use this register to turn observed prompt-understanding failures and surprising
fallbacks into reproducible, privacy-safe work items. It describes actual
behavior; a valid "no match" or "nothing to remember" result is not automatically
a failure.

## Review format

Add one row per concrete case using these fields:

| Feature | Failure/fallback category | Expected vs. actual | Sanitized example/pattern | Current fallback | Recommended next action | Test coverage |
|---------|---------------------------|---------------------|---------------------------|------------------|-------------------------|---------------|
| Feature path or name | Stable category/code | Intended result vs. observed result | Abstract pattern only; no real prompt/note text | Current user-visible behavior | Specific test or implementation investigation | Test file and scenario |

Classify a report as:

- **Understanding gap** when the model or a deterministic rule misclassifies
  valid, sanitized input.
- **Provider/format failure** when a call fails or output cannot be validated.
- **Fallback/operational limitation** when the application continues with a
  reduced capability (for example, lexical retrieval or OCR text).
- **Expected no-op** when the input correctly produces no candidate or match.

Do not label an expected no-op as a gap just because the result is empty.
Reproduce semantic issues with a sanitized fixture and a regression test before
changing a rule or prompt.

## Current register

| Feature | Failure/fallback category | Expected vs. actual | Sanitized example/pattern | Current fallback | Recommended next action | Test coverage |
|---------|---------------------------|---------------------|---------------------------|------------------|-------------------------|---------------|
| Memory extraction | `memory.extraction.provider_failed` | Extract a grounded durable fact when the configured provider is available; provider failure prevents extraction. | A durable preference phrased outside the deterministic name fast path | Return the normal Ask answer and report Memory as unavailable | Reproduce provider outage separately from semantic misses; preserve answer and add a sanitized intent fixture for misses | `test_ai_context_modes.py`; `test_memories.py` |
| Memory extraction | `memory.extraction.output_invalid` | Accept only schema-valid, user-evidenced candidates; malformed/ungrounded output is rejected. | Valid JSON with an invalid candidate shape or evidence | Make no memory change; return the normal Ask answer | Add a sanitized fixture for the rejected output class; never weaken evidence validation to improve recall | `test_memories.py` |
| Memory extraction | Deterministic cue miss / valid empty result | A durable user preference should be retained; an ordinary question or temporary instruction should not. A valid empty model result cannot by itself distinguish a missed intent from a correct no-op. | A paraphrased durable preference without the configured cue words | Structured extraction may return no upserts; status is `unchanged` | Add a regression case only when the intended durable meaning is clear; do not log raw messages or count every empty result as an error | `test_memories.py` name, temporary, question, and empty-result cases |
| Memory forgetting | `memory.forget.unresolved` | Remove only a uniquely matched, unchanged, authorized record; ambiguous or changed records must remain. | A broad forget request matching multiple records | Fail closed; leave memory unchanged and return `unavailable` | Review the fixed event code, then add a sanitized targeting regression if user intent was unambiguous | `test_memories.py` revocation and fail-closed cases |
| Memory retrieval | `memory.query.classification_failed` | A low-overlap query about a keyed preference should retrieve the corresponding record. | A paraphrased question about a saved preference | Keep lexical retrieval results; the keyed record may not be returned | Add sanitized query paraphrases with mocked classifier results; assess live provider accuracy separately | `test_memories.py` semantic query and lexical fallback cases |
| Notes retrieval | Rule-based intent threshold selection | Select a useful note context for the query; `classify_intent()` chooses lookup vs. exploratory thresholds using keyword cues. | Lookup wording without the current `find`/`lookup`/`note`/`stress` terms | No separate fallback; deterministic lexical retrieval can return no qualifying context | Add threshold-boundary tests for concrete misses; a no-match alone is not proof of an intent-classification failure | `test_text_retrieval.py`, `test_ai_context_modes.py` |
| AI Suggestions | `ai_suggestions.action_selection_failed` | Choose one allow-listed action from recent event-type counts; provider or action validation may fail. | Provider outage or an action outside the allow-list | Choose a fixed rule-based action and still return the suggestion | Keep fallback action behavior tested; compare sanitized event patterns when improving the selector | `test_ai_suggestions.py` |
| Flashcards | `flashcards.generation_failed` | Return the requested number of valid, grounded cards; malformed/provider-failed output is rejected. | Missing or malformed `cards` output | Return an error, refund reserved credits, and save no deck; there is no generated-content fallback | Keep schema/grounding tests; inspect only the fixed code and exception type | `test_flashcards.py` |
| Notes from images | `notes.image_ocr.unavailable`, `notes.image_ocr.image_failed` | Extract readable text from each supported image. | Missing OCR dependency or an unreadable/corrupt image | Skip failed images; reject the request if no text remains | Check local dependency/image compatibility; do not attach image bytes or extracted text to diagnostics | No dedicated OCR dependency/image-failure test discovered; add focused coverage when changing this path |
| Notes from images | `notes.image_summary.empty` | Produce a non-empty concise summary from extracted text. | Empty summary result | Save an excerpt of OCR text instead | Add a sanitized blank-output regression if this fallback changes | `test_understanding_gaps.py` covers the fallback and verifies OCR text is not logged |
| Ask | `ask.provider_failed` | Return an answer when the configured provider is reachable. | Provider/network failure during Ask | Return a generic client error and refund reserved credits when applicable | Monitor provider outages separately from semantic misses | `test_diagnostics.py` |
| Ask | `ask.operation_failed` | Return an answer when provider output can be processed. | Unexpected processing failure during Ask | Return a generic client error and refund reserved credits when applicable | Inspect only fixed metadata and exception class | `test_diagnostics.py` |
| Ask | `ask.feedback.reported` | N/A (user-initiated quality signal) | User reports an incorrect or unhelpful answer | Record metadata linked to `operation_id`; do not store conversation text | Review reports through admin diagnostics API or CLI summary | `test_diagnostics.py` |

## Automated production workflow

Observed fallback and failure paths call `report_understanding_gap()` with an
allow-listed code. When a `user_id` is available, the same call also appends a
bounded, content-free diagnostic record under `backend/data/diagnostics_<hash>.json`.
These records include timestamps, feature, code, category, fallback, exception
class, provider/model metadata, and the Ask `operation_id` when the request
context is active. They never store prompts, answers, note text, or provider
response bodies.

Users can report a bad Ask answer from the Ask UI with an allow-listed reason
only (`wrong`, `unhelpful`, `harmful`, `other`). The report links to a completed
Ask `operation_id` for the authenticated user and does not attach conversation
content to the diagnostic record.

Operators with the configured unlimited role (default `admin`) can review recent
metadata with `GET /diagnostics/events` or summarize stored events from
`backend/` using `python -m scripts.analyze_ai_diagnostics`. Use this register
for semantic follow-up: add sanitized expected/actual rows when a code indicates
a reproducible understanding gap rather than a pure provider outage.

## Structured logs and privacy

Backend fallback reports use the `ia.understanding` logger and the stable
`understanding_gap` format:

```text
understanding_gap code=... feature=... category=... fallback=... error_type=...
```

Only allow-listed codes and fixed metadata are logged. The helper accepts an
exception only to record its class name; it never logs exception text, prompts,
note contents, credentials, tokens, or provider responses. Search local backend
logs for `understanding_gap`, then use the code to find the corresponding
register row. Matching diagnostic records (when persistence is enabled) provide
a bounded local review queue; they are not a full conversation archive or
external telemetry service.

Prompt-bearing retrieval diagnostics are disabled by default:
`FAISS_LOG_SCORES`, `INTENT_CACHE_LOG_HITS`, and `LOG_DROPPED_NOTES` default to
false. `MEMORY_ANALYTICS_ENABLED` also defaults to false; enabling it persists
queries and included/dropped note titles locally, so use only with appropriate
test data and access controls. Do not paste raw logs or user content into this
register, issues, or test fixtures.

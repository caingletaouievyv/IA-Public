# AI-assisted decision workflows

## Purpose

IA has natural-language features that may need to infer what a user means before
performing an application operation. A reusable decision workflow provides a
consistent boundary between uncertain interpretation and trusted domain behavior.
It can make similar features easier to reason about, test, and extend without
turning each new feature into a separate, incompatible AI integration.

This document proposes a pattern for future feature work. It is not a claim that
IA already uses one classifier or this workflow across the application. Current
behavior and adoption candidates are called out separately below.

## Canonical workflow

1. **Receive input.** Accept the user's request and the minimum relevant context
   through the normal authenticated application boundary.
2. **Classify intent and category.** If interpretation is genuinely ambiguous,
   ask the AI to return a bounded, structured classification or proposed action
   (for example, a preference update, note operation, or retrieval request).
3. **Evaluate relevance, confidence, permissions, and risk.** Check whether the
   request is in scope and sufficiently clear; independently enforce
   authentication, authorization, ownership, business rules, and operation
   policy. Consider the impact and reversibility of the proposed action.
4. **Resolve the intended resource or existing record.** Find candidate records
   only within the authenticated user's permitted scope. Resolve duplicate,
   stale, or ambiguous matches before changing anything.
5. **Execute a validated operation.** Pass validated domain inputs to the
   relevant manager or service. Do not let AI-generated instructions call
   storage or arbitrary application operations directly.
6. **Verify the outcome and respond.** Check the manager's result and, where
   appropriate, re-read persisted state. Report success only when the intended
   result is confirmed; otherwise explain the failure or ask what is needed.

The AI result is untrusted input at every step. A plausible classification,
high confidence score, or exact-looking resource ID never bypasses application
validation, authentication, authorization, ownership checks, or domain rules.

## Architectural responsibilities

| Layer | Responsibility |
|-------|----------------|
| AI interpretation | Interpret ambiguous natural language; return a constrained classification or proposed action, with relevant evidence when useful. It does not authorize or execute operations. |
| Application/backend boundary | Validate the request and AI result; enforce authentication, authorization, ownership, business rules, allowed operations, confirmation policy, and safe error handling. |
| Feature manager/service | Perform domain-specific reads and writes using the feature's existing rules and helpers. Keep transport and model-specific behavior out of domain operations. |
| Storage | Persist only validated, authorized domain results using the feature's intended data model and consistency guarantees. |
| Tests and observability | Verify interpretation cases and real state changes, and record operational outcomes without exposing secrets or unnecessary personal content. |

Keep feature behavior in its existing domain boundary. This pattern does not
require a universal classifier service; reuse shared validation or policy code
only where multiple features demonstrate the same need.

## Operation types and data models

An interpreted request should resolve to an explicitly allowed operation. A
feature can support only the operations it needs.

| Operation | Meaning and safeguards |
|-----------|------------------------|
| **Skip** | The request is irrelevant, not actionable, or not an operation for this feature. Make no state change. |
| **Retrieve** | Read or search permitted records and return relevant results. Retrieval is not permission to save them elsewhere. |
| **Create** | Add a new domain record after validating required fields, ownership, and duplicate policy. |
| **Update** | Change selected fields on a resolved existing record. Validate the record again at write time and avoid overwriting unrelated or newer values. |
| **Replace** | Intentionally substitute a value or resource. Confirm the target and replacement semantics; require stronger confirmation when replacement is destructive or difficult to reverse. |
| **Delete** | Remove a resolved record only when policy allows it. Check ownership and ambiguity, and require explicit confirmation for destructive or high-impact deletion. |
| **Clarify or confirm** | Ask for missing information or explicit approval. Do not perform the pending write until the answer is sufficient and any required confirmation is received. |

Choose storage semantics based on what the data means; not every AI-assisted
feature is a memory store:

- **Immutable records** represent facts or events that should not be silently
  rewritten. A correction can be represented as a new, linked or superseding
  record so the original history remains intelligible.
- **Mutable keyed preferences** represent a current choice, such as an assistant
  name or application preference. Use a stable key and update that value rather
  than accumulating contradictory current values.
- **Append-only history** records interactions or events over time. Preserve
  history according to its retention policy; do not silently reinterpret it as
  durable user facts or preferences.
- **Derived or retrieved context** is computed or selected to help answer a
  request. It is normally transient and should retain source/ownership
  constraints; do not persist it as a new user record unless a separate,
  validated operation calls for that.

IA currently keeps Notes, Conversation History, and persistent Memory distinct;
this proposed workflow preserves that separation.

## Confidence, relevance, and risk

Confidence is evidence about interpretation, not authorization. Evaluate it
separately from relevance, identity, permissions, and risk. Do not use one
uncalibrated model score as a universal threshold; choose and test decision
criteria for each operation and domain.

- **Proceed** with a low-impact, reversible operation only when the request is
  relevant, the target and required values are clear, confidence meets the
  feature's tested criteria, and deterministic validation and authorization
  pass.
- **Clarify** when intent, category, target, or required fields are ambiguous,
  when candidates conflict, or when confidence is insufficient. Ask a focused
  question rather than guessing.
- **Confirm** before a consequential action when policy requires approval,
  especially replacement or deletion, a broad multi-record change, or an action
  that is difficult to undo. State what will change and which target is
  affected.
- **Reject** unsupported, unauthorized, invalid, unsafe, or out-of-scope
  operations. Do not convert an invalid model result into a successful no-op or
  claim that the operation completed.

Destructive and high-impact actions need stronger safeguards than read-only or
reversible actions. Confirmation does not waive authorization or validation.
Where the target remains ambiguous, fail closed and request clarification
instead of choosing a plausible record.

## Reusable examples

These examples describe where the pattern might apply; they do not assert that
each natural-language workflow exists in IA today.

| Feature | Possible interpretation | Domain and storage boundary |
|---------|-------------------------|----------------------------|
| Memory extraction | Distinguish a durable fact or preference from a question, temporary instruction, or explicit remember/forget request. | Validate evidence, consent and sensitivity policy; keep immutable facts, mutable keyed preferences, and deletion rules distinct in the Memory manager. |
| Assistant preferences | Interpret a request to change how the assistant addresses the user or responds. | Resolve a known preference key, validate its value, and update only that key in the authorized user's preference storage. |
| Application settings | Map a plain-language request to an existing, supported setting and value. | Reuse the Settings schema and per-user authorization; ask if multiple settings or meanings match. Keep ordinary controls deterministic. |
| Notes and knowledge management | Interpret whether a user wants to find, create, update, replace, or delete a note, and resolve a title/category or target. | Reuse Notes validation and CRUD managers, authenticated ownership, and duplicate/append policy. Confirm ambiguous destructive operations. |
| Tasks and reminders | Extract an action, due time, recurrence, and target from natural language. | This feature would first need a task/reminder domain model, time-zone and scheduling rules, ownership, and delivery lifecycle. Validate dates and recurrence deterministically. |
| Context retrieval and search | Translate a conversational question into a scoped search or source-selection proposal. | Keep retrieval read-only and bounded; use existing access rules and retrieval services. AI may help interpret the query, but deterministic search and source authorization remain authoritative. |

## When not to use AI

Prefer deterministic code for structured inputs and predictable rules:

- Parse and validate typed request fields with application schemas.
- Enforce authentication, authorization, ownership, and allowed-operation
  policies in application code.
- Handle simple conditions, exact-key setting updates, calculations, limits,
  date arithmetic, and state transitions with deterministic logic.
- Use existing lexical or other deterministic retrieval when it meets the
  feature's relevance requirements.

Use AI only where interpretation of natural-language meaning adds measurable
value. Keep its scope narrow and pass its proposal through the same validated
domain operations that non-AI callers use.

## Testing and observability

Test both the interpretation boundary and the real application effect:

- Exercise equivalent natural-language phrasings and expected classifications,
  including requests that should be skipped.
- Cover ambiguous targets, missing fields, unclear intent, and clarification or
  confirmation paths.
- Verify duplicate requests and retries do not create duplicate effects.
- Test stale, conflicting, corrected, or superseded values, including concurrent
  or changed records where the storage model permits them.
- Reject malformed, incomplete, out-of-range, unknown-operation, and otherwise
  invalid AI output without changing state.
- Verify unauthenticated, unauthorized, cross-user, and wrong-owner requests
  cannot read or mutate records.
- Exercise manager/storage/provider failures and check that errors are reported,
  partial results are not described as success, and retry behavior is safe.
- Re-read persisted state (or the authoritative manager result) to confirm it
  matches the intended operation and that unrelated state was preserved.

Keep classification tests distinct from integration tests of permissions,
managers, persistence, and user-visible responses. Prefer deterministic fixtures
for model outputs so policy tests do not depend on provider variability. If live
model evaluations are used, keep them separate from the required deterministic
regression suite.

Record useful operational metadata such as operation category, outcome,
validation/clarification reason, and latency where appropriate. Do not log
credentials, tokens, full prompts, sensitive extracted facts, or unnecessary
user content. Use bounded or redacted diagnostics and follow the feature's data
retention and access controls.

## Adoption candidates

The table distinguishes **current behavior** from **proposed work**. Priorities
are sequencing suggestions, not commitments or claims of app-wide
implementation.

| Priority and candidate | Current behavior | Potential value and prerequisites | Main risks |
|----------------------------------|-----------------|----------------------------------|------------|
| **1 — Memory extraction and assistant preferences** | Ask can perform best-effort AI-assisted Memory extraction when the authenticated user's Memory setting is on. The extractor already constrains output and the Memory manager validates and persists user-scoped records; keyed assistant-name preferences are supported. See [project behavior](../project.md) and [Ask flow](../flow.md). | Use the workflow as a review lens for extending supported preference types or extraction rules. Preserve the existing manager, evidence, consent, sensitivity, ownership, and retrieval safeguards; add per-operation tests before widening scope. | Sensitive or inferred facts, false updates/deletes, prompt injection, contradictory preferences, and best-effort failures being mistaken for successful persistence. |
| **2 — Notes and knowledge management** | Notes have authenticated CRUD and deterministic list/filter retrieval. Image-to-note processing uses OCR and AI summarization, then creates a note or appends to a matching title/category. | A future natural-language Notes action could route explicitly among retrieve/create/update/replace/delete. Reuse Notes schemas/managers and define title/category matching, duplicate behavior, and confirmation requirements first. | Updating or appending to the wrong note, duplicate creation, losing user-authored content, cross-user access, and treating an AI summary as source truth. |
| **3 — Context retrieval and search** | Ask supplies conversation history separately; Notes retrieval has existing modes and Memory retrieval is a separate opt-in behavior. Files, GitHub, Drive, and Web Ask sources are currently placeholders; a file-tree endpoint is not an Ask context workflow. | If users need more natural query or source interpretation, evaluate a narrow AI query-planning step against the current deterministic retrieval. Prerequisites include source-specific authorization, bounded retrieval, provenance, and a measurable relevance baseline. | Leaking or retrieving inaccessible context, unsupported source claims, prompt injection in retrieved content, and adding model latency where deterministic search already works. |
| **4 — Application settings** | Settings are per-user values changed through explicit UI/API inputs; Ask source visibility and Memory enablement are not currently natural-language routed. | Consider only if users demonstrate a need to change settings conversationally. Map requests to an allowlist of setting keys and existing schema validation; keep preference forms and ordinary toggles deterministic. | Broad or accidental settings changes, invalid values, confusing AI suggestions with saved settings, and bypassing per-user authorization. |
| **5 — Tasks and reminders** | No task/reminder feature is currently documented among IA's implemented features. | This is a future product capability, not an immediate AI integration. First define task data, CRUD, ownership, time zones, recurrence, notification delivery, and lifecycle; then assess whether natural-language extraction adds value. | Incorrect deadlines or recurrence, missed or duplicate notifications, time-zone errors, and users relying on unimplemented delivery guarantees. |

## Adoption checklist

Before adding an AI-assisted operation, confirm:

- [ ] Natural-language ambiguity is real and AI interpretation adds value over a
  deterministic control or parser.
- [ ] The feature has a clear domain model and only explicitly allowed
  operations; each operation has defined skip, clarification, and confirmation
  behavior.
- [ ] The output has a bounded schema and is treated as untrusted input. Invalid
  or unknown output cannot reach a write path.
- [ ] Authentication, authorization, ownership, validation, and business rules
  are independently enforced by application/backend code.
- [ ] The intended resource can be resolved without guessing, with duplicate,
  stale, conflicting, and missing-target behavior specified.
- [ ] Storage semantics are explicit: immutable record, mutable keyed value,
  append-only history, or transient/derived context.
- [ ] Risk, reversibility, confidence criteria, and confirmation requirements
  are defined for each operation; confidence is not used as permission.
- [ ] Managers/services own domain operations, and failures cannot produce
  success-shaped responses or silent state changes.
- [ ] Tests cover equivalent phrasings, ambiguity, duplicates, invalid output,
  permissions, failures, and verified persisted outcomes.
- [ ] Observability captures enough to diagnose behavior without logging secrets
  or unnecessary sensitive content.
- [ ] The feature documentation states what is implemented and what remains
  proposed, and any new integration preserves behavior of existing paths.

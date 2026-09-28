# Sahayak AI — Final Architecture & Phase-by-Phase Execution Plan

Multilingual, voice-first banking assistant for rural financial inclusion. Deployed as a branch/kiosk system — the customer never needs their own internet or device; only the kiosk needs connectivity, and even that is designed to degrade gracefully.

---

## 1. Problem Statement & Constraints

Rural customers often don't know which bank/government schemes or loan products they qualify for, and asking a human teller doesn't scale and isn't always available. A voice-first AI agent at the branch kiosk can answer this directly, in the customer's own language — but it must remain reliable when the branch's internet connection is unreliable (a real, common condition, not an edge case), and it must never give a wrong or fabricated eligibility answer, since this is a banking context.

**Hard constraints carried through every phase:**
- No dependency on the customer's own device or internet.
- Every eligibility decision must be deterministic, versioned, and auditable — never an LLM guess.
- The system must still answer correctly (just less fluently) if the kiosk's own connection drops.
- Sensitive data (PIN, password, OTP) is never requested or stored by the agent.

---

## 2. Core Architectural Principles (non-negotiable across all phases)

1. **Supervisor + MCP-connected worker agents** — not agent-to-agent (A2A), not a flat multi-agent peer system. No cross-organization trust boundary exists inside one bank's own kiosk, so A2A's overhead buys nothing; MCP gives clean tool access without it.
2. **The deterministic eligibility & rules engine is the only component allowed to decide eligibility.** Supervisor routes, workers extract and narrate, the engine decides. This single rule is what makes the whole system auditable.
3. **Single writer.** Only the supervisor agent (and the DB manager agent for the profile store specifically) ever writes to a datastore. Worker agents are pure read → process → return.
4. **Two separate stores, not one.** Session context store (short-term, per-conversation) and customer profile store (long-term, JWT-gated) have different lifecycles and must not be conflated.
5. **Offline-first, cloud-enhanced.** Every core capability (eligibility check, basic voice interaction) must work with zero live connection. Cloud services (better STT/TTS, more fluent LLM narration) are enhancements layered on top, never the only path.

---

## 3. System Architecture Overview

```
Customer (voice) / Branch staff (document upload)
              │
              ▼
      Voice / Input Layer (LangID → STT → NLU)
              │
              ▼
        Supervisor Agent  ──writes──▶  Session Context Store
              │                                │
   ┌──────────┴──────────┐          (read-only for workers)
   ▼                      ▼
Loan Worker Agent   Scheme Worker Agent
   │                      │
   └──────────┬───────────┘
              ▼   (MCP tool calls)
  Deterministic Eligibility & Rules Engine
   (per-scheme/per-loan-type versioned config)
              │
              ▼
     Structured result (eligible, satisfied[],
     missing[], completion_fraction, confidence,
     rule_source, rule_updated_at)
              │
              ▼
   Worker LLM narrates result + reasoning + benefits
              │
              ▼
   Supervisor composes final reply → Response generation
              │
              ▼
   Translation (if needed) → TTS → Customer

Parallel subsystems:
  Customer Profile Store  ◀── DB Manager Agent (JWT-gated, versioned upsert)
  Scheme/Loan Knowledge Base (vector) ◀── Document Ingestion (staff upload → embed
     for RAG + draft rule proposal → human review → becomes active rule)
  Offline resilience layer: local rule/knowledge cache, local STT/TTS fallback,
     template-based narration fallback, background sync queue
```

---

## 4. Component Deep-Dive

### 4.1 Supervisor Agent
- Owns the conversation state machine for a session.
- Determines intent (loan vs scheme vs mixed), decides which worker(s) to call, in what order.
- After each worker returns, writes the worker's structured result + an updated running summary to the session context store, before deciding the next step.
- Composes the final customer-facing response from worker outputs.
- Never computes eligibility, never writes to the customer profile store directly (delegates to DB Manager Agent).

### 4.2 Worker Agents (Loan Agent, Scheme Agent, extensible to more)
- Each is a narrow LLM + a fixed set of MCP tools scoped to its domain.
- Responsibilities: extract required structured fields from the conversation + profile, check the required-fields registry for what's missing, call the eligibility engine via MCP with what's known, and narrate the structured result — including a plain-language explanation of *why* the customer is/isn't eligible and what benefits the scheme/loan offers.
- Read-only against session context and customer profile stores. Returns structured output to the supervisor; never writes.

### 4.3 Deterministic Eligibility & Rules Engine
- Plain code, not an LLM call. Rules stored as versioned, structured config per scheme/loan type (e.g. `{"field": "monthly_income", "op": "<=", "value": 60000}` combined with AND/OR logic).
- Output schema (fixed, always the same shape):
```json
{
  "scheme_id": "sukanya_samriddhi",
  "eligible": true,
  "satisfied": ["age_requirement", "income_requirement"],
  "missing": ["income_certificate"],
  "completion_fraction": 0.8,
  "confidence": 0.82,
  "rule_source": "scheme_rules_v3",
  "rule_updated_at": "2026-09-01"
}
```
- **Threshold / partial-eligibility feature**: `completion_fraction` drives the "you'd qualify if you also had X" message — computed here, never estimated by an LLM. A configurable per-scheme threshold (e.g. ≥0.6) decides whether the "potentially eligible" message is shown at all, always paired with the explicit missing-criteria list and a disclaimer.

### 4.4 DB Manager Agent + Customer Profile Store
- JWT-gated — only accessible once the customer is authenticated at the kiosk.
- Maintains the required-fields registry (per scheme/loan type: which structured fields are needed) so it can tell the supervisor exactly what's missing.
- **Versioned upsert**: when a field already has a value and a new one is given, the old value is kept with a timestamp rather than overwritten — audit trail, and protection against accidental bad overwrites.
- Excludes PIN, password, OTP, and any other forbidden field by design — these are never even offered a storage path.

### 4.5 Session Context Store
- Short-term, scoped to the current kiosk session only (cleared/archived at session end).
- Holds: conversation summary so far, which fields have already been collected this session, which workers have already been called and their results.
- Written only by the supervisor; read by workers to avoid re-asking the customer something already established this session.

### 4.6 RAG + Scheme/Loan Knowledge Base
- Vector store of scheme/policy documents, used by worker agents to explain benefits, required documents, and application process in natural language.
- Explicitly **not** used for the eligibility decision itself — grounding for explanation only.

### 4.7 Document Ingestion (staff-only flow)
- Branch staff uploads a scheme/loan policy document, tags its type.
- Pipeline: classify → OCR if needed → chunk & embed into the knowledge base (for RAG) **and, separately**, an LLM-drafted rule proposal extracted from the same document.
- The rule proposal is never auto-activated — a human reviews and approves it before it becomes a live rule in the eligibility engine's config. This is what stops the LLM from deciding eligibility through the back door of document ingestion.

### 4.8 Offline-First Resilience Layer
- Local cache of active eligibility rules and scheme knowledge, synced whenever connectivity is up, used as-is when down — eligibility checks work with zero live connection.
- Local/on-device STT+TTS models for the branch's serving languages as the floor; cloud STT/TTS used opportunistically for better quality when online.
- Template-based, rule-linked explanation fallback if the cloud LLM call fails (e.g. "You qualify because your income is under ₹X and you have a child under 10") — never a silent failure.
- Background sync queue for anything that did need connectivity (profile updates to a central system, new rule approvals) — queues locally, syncs automatically once back online.

### 4.9 Security Layer
- **Output-side**: no cross-customer data leakage, PII redacted from logs by default.
- **Input-side**: self-reported financial claims used for eligibility are checked against on-file KYC/profile data where the bank already has it, rather than trusted purely on the customer's word.
- **Forbidden fields** (OTP, PIN, CVV, password): hard-rejected at the code level — the agent never asks for these and refuses to transmit or store them if offered, regardless of what any prompt says.
- Schema validation (Pydantic or equivalent) on every MCP call, both directions.

### 4.10 Voice Layer
- Pipeline: LangID → STT → NLU (intent + structured entity extraction) → supervisor → ... → response generation → Translator (if needed) → TTS.
- All four components behind provider interfaces (`SpeechRecognizer`, `LanguageDetector`, `Translator`, `TextToSpeech`) so local/offline and cloud providers are both pluggable without touching agent logic.
- Code-switching handled by extracting directly from native mixed-language text rather than translating first.

---

## 5. Data Models

```python
# Customer Profile (persistent, JWT-gated)
class CustomerProfile(BaseModel):
    customer_id: str
    monthly_income: float | None
    age: int | None
    dependents: int | None
    employment_type: str | None
    existing_products: list[str] = []
    language_preference: str | None
    # each field internally versioned: {value, source, updated_at, previous[]}

# Required Fields Registry entry
class RequiredFieldsEntry(BaseModel):
    scheme_or_loan_id: str
    required_fields: list[str]

# Eligibility Rule (versioned config, human-approved)
class EligibilityRule(BaseModel):
    scheme_id: str
    version: int
    conditions: list[dict]     # field/op/value triples, AND/OR structure
    source_document: str
    approved_by: str
    updated_at: datetime

# Eligibility Result (engine output — fixed shape, see 4.3)

# Session Context entry
class ContextEntry(BaseModel):
    session_id: str
    turn_index: int
    summary: str
    fields_collected_this_session: dict
    workers_called: list[str]
    written_by: Literal["supervisor"]   # enforced, never a worker
```

---

## 6. Technology Stack (consolidated)

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Agent orchestration | LangGraph (supervisor + worker state machine) |
| Agent-to-tool | MCP servers (eligibility engine, calculators, DB manager exposed as tools) |
| Structured extraction/prompting | DSPy (typed signatures per worker; auto-optimization deferred until real conversation logs exist) |
| Data validation | Pydantic |
| Relational DB | PostgreSQL (customer profile, rules, audit) |
| Vector store | pgvector to start (scheme/loan document embeddings) |
| Cache/session | Redis (session context store, rate limiting) |
| Auth | JWT |
| Voice (cloud) | Provider-abstracted STT/TTS (e.g. Bhashini primary, Whisper fallback) |
| Voice (offline) | Lightweight local/on-device STT+TTS models for the branch's serving languages |
| LLM | Provider-agnostic abstraction (Anthropic + fallback) |
| Observability | Structured logging minimum; Prometheus/Grafana/OTel optional stretch, not MVP-blocking |
| Deployment | Docker, single-kiosk service bundle |

---

## 7. Repository Structure

```
/supervisor            # state machine, routing, context store writer
/workers
  /loan_agent
  /scheme_agent
/eligibility_engine     # deterministic rules, versioned config, threshold logic
/mcp_servers            # tool wrappers around eligibility engine, calculators, DB manager
/db_manager             # profile store access, versioned upsert, required-fields registry
/rag                    # ingestion, chunking, embedding, retrieval
/document_ingestion     # classify, OCR, rule-proposal drafting, human-review queue
/voice
  /providers            # cloud + local STT/TTS/LangID/Translator implementations
/offline
  /cache_sync           # local rule/knowledge cache, background sync queue
/security               # forbidden-field guard, PII redaction, input validation
/database                # migrations, schemas
/tests
```

---

## 8. Phase-by-Phase Execution Plan

For a 3-person team, phases 1–4 can mostly run in parallel once schemas are agreed (one person on eligibility engine + rules, one on supervisor/worker agents, one on data/DB layer), converging for integration at Phase 5 onward.

### Phase 0 — Setup
- Repo scaffolding per Section 7, shared Pydantic schema package, dev environment (Docker Compose: Postgres, Redis).
- **Deliverable**: empty services boot and health-check.

### Phase 1 — Data Layer Foundation
- Implement `CustomerProfile`, `EligibilityRule`, `RequiredFieldsEntry`, `ContextEntry` schemas.
- Postgres migrations for profile store, rules config, audit log tables. Redis setup for session context.
- JWT auth scaffold (login → token → gated profile access).
- **Deliverable**: can create/read a customer profile and a session context entry via direct API calls, auth-gated.
- **Test**: unauthorized access to profile store fails; versioned upsert keeps old value on overwrite.

### Phase 2 — Deterministic Eligibility & Rules Engine (build this before any agent/LLM code)
- Rule schema + evaluator (AND/OR condition trees over structured profile fields).
- Hand-encode 5–10 real schemes/loan products as versioned rule configs (this is your core differentiator — invest real time here).
- Implement `completion_fraction` and configurable per-scheme threshold logic.
- **Deliverable**: given a profile + scheme_id, returns the fixed-shape eligibility result (Section 4.3) with no LLM involved.
- **Test**: hand-crafted test profiles with known expected outcomes (build this as a small regression suite now — reuse it every phase after).

### Phase 3 — MCP Tool Layer
- Wrap the eligibility engine, EMI/benefit calculators, and DB manager operations as MCP tools with strict input/output schemas.
- **Deliverable**: any MCP client can call `check_eligibility(profile, scheme_id)` and get back the Phase 2 result.
- **Test**: malformed tool input rejected before reaching the engine.

### Phase 4 — Worker Agents (text-only, no voice yet)
- Loan Agent and Scheme Agent: LLM + MCP tool access, narrow prompts for field extraction and narration.
- Narration must cite only fields present in the structured engine result — no invented numbers or reasons.
- **Deliverable**: given a text query + a profile, a worker extracts fields, calls the engine via MCP, returns a narrated explanation (eligible/not, why, missing items, benefits).
- **Test**: worker's stated eligibility always matches the engine's `eligible` field exactly (automated check comparing narration claims against structured result).

### Phase 5 — Supervisor Agent + Session Context Integration
- LangGraph state machine: intent detection → worker routing → result write-back to context store → next-step decision → final response composition.
- Enforce single-writer rule at the code level (workers physically cannot call the context store's write method).
- **Deliverable**: full text-only conversation flow works end-to-end — customer asks about a loan and a scheme in one session without repeating already-given info.
- **Test**: session context correctly prevents re-asking a field already collected this session.

### Phase 6 — DB Manager Agent + Required-Fields Registry
- Registry populated for each rule from Phase 2. Supervisor/workers query it to know exactly what's missing for a given scheme.
- Versioned upsert logic fully wired into the live conversation flow (not just direct API calls from Phase 1).
- **Deliverable**: system correctly identifies missing fields mid-conversation and asks only for those.
- **Test**: updating an existing field preserves history; profile completeness check matches the registry exactly.

### Phase 7 — RAG + Knowledge Base
- Ingest scheme/loan documents into the vector store; chunking + embedding pipeline.
- Wire retrieval into worker narration for "what does this scheme cover" / "what documents do I need" style follow-ups.
- **Deliverable**: worker answers grounded, cited explanatory questions beyond raw eligibility (benefits detail, application process).
- **Test**: retrieved passages actually match the scheme being discussed (basic retrieval precision spot-check).

### Phase 8 — Document Ingestion (staff flow) + Human-Reviewed Rule Proposals
- Upload → classify → embed (feeds Phase 7's store) + separate LLM-drafted rule proposal.
- Simple review queue/UI for staff to approve or reject a proposed rule before it becomes active in the Phase 2 engine's config.
- **Deliverable**: a new scheme document, once uploaded and approved, becomes both searchable (RAG) and enforceable (eligibility engine) without code changes.
- **Test**: an unapproved rule proposal never affects live eligibility results.

### Phase 9 — Voice Layer
- Integrate LangID → STT → NLU → (existing text pipeline) → response generation → Translator → TTS, cloud providers first since the text pipeline is already proven.
- Code-switch handling: extraction directly on mixed-language text.
- **Deliverable**: full voice-in, voice-out conversation for the Phase 5 flow.
- **Test**: code-switched sample utterances (Hindi+English) extract correctly; latency measured end-to-end.

### Phase 10 — Offline-First Resilience
- Local rule/knowledge cache with sync-when-online logic.
- Local/on-device STT+TTS fallback wired in with automatic failover from cloud.
- Template-based narration fallback if the LLM call fails or times out.
- Background sync queue for anything requiring connectivity.
- **Deliverable**: pulling the network cable mid-demo, the system still completes an eligibility check and responds in voice (lower fluency, still correct).
- **Test**: forced offline mode still returns correct `eligible` verdicts against the Phase 2 regression suite.

### Phase 11 — Security Hardening
- Forbidden-field hard-rejection enforced and tested across every input path (voice, text, document upload).
- PII redaction in all logs; cross-session/cross-customer isolation tests.
- Input corroboration: flag/soft-warn when a self-reported claim conflicts with on-file profile data.
- **Deliverable**: security test suite passes (Section 9).

### Phase 12 — Reasoning, Benefits & Threshold Polish
- Tune worker narration prompts for clear "why eligible / why not" explanations and benefits summaries.
- Finalize the partial-eligibility ("you'd qualify with X") messaging with disclaimer wording, validated against the Phase 2 `completion_fraction` output.
- **Deliverable**: narration quality reviewed against a checklist (cites only structured facts, always includes missing-items list when relevant, always includes the disclaimer for partial eligibility).

### Phase 13 — Kiosk UX / Printed Summary
- Optional: printed take-home slip (eligible schemes, required documents, next steps) generated at end of session.
- Human-teller handoff screen showing full session summary if the agent reaches its limits.
- **Deliverable**: session ends with either a resolved answer or a clean handoff artifact.

### Phase 14 — Testing, Evaluation & Demo Prep
- Full regression suite (Phase 2's eligibility test set + Phase 4's narration-matches-engine check + Phase 10's offline check) run together as CI.
- End-to-end demo script using a real multilingual, code-switched scenario, including a forced-offline segment to show resilience live.
- **Deliverable**: repeatable demo, documented test results, this architecture doc kept as the reference for the presentation.

---

## 9. Testing Strategy Summary

| Type | What it covers |
|---|---|
| Eligibility regression suite | Hand-crafted profiles × schemes with known expected outcomes (built in Phase 2, run every phase after) |
| Narration-matches-engine check | Automated comparison that worker narration never states an eligibility conclusion the engine didn't produce |
| Voice/code-switch tests | Mixed-language sample utterances extract correctly |
| Offline-mode tests | Same eligibility suite re-run with network disabled |
| Security tests | Forbidden-field rejection, cross-customer isolation, unauthorized profile access |
| Rule-approval tests | Unapproved rule proposals never affect live results |

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Local STT/TTS quality too low for real use | Cloud remains primary path; local is explicitly a floor, tune expectations accordingly in the demo |
| Rule encoding for real schemes takes longer than expected | Start Phase 2 early and in parallel with everything else — it's the critical path |
| Team members blocked waiting on shared schemas | Freeze Pydantic schemas at end of Phase 0 before parallel work begins |
| Offline fallback quality gap makes demo look broken | Explicitly demo *both* modes side-by-side rather than hiding the online path — the contrast is the point |
| Scope creep (A2A, multi-bank marketplace ideas) re-entering | This document is the frozen final architecture — any deviation should be a deliberate, discussed decision, not a mid-build drift |
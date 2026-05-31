# MockAI Phase 1 Specification

**Version:** 0.3 (locked)  
**Date:** 2026-05-31  
**Scope:** Stage 0 (Foundation) + Stage 1 (Interview Engine V1)  
**Sources:** [upgrade-roadmap.md](./upgrade-roadmap.md), Phase 1 planning session decisions

---

## 1. Purpose

Rebuild the MockAI backend into a production-grade, AI-first interview platform. Phase 1 delivers a safer foundation and a versioned AI interview engine that powers static (async) interviews with evidence-backed scoring and structured outputs.

Phase 1 does **not** deliver the company platform (Stage 2), live interviews (Stage 4), integrity/anti-cheat (Stage 3.5), or Temporal workflows.

---

## 2. Goals

| Goal | Success signal |
|------|----------------|
| Safer, modular codebase | No `eval()` in DB init; config centralized; embedded models fixed |
| AI as a production subsystem | Every AI call tracked; Pydantic-validated outputs; versioned prompts |
| Better static interviews | Planner → questions → per-answer evaluation → defensible reports |
| Reusable engine | Same `app/ai/` layer usable later for company + live flows |

---

## 3. Verified Current State (as of 2026-05-31)

These facts were confirmed by inspecting the repo — not assumed.

### 3.1 Layout

Flat Python package at repo root (no `app/` package yet):

```
main.py, auth.py, database.py, openai_utils.py, schemas.py, common_utils.py
models/          # Beanie documents
services/        # Route handlers mixed with business logic
deploy/          # K8s manifests (legacy "prepsom" naming)
```

No `tests/` directory. No `.env.example`.

### 3.2 API surface (today)

| Prefix | Router file | Notable routes |
|--------|-------------|----------------|
| `/user` | `services/users_service.py` | signup, OTP, profile, resume, dashboard |
| `/interview` | `services/interview_service.py` | create, generate_questions, transcribe, submit, paid, billing, TTS |
| `/company` | `services/company_service.py` | signup, login, dashboard |
| `/aptitude` | `services/aptitude_service.py` | tests, submit, scores |

Frontend (`mockai-frontend`) calls these paths directly (e.g. `InterviewContextProvider.jsx` → `/interview/*`, `/user/*`).

### 3.3 Known bugs / tech debt

1. **`database.py` uses `eval()`** for dynamic Beanie model discovery (lines 46–49).
2. **Embedded `Document` classes** inside `models/interview.py` (`SpeechAnalysis`, `QuestionResponse`, `FreeReview`, etc.) — should be `BaseModel` embeds.
3. **Payment status route bug:** `@router.get("/interview/status")` on router mounted at `/interview` → effective path **`GET /interview/interview/status`**. Target fix: `GET /billing/interviews/{id}/status` (per Phase 1 decisions).
4. **LangChain** used throughout `openai_utils.py` with raw JSON-in-text parsing and fragile cleanup.
5. **Google Cloud TTS** in `interview_service.py` (`texttospeech`, `storage`); Phase 1 decision is OpenAI TTS (`tts-1-hd`, voice `nova`).
6. **Hardcoded values:** S3 bucket `mockai-resume`, CORS origins in `main.py`, model names in `openai_utils.py`, Razorpay amounts in route handlers.
7. **Bloated `requirements.txt`:** includes langchain, streamlit, pandas, scikit-learn, etc. unrelated to the API.
8. **Deploy naming:** `prepsom-backend-v2` in `deploy/deployment.yaml` (legacy).

### 3.4 Current AI flow (static interview)

```
create_interview → generate_questions (LangChain, JSON text)
  → per question: transcribe (Whisper HTTP) + analyze_audio (LangChain JSON)
  → submit_interview (LangChain free report, sync, blocks request)
  → GET /paid (LangChain paid report, sync on first access)
```

Minimum 4 answered questions required to submit (hardcoded in `interview_service.py`).

---

## 4. Architectural Decisions (Phase 1)

| Topic | Decision |
|-------|----------|
| LangChain | Remove entirely |
| AI runtime | **[Pydantic AI](https://ai.pydantic.dev/)** in `app/ai/` only — `OpenAIResponsesModel` + `NativeOutput` |
| AI API | OpenAI **Responses API** + **Structured Outputs** (Pydantic schemas via Pydantic AI) |
| TTS | OpenAI `tts-1-hd`, voice `nova` — replace Google TTS |
| Database | MongoDB + Beanie (unchanged for Phase 1) |
| Python | 3.12+ |
| Workers / Temporal | **Not in Phase 1** — use FastAPI `BackgroundTasks` for async report generation |
| Auth | JWT (existing pattern); move to `app/core/security.py` |
| OTP / Redis | Keep Redis for OTP (existing `get_redis` in `main.py`) |

### 4.1 Locked product decisions (2026-05-31)

| # | Decision |
|---|----------|
| 1 | **Zero backward compatibility.** Delete legacy code; rebuild `app/` cleanly to production-grade standards. No legacy route wrappers. |
| 2 | **No existing MongoDB data.** Fresh schema only; no migration scripts. |
| 3 | **Aptitude in scope.** Port `/aptitude` to new structure with minimal changes. |
| 4 | **Company routes deferred.** Do not port `/company/*`, `Company`, or `Employee` until Stage 2. |
| 5 | **Minimum answers to submit:** configurable via `MIN_ANSWERS_TO_SUBMIT` env (default `4`). |
| 6 | **Recruiter scorecard:** define `RecruiterScorecard` Pydantic schema and generate/store on paid report path; **no API exposure** in Phase 1. |
| 7 | **Big-bang cutover.** Replace root `main.py` and delete all legacy modules in the same release; entrypoint is `uvicorn app.main:app`. |

Frontend must update to new API paths separately (spec §7). Paid report: triggered on payment verify **and** via `POST /interviews/{id}/report/paid` for explicit retry.

### 4.2 AI layer scope (Pydantic AI)

Pydantic AI is used **only** under `app/ai/` as the structured inference runtime. It is **not** used for FastAPI routes, Beanie, billing, Whisper, or TTS.

| Uses Pydantic AI | Does not use Pydantic AI |
|------------------|--------------------------|
| `app/ai/client.py` — shared `structured_completion()` wrapper | `app/api/`, `app/services/` |
| All six AI services (planner, strategist, conductor, evaluator, reports, guardrails) | `app/integrations/whisper.py`, `tts.py` |
| AI unit tests via `TestModel` / `FunctionModel` | Razorpay, S3, email, Redis OTP |

Each AI service: load versioned prompt → call `structured_completion()` → persist `AIRequest`. No multi-tool agent loops in Phase 1 — single-shot structured calls only.

---

## 5. Target Repository Structure

```
app/
  main.py
  core/
    config.py          # pydantic-settings
    logging.py         # structured logging + request ID
    errors.py          # global exception handlers
    security.py        # JWT, get_current_user
    deps.py            # Redis, DB, settings deps
  db/
    client.py          # Motor client
    init.py            # explicit Beanie model list (no eval)
    models/            # top-level Documents only
  api/
    routes/
      auth.py
      users.py
      interviews.py
      billing.py
      aptitude.py
  services/
    auth_service.py
    user_service.py
    interview_service.py
    billing_service.py
    aptitude_service.py
  ai/
    client.py          # Pydantic AI wrapper (OpenAIResponsesModel + NativeOutput)
    tracking.py        # AIRequest persistence (maps result.usage → Mongo)
    schemas/
      interview_plan.py
      question_set.py
      evaluation.py
      report.py
    prompts/
      planner/v1.md
      strategist/v1.md
      evaluator/v1.md
      conductor/v1.md
      report/v1.md
      guardrails/v1.md
    planners/interview_planner.py
    strategists/question_strategist.py
    conductors/static_conductor.py
    evaluators/answer_evaluator.py
    reports/report_generator.py
    guardrails/quality_guardrails.py
  integrations/
    storage.py         # S3
    tts.py             # OpenAI TTS (direct SDK/HTTP — not Pydantic AI)
    razorpay.py
    email.py
    whisper.py
tests/
  conftest.py
  test_ai/
  test_api/
.env.example
requirements.txt       # trimmed
```

Legacy root files (`main.py`, `openai_utils.py`, `auth.py`, `database.py`, flat `services/`, flat `models/`) are **deleted** in the big-bang cutover — not kept alongside `app/`.

---

## 6. Scope

### 6.1 In scope

**Stage 0 — Foundation**

- `pydantic-settings` config for all env vars and hardcoded constants
- Structured logging + request ID middleware
- Global error handling (consistent JSON error shape)
- Fix `database.py`: explicit model registration, remove `eval()`
- Fix models: embeds as `BaseModel`, only collections as `Document`
- Auth in `app/core/security.py`
- Integration modules (OpenAI, S3, Razorpay, TTS, email, Whisper)
- Fix payment status route bug
- `.env.example`, cleaned `requirements.txt`
- Basic tests for auth, interview create, question generation, submit flow
- Update deploy manifest naming (MockAI, not prepsom) — config only, no secrets in repo

**Stage 1 — Interview Engine V1**

- Versioned prompts (`app/ai/prompts/*/v1.md`)
- Pydantic output schemas: `InterviewPlan`, `QuestionSet`, `AnswerEvaluation`, `FreeReportOutput`, `PaidReportOutput`, `RecruiterScorecard` (schema + generation only; no API)
- `AIRequest` document — every AI call logs model, prompt version, schema version, token counts (input/cached/output), latency, validation status
- Prompt caching convention: stable system prefix first, dynamic data last
- Model routing: `gpt-4o-mini` for fast/cheap tasks; `gpt-4o` for planner, evaluator, reports
- AI services:
  1. **InterviewPlanner** — role + resume + company → `InterviewPlan`
  2. **QuestionStrategist** — plan → `QuestionSet` (intent, competency, difficulty, backup questions, follow-up policy)
  3. **StaticConductor** — weak/vague answer → follow-up decision
  4. **AnswerEvaluator** — transcript + question + competency → `AnswerEvaluation` with evidence
  5. **ReportGenerator** — free report (triggered on submit) + paid report (background)
  6. **QualityGuardrails** — illegal/bias/rubric mismatch checks
- Structured outputs only; retry with repair prompt on validation failure (max 1 retry)
- Static interview upgrades: adaptive follow-up, resume/company-aware questions, evidence-backed speech analysis

### 6.2 Out of scope (Phase 1)

- **`/company/*` routes** and `Company` / `Employee` models (Stage 2)
- Company workspace, job openings, interview templates (Stage 2)
- Invite links, RBAC, audit logs (Stage 2)
- Recruiter scorecard **API** or UI (schema + embed storage only)
- LiveKit / Realtime API / live conductor (Stage 4)
- Temporal / Celery workers
- Integrity / anti-cheat (Stage 3.5)
- Candidate memory / MemorySynthesizer (future)
- Postgres migration
- MongoDB data migration (no legacy data exists)
- Legacy API paths and compatibility wrappers

### 6.3 Aptitude module

Port existing `/aptitude` behavior to `app/api/routes/aptitude.py` and `app/services/aptitude_service.py` with minimal changes. No AI engine work. Aptitude models move to `app/db/models/`.

---

## 7. API Contract (target — clean break)

Base path unchanged (`/`). New resource-oriented routes:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/otp/send` | Send OTP |
| POST | `/auth/otp/verify` | Verify OTP → JWT |
| GET | `/users/me` | Current user profile |
| PATCH | `/users/me` | Update profile |
| POST | `/users/me/resume` | Upload resume |
| POST | `/interviews` | Create interview session |
| GET | `/interviews/{id}` | Get interview state |
| POST | `/interviews/{id}/questions` | Generate question set (AI) |
| POST | `/interviews/{id}/turns/{turn_id}/audio` | Upload audio → transcribe + evaluate |
| POST | `/interviews/{id}/submit` | **202 Accepted** — enqueue free report generation |
| GET | `/interviews/{id}/report` | Free report (+ status: pending/ready/failed) |
| POST | `/interviews/{id}/report/paid` | Trigger paid report (after payment) |
| POST | `/billing/orders` | Create Razorpay order |
| POST | `/billing/verify` | Verify payment signature |
| POST | `/billing/webhook` | Razorpay webhook |
| GET | `/billing/interviews/{id}/status` | Payment status (**fixes bug**) |
| POST | `/tts/synthesize` | OpenAI TTS |
| GET/POST | `/aptitude/...` | Ported aptitude routes (same behavior, cleaner paths TBD at implementation) |

### 7.1 Mapping from legacy routes (frontend migration reference only)

Legacy code is deleted; this table is for frontend/API client updates only.

| Current | New |
|---------|-----|
| POST `/user/sendOtp` | POST `/auth/otp/send` |
| POST `/user/verifyOtp` | POST `/auth/otp/verify` |
| GET `/user/profile` | GET `/users/me` |
| PATCH `/user/profile` | PATCH `/users/me` |
| POST `/user/profile/resume` | POST `/users/me/resume` |
| POST `/interview/create_interview` | POST `/interviews` |
| POST `/interview/generate_questions` | POST `/interviews/{id}/questions` |
| POST `/interview/transcribe` | POST `/interviews/{id}/turns/{turn_id}/audio` |
| POST `/interview/submit_interview` | POST `/interviews/{id}/submit` |
| GET `/interview/paid` | GET `/interviews/{id}/report` + POST `/interviews/{id}/report/paid` |
| GET `/interview/interview/status` | GET `/billing/interviews/{id}/status` |
| POST `/interview/synthesize_speech` | POST `/tts/synthesize` |
| POST `/interview/create_order` | POST `/billing/orders` |
| POST `/interview/verify_order` | POST `/billing/verify` |
| POST `/interview/razorpay/webhook` | POST `/billing/webhook` |

---

## 8. Data Model Changes

### 8.1 Top-level MongoDB collections (Beanie `Document`)

| Collection | Notes |
|------------|-------|
| `users` | Fresh schema; preserve useful fields (profile, resume, OTP identity) |
| `interview` | New schema: `interview_plan`, `question_set`, report statuses, turn evaluations, optional `target_company: str` |
| `payments` | Fresh schema aligned with billing service |
| `ai_requests` | **New** — traceability record per §8.3 |
| Aptitude collections | Port as-is into `app/db/models/` |

**Not in Phase 1:** `companies`, `employees` collections (Stage 2).

### 8.2 Embeds (`BaseModel`, not `Document`)

Move out of `models/interview.py`:

- `SpeechAnalysis`, `QuestionResponse`, `FreeReview`, `PaidReview`, and all nested review types
- New: `InterviewTurn`, `AnswerEvaluationEmbed`, `ReportStatus`

### 8.3 AIRequest schema

```python
# app/db/models/ai_request.py (illustrative)
class AIRequest(Document):
    workflow_id: str | None          # interview_id for Phase 1
    task_type: str                   # e.g. "interview_plan", "answer_eval"
    prompt_version: str              # e.g. "planner/v1"
    schema_version: str              # e.g. "interview_plan/v1"
    model: str
    input_refs: dict                 # e.g. {"interview_id": "...", "turn_id": "..."}
    input_token_count: int
    cached_token_count: int
    output_token_count: int
    latency_ms: int
    raw_response: str | None         # or S3 ref if large
    parsed_output: dict | None
    validation_status: Literal["valid", "repaired", "failed"]
    created_at: datetime
```

### 8.4 Interview document extensions

```python
class ReportStatus(str, Enum):
    pending = "pending"
    generating = "generating"
    ready = "ready"
    failed = "failed"

# On Interview:
interview_plan: InterviewPlanEmbed | None
question_set: QuestionSetEmbed | None
free_report_status: ReportStatus
paid_report_status: ReportStatus
recruiter_scorecard: RecruiterScorecardEmbed | None  # generated with paid report; not exposed via API
# free_review / paid_review shapes match new AI schemas
```

**Data:** Greenfield only. No migration scripts.

---

## 9. AI Engine Specification

### 9.1 Quality rules (non-negotiable)

1. No production path trusts raw model text — all outputs validated against Pydantic schemas via Structured Outputs.
2. Every AI output linked to an `AIRequest` row with token counts and latency.
3. On validation failure: one repair attempt with explicit schema error feedback; then fail the task and surface `report_status=failed`.
4. Every score must cite transcript evidence — no generic feedback.
5. Prompt structure: stable instructions + schema prefix first; candidate/interview data last (cache-friendly).

### 9.2 Model routing

| Task | Model |
|------|-------|
| Guardrails pre-checks, simple classification | `gpt-4o-mini` |
| InterviewPlanner, QuestionStrategist | `gpt-4o` |
| AnswerEvaluator, ReportGenerator | `gpt-4o` |
| StaticConductor follow-up decision | `gpt-4o-mini` |
| Transcription | Whisper (`whisper-1`) via `integrations/whisper.py` |

Exact model IDs live in config, not code.

### 9.3 Service contracts

#### InterviewPlanner

- **Input:** `job_role`, `years_of_experience`, `field`, `resume_summary`, `company_name`, optional `job_description`
- **Output:** `InterviewPlan` — competencies to probe, difficulty arc, intro/outro notes, resume deep-dive areas

#### QuestionStrategist

- **Input:** `InterviewPlan`, prior questions (dedup)
- **Output:** `QuestionSet` — ordered questions with `competency`, `difficulty`, `intent`, `backup_question`, `follow_up_policy`

#### StaticConductor

- **Input:** question, `AnswerEvaluation`, follow_up_policy
- **Output:** `{ ask_follow_up: bool, follow_up_question: str | None }`

#### AnswerEvaluator

- **Input:** question, competency, transcript, optional audio metrics (WPM, fillers)
- **Output:** `AnswerEvaluation` — rubric signals with evidence, strengths, concerns

#### ReportGenerator

- **FreeReportOutput:** overall summary, competency scores with evidence, strengths/weaknesses, speech summary
- **PaidReportOutput:** per-question analysis, performance metrics, career recommendations
- **RecruiterScorecard:** competency scores with evidence, hire/no-hire signals, reviewer notes structure — generated alongside paid report, stored on `Interview`, not returned by any Phase 1 route
- Free report: kicked off by `POST .../submit` (background)
- Paid report + scorecard: kicked off on payment verify and via `POST .../report/paid` (background)

#### QualityGuardrails

- Run on generated questions before returning to client
- Run on reports before marking `ready`
- Block or regenerate on: discriminatory content, off-role questions, rubric mismatch

### 9.4 AI client pattern (Pydantic AI)

Central helper in `app/ai/client.py` wraps Pydantic AI — domain services never call OpenAI directly.

```python
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIResponsesModel

async def structured_completion[T: BaseModel](
    *,
    task_type: str,
    prompt_version: str,
    schema_version: str,
    model: str,
    system_prompt: str,
    user_content: str,
    output_schema: type[T],
    workflow_id: str | None = None,
    input_refs: dict | None = None,
) -> tuple[T, AIRequest]:
    agent = Agent(
        OpenAIResponsesModel(model),
        instructions=system_prompt,
        output_type=NativeOutput(output_schema, strict=True),
        retries={"output": 1},  # spec: max 1 repair on validation failure
    )
    result = await agent.run(user_content)
    # Map result.output → T
    # Map result.usage → AIRequest fields:
    #   input_tokens, output_tokens, cache_read_tokens (cached)
    # Set validation_status: valid | repaired | failed
    # Persist via tracking.py; return (parsed, ai_request)
```

**We still own:** prompt files, `prompt_version` / `schema_version`, `AIRequest` persistence, model routing from config, business guardrail policy.

**Pydantic AI owns:** schema → API call, parse/validate, output retry, `RunUsage` token aggregation.

Optional: cache agents per `(task_type, prompt_version, model)` if construction cost matters — start simple, optimize if needed.

---

## 10. Configuration

| Setting | Env var | Default | Notes |
|---------|---------|---------|-------|
| Min answers to submit | `MIN_ANSWERS_TO_SUBMIT` | `4` | Enforced in `submit_interview`; return 400 if below threshold |
| CORS origins | `CORS_ORIGINS` | (required) | Comma-separated list |
| OpenAI fast model | `OPENAI_MODEL_FAST` | `gpt-4o-mini` | Conductor, guardrails |
| OpenAI strong model | `OPENAI_MODEL_STRONG` | `gpt-4o` | Planner, evaluator, reports |
| TTS | `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE` | `tts-1-hd`, `nova` | Replaces Google TTS; direct OpenAI audio API, not Pydantic AI |

Remove `google-cloud-texttospeech` from dependencies. Resume storage stays on S3 (boto3).

**Python package:** `pydantic-ai-slim[openai]` (or `pydantic-ai`) — only required for `app/ai/`.

---

## 11. Acceptance Criteria

### Foundation

- [ ] App starts with `uvicorn app.main:app`; health check returns 200
- [ ] All settings loaded from env via `Settings` class; `.env.example` documents every var
- [ ] No `eval()` in database initialization; no legacy root modules remain (`rg langchain` clean)
- [ ] Request ID present in logs and error responses
- [ ] `GET /billing/interviews/{id}/status` returns correct payment state
- [ ] `requirements.txt` installs only needed packages; LangChain removed
- [ ] At least smoke tests pass in CI for auth + interview lifecycle

### AI Engine

- [ ] Question generation uses Structured Outputs; invalid response triggers ≤1 repair
- [ ] Each AI call creates an `AIRequest` document with token counts
- [ ] Answer evaluation includes evidence strings tied to transcript
- [ ] Submit returns **202** immediately; free report status pollable via `GET .../report`
- [ ] Guardrails block or regenerate clearly biased/off-topic questions (test with fixture prompts)
- [ ] TTS endpoint uses OpenAI `tts-1-hd` / `nova`
- [ ] Follow-up question inserted when `StaticConductor` recommends it after weak answer
- [ ] `RecruiterScorecard` persisted on interview after paid report generation (not exposed via API)
- [ ] Submit rejected when answered count `< MIN_ANSWERS_TO_SUBMIT`

### End-to-end

- [ ] A candidate can complete a full static interview through the **new API** (manual or frontend)
- [ ] Free and paid reports contain evidence-backed content, not generic filler

---

## 12. References

- [upgrade-roadmap.md](./upgrade-roadmap.md) — Stages 0–1, AI architecture, quality bar
- [Pydantic AI](https://ai.pydantic.dev/) — Agent, NativeOutput, OpenAIResponsesModel
- [Pydantic AI — OpenAI Responses API](https://ai.pydantic.dev/models/openai/#openai-responses-api)
- [Pydantic AI — Output / NativeOutput](https://ai.pydantic.dev/output/)
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs

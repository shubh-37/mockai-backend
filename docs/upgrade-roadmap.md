# MockAI Upgrade Roadmap

Last updated: 2026-05-31

## North Star

MockAI should become an interview intelligence platform, not just a question generator.

The product should serve two audiences:

1. Candidates who want realistic practice, clear feedback, and measurable improvement.
2. Companies that want to create, schedule, run, review, and compare AI-assisted interviews at hiring scale.

The rebuild should optimize in this order:

1. Interview quality
2. Trust, consistency, and explainability
3. Company revenue workflows
4. Interview integrity and anti-cheat
5. Low-latency live experience
6. Long-term candidate and company memory

Latency matters, but only after the interview itself is worth taking. A fast shallow interviewer is still a bad product.

## Current Product Snapshot

The current system supports:

- Candidate signup/login through OTP.
- Candidate profile, resume upload, and resume summary.
- Static interview creation.
- AI-generated question list.
- Browser camera preview and audio recording.
- Per-question audio upload.
- Whisper transcription.
- AI speech/content analysis.
- Free and paid reports.
- Razorpay payment flow.
- Aptitude tests.

This is a useful prototype, but the architecture is shaped around a single-user mock interview flow. The broader company/interview platform needs a cleaner domain model and a more deliberate AI interview engine.

## Strategic Direction

The upgrade should not begin with LiveKit. It should begin with the AI interview engine.

AI should be the core upgrade of the platform. The company workflows, candidate practice product, static interviews, live interviews, reports, memory, and shortlisting should all be powered by the same versioned AI system. LiveKit is the media layer. Temporal or another workflow engine is the reliability layer. The AI engine is the product.

The right sequence is:

1. Modernize the current codebase and data model.
2. Build the company platform and interview-template system.
3. Improve static/asynchronous interview quality using the new engine.
4. Add human-in-the-loop review, recordings, integrity checks, and candidate comparison.
5. Add live AI interviews with LiveKit/OpenAI Realtime.
6. Add durable user/company memory and continuous learning loops.

This keeps revenue work moving while making the live experience much stronger when it arrives.

## AI-First Platform Architecture

The rebuild should treat AI like a production subsystem, not a collection of prompts.

The AI platform should include:

- Versioned system prompts.
- Pydantic input/output schemas.
- OpenAI structured outputs.
- Prompt caching strategy.
- Token-budgeting and summarization.
- Model routing by task.
- Evals for every major prompt/agent.
- Workflow orchestration for long-running jobs.
- Full traceability from final score back to transcript evidence.

Every important AI result should be reproducible and inspectable:

```txt
AIRequest
  id
  workflow_id
  task_type
  prompt_version
  schema_version
  model
  input_refs
  input_token_count
  cached_token_count
  output_token_count
  latency_ms
  raw_response_asset_id
  parsed_output
  validation_status
  created_at
```

### Core AI Services

```txt
InterviewPlanner
  Creates the interview plan from role, resume, company criteria, job description, and memory.

QuestionStrategist
  Produces planned questions, required questions, backup questions, and follow-up policies.

InterviewConductor
  Decides what to ask next in static or live mode.

AnswerEvaluator
  Scores each answer against the rubric and extracts evidence.

ScorecardGenerator
  Produces recruiter-facing structured scorecards.

CandidateCoach
  Produces candidate-facing feedback and improvement plans.

MemorySynthesizer
  Compresses prior interviews into useful, privacy-aware memory.

QualityJudge
  Evaluates question quality, scoring quality, bias risk, and report usefulness.

IntegrityAnalyzer
  Detects suspicious interview behavior from browser, audio, video, transcript, and recording signals.
```

### OpenAI Usage Strategy

Use OpenAI APIs in different modes depending on the task:

- Responses API for structured planning, scoring, reports, tool use, and multi-step agentic work.
- Structured Outputs for every planner/evaluator/report object, preferably generated from Pydantic models.
- Background mode for long-running report generation, deep scorecards, or multi-candidate comparisons where an HTTP request should not stay open.
- Realtime API for low-latency speech-to-speech live interviews.
- Prompt caching for long repeated system prompts, rubrics, scoring instructions, and stable schema/tool prefixes.

Official OpenAI docs note that Structured Outputs can use JSON Schema directly and SDK helpers can parse into Pydantic/Zod models. Prompt caching works best when static instructions and examples appear at the start of the prompt, with user-specific data later. The Realtime API is designed for low-latency multimodal experiences including speech-to-speech conversations.

### Pydantic And Structured Outputs

Define every AI contract as code:

```python
from pydantic import BaseModel, Field
from typing import Literal


class RubricSignal(BaseModel):
    competency: str
    evidence: str
    score: float = Field(ge=0, le=10)
    confidence: Literal["low", "medium", "high"]


class AnswerEvaluation(BaseModel):
    question_id: str
    answer_summary: str
    rubric_signals: list[RubricSignal]
    strengths: list[str]
    concerns: list[str]
    follow_up_recommended: bool
    follow_up_question: str | None = None
```

Rules:

- No production AI path should depend on fragile regex cleanup of model text.
- Store schema version with each generated artifact.
- Validate before saving.
- Retry with a repair prompt only when validation fails.
- Keep raw output for debugging, but never trust raw output as product data.

### Prompt System

Prompts should be treated like code:

```txt
ai/prompts/
  interview_planner/
    v1.md
    v2.md
    eval_cases.jsonl
  answer_evaluator/
    v1.md
    v2.md
    rubric_examples.md
  live_conductor/
    v1.md
    latency_notes.md
```

Each prompt should have:

- Purpose.
- Inputs.
- Output schema.
- Non-negotiable rules.
- Good examples.
- Bad examples.
- Safety constraints.
- Version.
- Eval cases.

Prompt design principles:

- Put stable instructions first for caching.
- Put dynamic candidate/interview data at the end.
- Separate company criteria from candidate memory.
- Require evidence for every score.
- Ask for uncertainty when the answer is weak or transcript quality is poor.
- Avoid inflated scoring.
- Avoid generic feedback.
- Make the AI interviewer follow a plan but adapt within boundaries.

### Token Saving And Context Strategy

Token saving should be part of the design from day one.

Use these techniques:

- Stable prompt prefixes to improve OpenAI prompt cache hits.
- Small models for classification, extraction, and simple validation.
- Stronger models only for planning, final evaluation, and nuanced reports.
- Store compact interview memory summaries instead of resending full histories.
- Use transcript chunking for long interviews.
- Use evidence windows around relevant transcript moments.
- Deduplicate repeated profile/resume/company data.
- Cache resume summaries, job-description summaries, and company rubric summaries.
- Use retrieval instead of stuffing all memory into every request.
- Log `cached_tokens`, input tokens, output tokens, latency, and task type.
- Set task-level token budgets.

Context packing order:

```txt
1. Stable system prompt and rules
2. Output schema/tool definitions
3. Rubric and interview template summary
4. Candidate/job/company summary
5. Relevant memory snippets
6. Current question/answer/transcript
7. Explicit task instruction
```

### Workflow Orchestration

Use Temporal if workflows become multi-step, long-running, or reliability-critical.

Good Temporal candidates:

- Company interview invite lifecycle.
- Static interview completion pipeline.
- Resume extraction and summarization.
- Final report generation.
- Paid scorecard generation.
- Recording processing.
- Live interview post-processing.
- Multi-candidate comparison.
- Email reminders and retries.

Example workflow:

```txt
InterviewCompletedWorkflow
  1. Lock session
  2. Ensure all recordings/transcripts are uploaded
  3. Normalize transcript
  4. Evaluate each answer
  5. Generate scorecard
  6. Generate candidate feedback
  7. Update company dashboard
  8. Send completion emails
  9. Emit analytics events
```

Start without Temporal only if the system is still simple. Once company interviews, retries, recordings, emails, and live sessions exist, Temporal becomes valuable because those workflows need durability, retry policies, and visibility.

### AI Quality Bar

The interview engine should be judged by:

- Question relevance.
- Follow-up quality.
- Candidate experience.
- Rubric adherence.
- Evidence-backed scoring.
- Low hallucination rate.
- Fairness and compliance.
- Recruiter usefulness.
- Candidate improvement usefulness.

The best version of the product is not "AI asks questions." It is "AI runs a structured interview process that feels natural and produces decisions humans can trust."

## Recommended Tech Stack

### Frontend

Use a serious modern frontend stack:

- Next.js App Router or modern Vite React if SEO/server rendering is not important for the app area.
- TypeScript everywhere.
- TanStack Query for server state.
- Zustand or Jotai for local app state.
- React Hook Form + Zod for forms.
- Tailwind + shadcn/ui or a tightly controlled internal design system.
- Recharts or Tremor-style components for analytics.
- LiveKit React SDK for live rooms.
- OpenAI Agents SDK for browser-based realtime prototypes where direct WebRTC to OpenAI is useful.
- Sentry or OpenTelemetry browser tracing.

Recommendation:

- Keep the marketing site separate or Next.js-based.
- Build the authenticated product app as a dense, reliable dashboard.
- Avoid mixing MUI, Radix wrappers, custom UI, and one-off components without a design layer.

### Backend

Use a modular Python backend:

- FastAPI remains a good choice.
- Python 3.12+.
- Pydantic v2.
- Beanie/Mongo can stay initially, but the company platform may eventually benefit from Postgres.
- Redis for OTP, queues, short-lived session state, rate limits.
- Celery/RQ/Arq/Temporal-style workers for long-running AI jobs.
- OpenAI Responses API / Agents SDK for structured AI workflows.
- OpenAI Realtime API for direct realtime voice experiments.
- LiveKit Agents for production live interview rooms.
- Temporal for durable, retryable AI and interview workflows once the platform has company scheduling, recordings, reports, and live sessions.
- S3-compatible object storage for resumes, recordings, generated reports.
- OpenTelemetry + Sentry for tracing and error monitoring.

Database recommendation:

- Short term: keep MongoDB to avoid blocking the rebuild.
- Medium term: move core company/interview scheduling data to Postgres if reporting, filtering, permissions, and analytics become complex.
- Keep raw transcripts, event logs, and AI artifacts in document/object storage.

### AI/Voice

Use separate AI layers:

- Interview Planner: creates a structured interview plan.
- Question Generator: creates initial and backup questions.
- Interview Conductor: decides follow-ups and pacing.
- Evaluator: scores against rubric.
- Report Writer: creates candidate/company-facing summaries.
- Memory Service: retrieves useful prior context.
- Guardrails: checks fairness, unsafe questions, leakage, and hallucinated criteria.
- Integrity Analyzer: flags anti-cheat and proctoring signals with timestamped evidence.

For voice:

- Static/asynchronous mode: STT -> text reasoning -> TTS, because it is easier to debug and evaluate.
- Live mode: LiveKit Agents + OpenAI Realtime for natural speech-to-speech rooms.

Relevant docs:

- LiveKit Agents supports Python/Node realtime AI apps, WebRTC frontends, OpenAI Realtime bridging, interruption handling, noise cancellation, and synced transcription: https://docs.livekit.io/agents/integrations/openai/
- OpenAI voice agents support speech-to-speech and chained voice pipelines; speech-to-speech is best for natural low-latency conversations, chained workflows are better when intermediate transcript/control is required: https://developers.openai.com/api/docs/guides/voice-agents
- OpenAI Agents SDK voice layer wraps realtime sessions, tools, guardrails, handoffs, and session history: https://openai.github.io/openai-agents-js/guides/voice-agents/

## Product Architecture

### Core Domains

The backend should be split into domain modules:

- `auth`: OTP, sessions, JWT, company/user identity.
- `users`: candidate profile, preferences, resume, memory.
- `companies`: company profile, workspace, billing, recruiters.
- `jobs`: job roles, openings, competencies, criteria.
- `interview_templates`: interview structure, rubrics, required questions.
- `interview_sessions`: scheduled interviews, links, live/static execution.
- `interview_turns`: questions, answers, transcript, timing, events.
- `evaluations`: scorecards, evidence, recommendations, shortlist status.
- `recordings`: audio/video assets, consent, retention policy.
- `integrity`: proctoring signals, anti-cheat events, risk scoring, review evidence.
- `notifications`: email invites, reminders, completion emails.
- `billing`: Razorpay, credits, invoices, plans.
- `ai`: model clients, prompt/agent definitions, structured outputs, evals.
- `live`: LiveKit room/token management and agent orchestration.

### High-Level System

```txt
Frontend App
  Candidate Portal
  Company Dashboard
  Recruiter Review Console
  Live Interview Room

Backend API
  Auth / RBAC
  Company / Candidate / Jobs
  Interview Templates
  Scheduling
  Interview Sessions
  Evaluation and Reports
  LiveKit Token Service

Workers
  Resume Extraction
  Question Planning
  Static Interview Analysis
  Report Generation
  Email Delivery
  Recording Processing

AI Services
  Planner
  Conductor
  Evaluator
  Report Writer
  Memory Retriever
  Guardrails
  Integrity Analyzer

External Services
  OpenAI
  LiveKit
  Email provider
  S3/object storage
  Razorpay
  Observability
```

## Data Model Direction

### Company Platform Entities

```txt
Company
  id
  name
  logo
  domain
  settings

CompanyMember
  id
  company_id
  user_id
  role: owner | admin | recruiter | interviewer | reviewer

JobOpening
  id
  company_id
  title
  department
  location
  employment_type
  description
  status

InterviewTemplate
  id
  company_id
  job_opening_id
  name
  round_type
  duration_minutes
  competencies
  rubric
  required_questions
  optional_question_bank
  disqualifiers
  ideal_candidate_profile

Candidate
  id
  company_id
  name
  email
  phone
  resume_asset_id
  profile_summary
  source

InterviewSession
  id
  company_id
  job_opening_id
  template_id
  candidate_id
  mode: static | live_ai | live_human_ai | human_only
  status: draft | scheduled | invited | in_progress | completed | reviewed | shortlisted | rejected
  scheduled_at
  invite_token
  livekit_room_name
  created_by

InterviewTurn
  id
  session_id
  turn_index
  speaker: ai | candidate | human_interviewer
  question_id
  text
  transcript
  audio_asset_id
  video_timestamp
  start_time
  end_time
  metadata

Evaluation
  id
  session_id
  overall_score
  recommendation
  rubric_scores
  evidence
  strengths
  concerns
  followup_questions
  generated_at
  reviewed_by

IntegritySignal
  id
  session_id
  signal_type
  severity: low | medium | high
  evidence
  timestamp
  confidence
  source: browser | audio | video | transcript | reviewer | model

IntegrityReport
  id
  session_id
  risk_level: low | medium | high
  summary
  signals
  reviewer_notes
  final_status: clear | needs_review | disqualified

CandidateMemory
  id
  candidate_user_id
  summary
  strengths
  repeated_weaknesses
  recent_interviews
  embeddings
```

### Rubric Shape

A company should be able to express what it wants:

```json
{
  "competencies": [
    {
      "name": "Backend API Design",
      "weight": 25,
      "signals": [
        "Designs clear contracts",
        "Discusses error handling",
        "Mentions observability and scaling"
      ],
      "red_flags": [
        "Cannot explain tradeoffs",
        "Ignores data consistency"
      ]
    }
  ],
  "must_have": ["Python", "FastAPI", "Postgres"],
  "nice_to_have": ["Kubernetes", "Event-driven systems"],
  "disqualifiers": ["No production backend experience"],
  "ideal_candidate_notes": "Has built customer-facing APIs and can reason through scale."
}
```

## Stage 0: Foundation Audit And Stabilization

Goal: make the current repo safer before larger changes.

Backend work:

- Fix route bugs, especially payment status path.
- Replace embedded Beanie `Document` classes with Pydantic models where appropriate.
- Remove dynamic model discovery and `eval` from database initialization.
- Centralize settings with `pydantic-settings`.
- Move hard-coded bucket names, model names, origins, and prices into config.
- Add proper logging and request IDs.
- Add basic tests for critical flows.
- Clean dependencies.
- Remove committed credentials and old deployment naming.
- Add `.env.example`.

Frontend work:

- Convert high-change areas to TypeScript.
- Centralize API client.
- Replace localStorage direct access with an auth/session helper.
- Add route-level error boundaries.
- Normalize toast/error handling.
- Fix inconsistent branding/package naming.

Deliverable:

- Current product still works.
- Codebase is safer to modify.
- New architecture can be introduced incrementally.

## Stage 1: Interview Engine V1

Goal: improve static interview quality before live mode.

Build a new AI interview engine with these steps:

1. `InterviewPlanner`
   - Inputs: role, experience, resume summary, company, job description, template, prior memory.
   - Output: structured interview plan.

2. `QuestionSetGenerator`
   - Generates planned questions.
   - Produces backup questions.
   - Tags each question with competency, difficulty, and evaluation intent.

3. `AnswerEvaluator`
   - Scores each answer against the intended competency.
   - Extracts evidence from transcript.
   - Avoids generic feedback.

4. `ReportGenerator`
   - Produces candidate-facing report.
   - Produces recruiter-facing scorecard.
   - Separates confidence from competence.

5. `QualityGuardrails`
   - Checks question relevance.
   - Prevents illegal/discriminatory interview questions.
   - Ensures rubrics and scoring match the role.

Use structured outputs for every AI response. No raw JSON-in-text parsing as the primary path.

Static interview upgrades:

- Adaptive follow-up question after weak or vague answers.
- Difficulty progression.
- Per-question intent.
- Resume deep-dive questions.
- Company/job description aware questions.
- Stronger speech analysis with evidence.
- Better retry/recovery when transcription fails.

Deliverable:

- Static interviews feel much smarter.
- Reports are more specific and defensible.
- The engine is reusable for company and live flows.

## Stage 2: Company Platform MVP

Goal: create the revenue-oriented workflow.

Company features:

- Company signup/login.
- Company workspace.
- Invite recruiters/interviewers.
- Create job opening.
- Create interview template.
- Add required questions.
- Add candidate criteria.
- Add disqualifiers and preferred signals.
- Upload or paste job description.
- Create candidate.
- Send interview link by email.
- View interview status.
- View transcript, recording, and scorecard.
- Shortlist/reject candidate.

Candidate features:

- Candidate receives secure invite link.
- Candidate sees company/role/interview instructions.
- Candidate completes interview without needing a full account.
- Candidate gives recording consent.
- Candidate can optionally create an account after completion.

Backend requirements:

- Role-based access control.
- Invite tokens with expiry.
- Audit logs for recruiter actions.
- Email templates and delivery tracking.
- Candidate privacy and retention settings.
- Company-level data isolation.

Frontend requirements:

- Company onboarding.
- Dashboard with open jobs and active interviews.
- Interview template builder.
- Candidate list.
- Candidate detail page.
- Scorecard/review page.
- Shareable report links.

Deliverable:

- A company can run an async AI screening interview end-to-end.
- This creates a credible revenue path before live voice complexity.

## Stage 3: Human Review And Human Join

Goal: make the product useful for real hiring teams.

Features:

- Recruiter review queue.
- Human comments on candidate answers.
- Score override with reason.
- Candidate comparison table.
- Shortlist based on configured criteria.
- Human interviewer can join a scheduled room.
- Human can observe silently or participate.
- AI can summarize human-led interviews.

Human join options:

1. Static/async interview review only.
2. Live room with candidate + human interviewer.
3. Live room with candidate + AI interviewer + optional human observer.
4. Live room where human can take over from AI.

This stage should introduce recording and consent flows properly.

Deliverable:

- Companies trust the system because humans can inspect, override, and participate.

## Stage 3.5: Interview Integrity And Anti-Cheat

Goal: make company interviews trustworthy without damaging candidate experience.

Anti-cheat should be implemented as an integrity layer, not as automatic punishment. The system should collect signals, explain them, and let companies decide how strict they want to be.

### Static/Async Interview Integrity

Browser-side signals:

- Tab switch and window blur events.
- Copy/paste into answer fields if typed answers exist.
- Fullscreen exit or permission changes.
- Unusual session pauses.
- Repeated recording restarts.
- Camera or microphone disabled during required recording.

Video signals:

- Face not visible.
- Multiple faces.
- Candidate frequently looking away.
- Camera blocked or turned off.
- Identity mismatch where ID verification is explicitly enabled.

Audio signals:

- Second speaker detected.
- Background prompting.
- Text-to-speech playback artifacts.
- Long unnatural pauses.
- Audio/video desync.

Transcript/content signals:

- Answer appears copied from generic web or LLM style.
- Answer ignores the question but sounds polished.
- Sudden quality jump compared with earlier answers.
- Repeated template phrasing across candidates.
- Possible prompt-injection attempts.

Recording post-processing:

- Generate timestamped integrity events.
- Attach evidence snippets, not just a score.
- Let reviewers jump to suspicious moments in playback.
- Include a confidence level for every signal.

### Live Interview Integrity

Realtime signals:

- Candidate leaves tab or room.
- Candidate muted/unmuted patterns.
- Camera off during required live interview.
- Multiple voices detected.
- AI/human interviewer detects delayed reading behavior.
- Live transcript shows pasted/scripted style.
- Candidate asks for repeated long pauses.
- Network disruptions that cluster around hard questions.

Live responses:

- Soft warning to candidate when policy allows.
- Silent flag for recruiter review.
- Human observer can join.
- AI can ask a clarifying follow-up to verify understanding.
- Do not auto-fail except for explicit company policy violations.

### Integrity UX

Candidate experience:

- Show clear consent before recording/proctoring.
- Explain what is monitored.
- Avoid fear-based language.
- Provide a test camera/mic step.
- Allow legitimate accessibility accommodations.

Company experience:

- Integrity score is separate from interview score.
- Show evidence by timestamp.
- Allow configurable strictness by interview template.
- Allow reviewer override.
- Keep an audit log of integrity decisions.

### Privacy And Compliance

Rules:

- Get explicit recording and proctoring consent.
- Store only necessary integrity artifacts.
- Define retention periods per company.
- Avoid biometric claims unless legally reviewed.
- Do not use face recognition by default.
- Prefer "face presence" and "multiple faces" over identity claims unless ID verification is a paid/consented feature.
- Make integrity scoring explainable and reviewable.

### Implementation Approach

Start simple:

1. Browser tab/window events.
2. Recording availability and camera/mic health.
3. Timestamped transcript/audio anomalies.
4. Reviewer-facing integrity report.

Then add:

1. Face presence and multiple-face detection.
2. Multi-speaker detection.
3. LLM-style answer anomaly detection.
4. Live warning/review policies.
5. Optional identity verification.

Deliverable:

- Companies can trust interviews more.
- Candidates understand the rules.
- Reviewers get evidence, not black-box accusations.

## Stage 4: Live AI Interview MVP

Goal: launch a live experience that feels meaningfully better than static.

Recommended architecture:

- LiveKit room for candidate/interviewer media.
- Backend creates room and access tokens.
- LiveKit Agent joins as AI interviewer.
- Agent uses the same Interview Engine from Stage 1.
- Agent emits events to backend:
  - `session_started`
  - `question_asked`
  - `candidate_answer_started`
  - `candidate_answer_transcript_delta`
  - `candidate_answer_completed`
  - `followup_selected`
  - `rubric_signal_detected`
  - `session_completed`
- Backend persists turns and events.
- Evaluator runs after the session, with optional lightweight real-time notes.

Why LiveKit:

- It solves WebRTC room infrastructure.
- It supports real browser/mobile frontends.
- It allows human participants to join.
- It integrates with OpenAI Realtime.
- It supports interruption handling, state coordination, and transcription sync.
- It leaves room for telephony later.

Voice experience goals:

- Natural turn taking.
- Candidate can interrupt.
- AI does not speak over candidate.
- Clear interviewer persona.
- Low first-audio latency.
- Real-time transcript.
- Visual speaking/listening states.
- Graceful recovery when audio drops.

Start with one interview type:

- Role-based behavioral + technical screening.
- 20-30 minute duration.
- 5-8 planned questions with adaptive follow-ups.

Do not start with every role, every company setting, and every live mode. Make one live flow excellent.

Deliverable:

- Live AI interview room with candidate + AI.
- Persistent transcript.
- End-of-session company scorecard.
- Latency and quality metrics.

## Stage 5: Premium Live Experience

Goal: get close to a human interviewer feel.

Enhancements:

- Better interviewer persona configuration.
- More natural voice selection.
- Candidate pacing and confidence coaching.
- Follow-up question timing.
- Mid-interview adaptation.
- Real-time notes visible to human observer.
- Post-interview highlight reel.
- Searchable transcript.
- Video/audio recording playback.
- Recruiter bookmarks.
- Red flag detection with evidence.
- Bias/fairness checks.
- Human takeover.
- Multi-agent interview panels, such as:
  - recruiter agent
  - technical agent
  - behavioral agent
  - evaluator agent

Live quality metrics:

- Time to first AI audio.
- End-of-candidate-speech to AI response latency.
- Interruption success rate.
- Transcript accuracy.
- Question relevance score.
- Candidate completion rate.
- Recruiter usefulness rating.

Deliverable:

- A live interview that feels like a polished AI interviewer, not an audio demo.

## Stage 6: Memory And Learning System

Goal: make MockAI improve over time for both candidates and companies.

Candidate memory:

- Last interview summary.
- Repeated strengths.
- Repeated weaknesses.
- Role interests.
- Resume/project context.
- Practice history.
- Improvement trajectory.

Company memory:

- Hiring criteria by role.
- Successful candidate patterns.
- Interview template performance.
- Recruiter preferences.
- Rejected/shortlisted signal analysis.
- Calibration examples.

Memory rules:

- Always separate candidate-owned memory from company-owned interview data.
- Do not leak one company's criteria to another.
- Let users delete memory.
- Keep evidence references for important claims.
- Use memory for personalization, not hidden unfair scoring.

Deliverable:

- Returning users get better practice.
- Companies get calibrated, repeatable interviews.

## Stage 7: Analytics, Evaluation, And Moat

Goal: create defensible interview quality.

Build internal evals:

- Question relevance eval.
- Rubric adherence eval.
- Feedback specificity eval.
- Hallucination eval.
- Fairness/safety eval.
- Transcript-to-score evidence eval.
- Recruiter satisfaction eval.
- Candidate experience eval.

Create a gold dataset:

- Example resumes.
- Job descriptions.
- Candidate answers.
- Human-labeled scores.
- Good/bad feedback examples.
- Company-specific rubric examples.

Use this to test every model/prompt/agent change.

Deliverable:

- You can improve AI quality without guessing.

## Frontend Product Surfaces

### Candidate Practice App

- Dashboard.
- Resume/profile.
- Static interview.
- Live interview.
- Reports.
- Progress history.
- Recommended practice plan.

### Company App

- Workspace dashboard.
- Jobs.
- Candidates.
- Interview templates.
- Scheduling/invites.
- Live interview monitor.
- Candidate review.
- Scorecards.
- Shortlists.
- Settings/team/billing.

### Interview Room

- Candidate video.
- AI/human interviewer panel.
- Live transcript.
- Current question.
- Timer.
- Connection quality.
- Consent indicator.
- End session.
- Optional human observer controls.

### Recruiter Review Console

- Candidate profile.
- Resume.
- Recording playback.
- Transcript by question.
- AI scorecard.
- Evidence snippets.
- Human notes.
- Shortlist/reject action.
- Compare candidates.

## Backend Service Design

### API Layer

Keep route handlers thin:

- Validate input.
- Authorize action.
- Call service.
- Return response.

### Service Layer

Business workflows live here:

- `CreateCompanyInterviewTemplate`
- `ScheduleCandidateInterview`
- `StartStaticInterview`
- `StartLiveInterview`
- `CompleteInterview`
- `GenerateEvaluation`
- `ShortlistCandidate`

### AI Layer

AI should be versioned:

```txt
ai/
  planners/
    interview_planner_v1.py
  conductors/
    static_conductor_v1.py
    live_conductor_v1.py
  evaluators/
    rubric_evaluator_v1.py
  reports/
    candidate_report_v1.py
    recruiter_scorecard_v1.py
  schemas/
    interview_plan.py
    evaluation.py
  prompts/
    interview_planner/
    answer_evaluator/
    live_conductor/
  workflows/
    interview_completed.py
    live_post_processing.py
```

Every AI output should have:

- Schema.
- Version.
- Model name.
- Prompt version.
- Prompt cache key.
- Input hash/reference.
- Token usage.
- Cached token usage.
- Latency.
- Raw output artifact.
- Parsed output.
- Validation result.

## Suggested Repository Shape

```txt
mockai-backend/
  app/
    main.py
    core/
      config.py
      logging.py
      security.py
      errors.py
    db/
      mongo.py
      models/
    api/
      routes/
        auth.py
        users.py
        companies.py
        jobs.py
        interview_templates.py
        interview_sessions.py
      evaluations.py
        integrity.py
        live.py
        billing.py
    services/
      auth_service.py
      company_service.py
      interview_service.py
      evaluation_service.py
      notification_service.py
      billing_service.py
    ai/
      clients/
      planners/
      conductors/
      evaluators/
      reports/
      integrity/
      schemas/
      evals/
    integrations/
      livekit.py
      openai.py
      razorpay.py
      email.py
      storage.py
    workers/
      tasks.py
    tests/
```

Frontend:

```txt
mockai-frontend/
  src/
    app/
    routes/
    features/
      auth/
      candidate/
      company/
      interviews/
      integrity/
      live-room/
      reports/
      billing/
    components/
      ui/
      layout/
      charts/
    lib/
      api/
      auth/
      query/
      livekit/
      validation/
    styles/
```

## Build Order

### Milestone 1: Clean Core

- Settings/config.
- Model cleanup.
- API client cleanup.
- Structured AI responses.
- Pydantic schemas for AI outputs.
- Prompt version folder.
- Token/cost/latency logging for AI calls.
- Static interview still works.

### Milestone 2: Better Static Interview

- Interview plan.
- Question intents.
- Rubric scoring.
- Evidence-based report.
- Candidate memory v1.
- Prompt caching layout with stable system prefixes.
- Model routing by task complexity.
- AI eval cases for planner and evaluator quality.

### Milestone 3: Company MVP

- Company signup.
- Company dashboard.
- Job openings.
- Interview templates.
- Candidate invites.
- Async interview completion.
- Recruiter scorecard.
- Durable workflow runner if invite/report/email steps need retries and observability.

### Milestone 4: Review And Shortlist

- Recording/transcript review.
- Human notes.
- Shortlist/reject.
- Candidate comparison.
- Criteria-based filtering.

### Milestone 5: Integrity MVP

- Candidate consent and proctoring disclosure.
- Browser tab/window event capture.
- Camera/mic health timeline.
- Basic recording anomaly detection.
- Timestamped integrity report.
- Reviewer evidence view.
- Company-level strictness settings.

### Milestone 6: LiveKit MVP

- LiveKit token service.
- Candidate live room.
- AI agent joins room.
- Live transcript.
- Persisted session events.
- End summary.
- Realtime prompt and turn-taking evals.
- Post-live Temporal workflow for transcript cleanup, scoring, recording processing, and emails.
- Realtime integrity signals for tab leave, room leave, muted/camera-off behavior, and multi-speaker hints.

### Milestone 7: Human Join

- Human interviewer/observer join.
- Human takeover.
- AI note-taker mode.
- Human-led interview summary.

### Milestone 8: High-Quality Live

- Better voice.
- Lower latency.
- Interruptions.
- Multi-agent panels.
- Live score hints.
- Calibration/evals.
- Advanced integrity checks with evidence-first review.

## What To Avoid

- Do not make LiveKit the core product architecture. It is the live media layer.
- Do not keep adding prompts inside route handlers.
- Do not build company flows as a thin wrapper around candidate mock interviews.
- Do not score candidates without evidence.
- Do not let static and live interviews have totally separate evaluation logic.
- Do not launch live interviews without recording consent and retention policy.
- Do not launch company screening without consented integrity/proctoring policies.
- Do not auto-reject candidates from black-box anti-cheat scores.
- Do not use memory in ways recruiters cannot understand or audit.

## Experience Bar

The upgraded product should feel like:

- For candidates: "This interview understood my background and challenged me fairly."
- For companies: "This saved us screening time and gave us a defensible, reviewable scorecard."
- For live interviews: "The AI interviewer was responsive, natural, and stayed on the hiring criteria."

## Immediate Next Step

Start with Stage 0 and Stage 1 together:

1. Create the new backend structure.
2. Add settings and clean model definitions.
3. Build the Interview Engine V1 behind the existing static interview UI.
4. Keep the existing routes temporarily as compatibility wrappers.
5. Once the new engine works, build the company dashboard and template system on top of it.

This lets the current product improve immediately while laying the foundation for company revenue and live interviews.

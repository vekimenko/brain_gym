# Brain Gym Implementation Plan

## Objective
Build a modular active-reading app that supports both live and offline study loops, persists progress in SQLite, and can evolve into a richer product with scheduling, analytics, and UI layers.

## Target user experience
The app should let a user:
- Provide an article source (URL, YouTube transcript, file, or pasted text)
- Generate questions grounded in the source material
- Answer questions live or later from saved sets
- Receive automated scoring with correctness, completeness, clarity, and evidence-use metrics
- Receive targeted feedback and hints for improvement
- Retry weak questions until the user reaches a target score or skips them
- Continue with follow-up questions tied to missed content
- Revisit missed concepts across sessions with a spaced-repetition flow

## Product goals
1. Keep the existing active-reading workflow working in a stable, testable way.
2. Add a persistent SQLite-based session store for progress and history.
3. Support both live and offline modes with a clear, consistent CLI.
4. Design the app to make later web or desktop expansion straightforward.
5. Prepare the structure for feature flags, advanced scheduling, and analytics.

## High-level architecture

### 1. App layer
- CLI entrypoints for user interactions
- Session orchestration
- Source ingestion and article validation
- Mode selection (`live`, `offline`, `mixed`, `review`)
- Output formatting for progress, summaries, and hints

### 2. Domain layer
- `ArticleSource`
- `Session`
- `Question`
- `Attempt`
- `Grade`
- `ReviewItem`
- `ProgressSnapshot`

### 3. Services layer
- `ArticleLoader`: fetch and normalize article text from URL, file, transcript, or text input
- `QuestionGenerator`: produce grounded questions, optionally focused on weak points
- `AnswerJudge`: evaluate answer quality using rubric metrics
- `ProgressStore`: save/load sessions and attempts
- `ReviewScheduler`: schedule weak topics for future practice
- `RecommendationEngine`: choose the next question or follow-up focus

### 4. Data layer
SQLite tables and schema to support:
- `sessions`
- `questions`
- `attempts`
- `grades`
- `sources`
- `review_queue`
- `metrics_summary`
- `user_preferences`

### 5. Future UI layer
- Optional web frontend using FastAPI or Flask
- Optional desktop app shell (Tauri / Electron / PyQt)
- Shared backend API for both frontends

## Feature set

### Feature group A — Core active reading
- Article upload from URL, file, YouTube transcript, or pasted text
- Question generation with requested depth and count
- Structured answer grading
- Feedback and hint generation
- Retry loop for live questions
- Follow-up question generation based on missed points
- Session summary and saved history

### Feature group B — Offline and review workflow
- Save generated bank to SQLite
- Allow user to answer stored questions later
- Grade saved answers in batch
- Resume or continue sessions
- Review only weak points from prior sessions
- Human-in-the-loop answer entry from DB browser or CLI
- Optional offline grading using a local sentence-transformer model and key-point coverage checks
- Persist `key_points` alongside each saved question so a later grading pass can run without LLM access

### Feature group C — Progress intelligence
- Track per-question and per-session scoring trends
- Compute averages, streaks, weakest topic areas
- Support review scheduling with spaced repetition logic
- Detect repeated mistakes and re-target them

### Feature group D — Advanced options
- Mixed mode: generate a bank once and then either live or offline practice
- Difficulty ladder: adjust question complexity based on score
- Spaced repetition: schedule reviews at progressive intervals
- Multimodal source support: article text + notes + transcript context
- Personalization: user goals, subject areas, question preferences
- Web or desktop frontend

## Phase plan

### Phase 0 — Baseline audit and cleanup
Goals:
- Confirm current script behavior and identify retained logic worth preserving
- Separate model logic from app logic
- Define the minimum stable API to implement before broader features

Steps:
1. Inventory current script responsibilities
2. Identify reusable functions for article loading, LLM calls, and grading
3. Decide which features belong in v1 vs later phases
4. Freeze the CLI contract for live/offline modes

Outputs:
- Shared service boundary map
- App feature scope document
- MVP CLI specification

### Phase 1 — App skeleton and persistence
Goals:
- Establish a clean app structure and SQLite schema
- Enable session creation and tracking

Steps:
1. Create packages/modules:
   - `app/cli.py`
   - `app/session_manager.py`
   - `app/config.py`
   - `app/models.py`
   - `app/db.py`
   - `services/article_loader.py`
   - `services/question_service.py`
   - `services/grading_service.py`
   - `services/review_service.py`
2. Define SQLite migration/bootstrap logic
3. Create tables for sessions, questions, attempts, grades, review queue
4. Add helper queries for pending questions, scored attempts, and weak-point summaries
5. Add CLI entrypoint with `--mode` support and required source arguments

Outputs:
- Bootstrapped app shell
- SQLite schema ready for development
- Basic session creation flow

### Phase 2 — Core live flow
Goals:
- Support the interactive practice loop end-to-end

Steps:
1. Implement article source loading from URL/file/text/Youtube
2. Build question generation from source text
3. Present the user with one question at a time
4. Capture answer input from terminal
5. Call LLM grading service
6. Save attempt and grade records to SQLite
7. Show feedback + hint + missed points
8. Retry loop until score threshold or skip
9. Continue with new questions until user exits
10. Save final session status and summary

Outputs:
- Working live study mode
- Persisted attempt and grading history
- Session summary output

### Phase 3 — Core offline flow
Goals:
- Support generated question sets stored for later answer entry

Steps:
1. Save a question bank to SQLite with status metadata
2. Allow retrieval of pending questions by session
3. Allow answer entry through CLI or manual DB interaction
4. Grade answers in batch using the same LLM judge logic
5. Save per-question metrics and missed points
6. Generate follow-up questions targeting previously missed content
7. Record completed offline session state
8. Add an `--offline-grading` mode that uses sentence-transformer similarity and key-point coverage without an LLM call
9. Store `key_points` per question and allow `--session-id` resumption of any unfinished offline session

Outputs:
- Working offline study mode
- Database-driven question and answer lifecycle
- Local, offline grading path that preserves the same scoring structure as the LLM-based evaluator

### Phase 4 — Review and weak-point loop
Goals:
- Turn the app into a genuine learning system rather than a single pass

Steps:
1. Store missed-point tags from each grade
2. Aggregate those tags across sessions
3. Build a `review_queue` that prioritizes repeated misses
4. Optionally allow the user to review only the weakest concepts
5. Generate follow-up questions that reference previously missed ideas
6. Label sessions as `new`, `review`, or `mastered`
7. Add score thresholds to mark a concept as sufficiently learned

Outputs:
- Weighted weak-point review loop
- Repeat-focused training behavior

### Phase 5 — Spaced repetition and scheduling
Goals:
- Add retention-oriented review cadence

Steps:
1. Define review intervals: 1 day, 3 days, 7 days, 14 days, 30 days
2. Track next_review_at timestamps per concept/question
3. Prioritize items that are due soon or have high error frequency
4. Implement a scheduler that surfaces due items before new ones
5. Provide optional `--review` command to launch due review sessions
6. Extend metrics to include mastery trend over time

Outputs:
- Due-item scheduler
- Spaced repetition mode

### Phase 6 — Analytics and personalization
Goals:
- Turn user performance into actionable recommendations

Steps:
1. Aggregate per-topic performance across questions and sessions
2. Compute average correctness, completeness, and clarity by level
3. Track mastery score per question cluster or topic cluster
4. Recommend question difficulty, review cadence, and focus areas
5. Identify patterns like recurring confusion or answer-length issues
6. Allow per-user preference tuning: target score, review volume, tone of feedback

Outputs:
- Progress dashboard data model
- Recommendation engine
- Session analytics summary

### Phase 7 — Mixed mode and UI readiness
Goals:
- Prepare for non-CLI experiences

Steps:
1. Add `mixed` mode: generate a set, then let the user choose live/offline practice
2. Add command to resume incomplete sessions
3. Build API layer for a web UI or desktop shell
4. Ensure all session operations are backend-driven and serializable
5. Add config-driven environment variables for LLM model selection and review rules

Outputs:
- Mixed-mode flows
- Backend ready for UI integration

### Phase 8 — Optional web app or desktop shell
Goals:
- Provide a more user-friendly interface

Web app options:
- FastAPI + SQLite + HTML/JS frontend
- Machine-friendly API endpoints:
  - `/sessions/create`
  - `/sessions/{id}/questions`
  - `/questions/{id}/answer`
  - `/grades/{id}`
  - `/sessions/{id}/summary`

Desktop options:
- Tauri or Electron for local app shell
- Browser-style UI backed by the same SQLite and service layer

Outputs:
- UI front-end ready to use with same backend logic
- Reduced user friction for ongoing learning sessions

## Additional options and expansions

### 1. Mixed mode
Use case:
- Generate once, then let user decide whether to answer immediately or later

Implementation:
- Create a session with `mode = mixed`
- Store generated questions with a status of `ready`
- Let user pick `live`, `manual answer entry`, or `batch judge`
- Reuse same services for generation and grading

### 2. Difficulty ladder
Use case:
- Adjust question complexity to the user’s ability

Implementation:
- Score each answer and classify as `easy`, `medium`, `hard`
- Raise or lower difficulty thresholds based on score trend
- Select question level distribution dynamically:
  - low score => more recall/support tasks
  - high score => more inference/synthesis tasks

### 3. Spaced repetition review
Use case:
- Revisit missed material at increasing intervals

Implementation:
- Track `last_reviewed_at` and `next_review_at`
- On each grade, update a retention score
- Re-prioritize when due
- Recommend due items before brand-new material

### 4. Multi-source context blending
Use case:
- Learn from article + notes + transcript together

Implementation:
- Allow a session to include additional context text or note attachments
- Add a source-type value to the database
- Blend all context into prompt generation
- Keep each question tagged to the source or evidence it came from

### 5. Personalization and user profiles
Use case:
- Tailor question style and target difficulty to each user

Implementation:
- Add `user_preferences` table
- Include learning goals, preferred question counts, preferred difficulty range
- Save continuous tuning observations to user profile

### 6. Web or desktop front-end
Use case:
- Better UX than the terminal workflow

Implementation:
- Use the same backend services but wrap them in HTTP endpoints or desktop IPC calls
- Maintain session state in SQLite to avoid losing progress
- Let UI handle display of progress metrics, hints, and review queue

## Recommended implementation sequence

1. Stabilize CLI and app structure
2. Build SQLite schema and session lifecycle
3. Implement live mode
4. Implement offline mode
5. Add weak-point review loop
6. Add spaced repetition
7. Add analytics and recommendations
8. Add mixed mode and UI options

## Risks and mitigations

### Risk: LLM output variability
Mitigation:
- Use structured JSON prompts
- Validate response shape before persisting
- Add retry/fallback logic for malformed responses

### Risk: Incomplete app boundaries
Mitigation:
- Separate service and domain code early
- Keep database and CLI orchestration decoupled from LLM prompting details

### Risk: Review logic becomes too complex too early
Mitigation:
- Start with simple missed-point aggregation
- Add scheduling only after core live/offline flows work reliably

### Risk: Scope creep from optional features
Mitigation:
- Prioritize `core + review + scheduling` before web UI
- Put non-essential features behind explicit milestones

## Definition of done for MVP
The MVP is complete when:
- A user can run live mode end-to-end with a file or URL input
- A user can run offline mode end-to-end with saved SQLite questions
- Questions are generated, answered, and graded with metrics
- Progress is saved in SQLite
- Weak points can drive follow-up question generation
- The CLI help and app entrypoints behave consistently

## Definition of done for v2
The v2 release is complete when:
- Spaced repetition is active
- Review queue and analytics are functioning
- Mixed mode is supported
- The backend is ready for UI integration

## Suggested next-session task breakdown

### Session 1
- Build app module structure
- Create database bootstrap and schema
- Connect article loading to the CLI

### Session 2
- Implement live flow end-to-end
- Add score and hint output

### Session 3
- Implement offline flow and question bank persistence

### Session 4
- Add review loop and missed-point follow-up generation

### Session 5
- Add spaced repetition and scheduling

### Session 6
- Add analytics and recommendation data model

### Session 7
- Add mixed mode and UI API layer

## Success metrics
- Live mode completes without data loss
- Offline mode reliably saves and grades stored questions
- Follow-up question generation uses previous misses effectively
- Review flow reduces repeated mistakes over time
- App remains modular for the next feature iteration

## Open design decisions to confirm later
1. Should question generation produce one question at a time or batches?
2. Should the app support multiple users or a single-user local profile?
3. Should review scheduling be based on concept clusters or individual question IDs?
4. Should the final user-facing product be terminal-first or UI-first?
5. Should the project keep using the current `reading_sessions.db` file or introduce a dedicated app database?

## Appendix: example roadmap summary
- MVP: live + offline + persistence
- v1.1: review and weak-point loops
- v1.2: spaced repetition and analytics
- v2: mixed mode and web/desktop UI

## Implementation notes
- Keep the domain model explicit and small
- Prefer SQLite tables that map directly to user workflows rather than overly normalized schema early
- Maintain prompt and grading logic as service functions that can be unit-tested separately
- Add API contracts for future UI consumption before frontend work begins

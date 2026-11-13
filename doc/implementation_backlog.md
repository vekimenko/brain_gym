# Brain Gym Detailed Implementation Backlog

## 1. Product objective
Build a modular active-reading application that supports:
- live practice mode
- offline question-bank mode
- review mode for weak points
- spaced repetition and adaptive scheduling
- optional web/desktop frontend in a later phase
- offline grading for saved question banks without requiring external API access

The product must be SQLite-first, LLM-assisted, and structured so each workflow can be tested independently.

## 2. Delivery principles
- Keep the LLM logic isolated from the app flow.
- Separate domain models from persistence and CLI orchestration.
- Use SQLite as the source of truth for progress and review state.
- Prefer iterative delivery: core live flow first, then offline, then review/repetition, then UI.
- Design every module to support future extension without a rewrite.

## 3. Target file and module structure

```text
brain_gym/
├── brain_gym_app.py                  # top-level CLI entrypoint
├── README.md                         # project usage and onboarding
├── requirements.txt                  # runtime deps
├── .env.example                      # environment variables
├── app/
│   ├── __init__.py
│   ├── cli.py                        # argument parsing and command dispatch
│   ├── config.py                     # env/config resolution
│   ├── session_orchestrator.py        # orchestrates live/offline/review flows
│   ├── state.py                      # in-memory session state if needed
│   └── output.py                     # formatted printing, summaries, prompts
├── core/
│   ├── __init__.py
│   ├── models.py                     # Question, Attempt, Grade, Session, ReviewItem
│   ├── enums.py                      # Mode, Status, Difficulty, ReviewCadence
│   └── schemas.py                    # validation helpers / dataclasses
├── db/
│   ├── __init__.py
│   ├── bootstrap.py                  # ensure schema exists
│   ├── schema.sql                    # canonical SQL schema
│   ├── repo.py                       # query and persistence helpers
│   ├── migrations.py                 # future migration system
│   └── seed.py                       # demo/test data generation
├── services/
│   ├── __init__.py
│   ├── article_loader.py             # fetch URLs, transcripts, files, inline text
│   ├── llm_client.py                 # OpenAI-compatible client wrapper
│   ├── question_service.py           # generate and validate questions
│   ├── grading_service.py            # rubric grading and hints
│   ├── review_service.py             # weak-point and review-queue logic
│   ├── scheduler.py                  # spaced repetition intervals
│   ├── analytics.py                  # aggregate metrics and progress trends
│   └── recommendations.py            # decide next best question or review target
├── workflows/
│   ├── __init__.py
│   ├── live_mode.py                  # run live question-answer loop
│   ├── offline_mode.py               # generate and answer saved questions
│   ├── review_mode.py                # focused weak-point review
│   ├── mixed_mode.py                 # generate once; user chooses how to practice
│   └── resume_mode.py                # reopen incomplete sessions
├── scripts/
│   ├── reset_db.py                   # development reset helper
│   ├── demo_run.py                   # sample/demo session runner
│   └── export_session.py             # export session JSON/CSV if needed
├── tests/
│   ├── test_article_loader.py
│   ├── test_question_service.py
│   ├── test_grading_service.py
│   ├── test_review_service.py
│   ├── test_scheduler.py
│   ├── test_cli.py
│   └── test_db_repo.py
├── ui/
│   ├── __init__.py
│   ├── api.py                        # optional FastAPI backend later
│   └── web/
│       └── templates/
│          └── ...
└── doc/
    ├── implementation_plan.md
    ├── implementation_backlog.md
    └── product_notes.md
```

## 4. Core database schema (SQLite)

### 4.1 sessions
```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,                   -- live, offline, review, mixed, resume
    source_type TEXT NOT NULL,            -- url, youtube, file, text
    source_value TEXT,
    article_text TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}'
);
```

### 4.2 questions
```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    question_index INTEGER NOT NULL,
    level TEXT NOT NULL,                  -- recall, comprehension, inference, synthesis
    question_text TEXT NOT NULL,
    ideal_answer TEXT,
    key_points TEXT,
    source_context TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

`key_points` stores a JSON array of short factual claims used by the local offline grader to estimate completeness and missed points.

### 4.3 attempts
```sql
CREATE TABLE attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    attempt_no INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'answered',
    created_at TEXT NOT NULL,
    FOREIGN KEY(question_id) REFERENCES questions(id)
);
```

Offline grading does not change the attempt model; it simply creates a grade record from the locally computed score instead of an LLM call.

### 4.4 grades
```sql
CREATE TABLE grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    attempt_id INTEGER NOT NULL,
    correctness REAL,
    completeness REAL,
    clarity REAL,
    evidence_use REAL,
    overall_score REAL,
    missed_points TEXT,
    feedback TEXT,
    hint TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(question_id) REFERENCES questions(id),
    FOREIGN KEY(attempt_id) REFERENCES attempts(id)
);
```

### 4.5 review_queue
```sql
CREATE TABLE review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    concept_key TEXT,
    priority_score REAL NOT NULL DEFAULT 0,
    due_at TEXT,
    last_reviewed_at TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    mastery_score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY(question_id) REFERENCES questions(id),
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

### 4.6 metrics_summary
```sql
CREATE TABLE metrics_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    avg_correctness REAL,
    avg_completeness REAL,
    avg_clarity REAL,
    avg_overall REAL,
    question_count INTEGER,
    mastered_count INTEGER,
    weak_point_count INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

### 4.7 user_preferences
```sql
CREATE TABLE user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 5. Execution order and implementation sequence

### Phase 0 — Project bootstrap and guardrails
Priority: P0

Tasks:
1. Create package skeleton and entrypoint.
2. Establish environment variable loading from `.env`.
3. Confirm dependencies and versions.
4. Validate Python CLI startup.
5. Create `doc/` backlog and plan files.

Files:
- `brain_gym_app.py`
- `app/config.py`
- `app/cli.py`
- `README.md`
- `pyproject.toml`
- `doc/*.md`

Commands:
```bash
uv run python brain_gym_app.py --help
```

Acceptance criteria:
- CLI loads without crashes
- environment variables resolve correctly
- app exits cleanly on invalid input

---

### Phase 1 — Database bootstrap and persistence layer
Priority: P0

Tasks:
1. Build SQLite schema and bootstrap scripts.
2. Add repo helpers for session, question, attempt, and grade access.
3. Add session creation and retrieval methods.
4. Add migration-ready structure.
5. Add reset helper script.

Files:
- `db/schema.sql`
- `db/bootstrap.py`
- `db/repo.py`
- `db/migrations.py`
- `scripts/reset_db.py`

Commands:
```bash
python scripts/reset_db.py
python brain_gym_app.py --mode live --file article.txt
```

Acceptance criteria:
- database creates automatically on first run
- sessions and question records persist across runs
- reset script clears only local development data

---

### Phase 2 — Article ingestion services
Priority: P0

Tasks:
1. Implement URL fetcher with HTML/text extraction.
2. Add YouTube transcript extraction support.
3. Add file and pasted-text ingestion.
4. Validate minimum input length and handle parse errors.
5. Add source metadata tracking.

Files:
- `services/article_loader.py`
- `tests/test_article_loader.py`

Commands:
```bash
python brain_gym_app.py --url https://example.com/article
python brain_gym_app.py --youtube https://youtu.be/abcd1234
python brain_gym_app.py --file article.txt
python brain_gym_app.py --text "paste your article here"
```

Acceptance criteria:
- valid source data loads into article text
- unsupported sources fail gracefully with clear error messages
- text length checks prevent empty or unusable inputs

---

### Phase 3 — LLM service abstraction
Priority: P0

Tasks:
1. Wrap OpenAI-compatible client creation.
2. Add `llm()` and `llm_json()` helpers to one service.
3. Add model selection logic for generate vs grade tasks.
4. Standardize JSON validation and response fallback logic.
5. Add environment-configurable model overrides.

Files:
- `services/llm_client.py`
- `app/config.py`
- `tests/test_question_service.py`

Commands:
```bash
python brain_gym_app.py --model gpt-4.1-mini --grade-model gpt-4.1-mini --help
```

Acceptance criteria:
- generate and grade models are configurable
- malformed LLM output is handled gracefully
- fallback logic does not silently corrupt results

---

### Phase 4 — Live mode workflow
Priority: P0

Tasks:
1. Create `workflows/live_mode.py`.
2. Generate a single question at a time.
3. Prompt user for answer.
4. Grade the answer with metrics.
5. Show feedback and hint.
6. Save attempt and grade.
7. Repeat until target score or skip.
8. Allow next-question flow and session summary.

Files:
- `workflows/live_mode.py`
- `services/question_service.py`
- `services/grading_service.py`
- `app/session_orchestrator.py`
- `tests/test_cli.py`

Commands:
```bash
python brain_gym_app.py --mode live --file article.txt --target-score 4.5 --max-retries 2
```

Acceptance criteria:
- one question at a time is presented
- grade metrics persist to DB
- retry loop exits when score threshold is reached or the user skips
- session summary prints meaningful results

---

### Phase 5 — Offline mode workflow
Priority: P0

Tasks:
1. Create `workflows/offline_mode.py`.
2. Generate a batch of questions and ideal answers.
3. Save them to SQLite as a question bank.
4. Retrieve pending questions by session.
5. Allow answer input from CLI and manual DB entry flow.
6. Judge answers in batch.
7. Save grade results and missed-point tags.
8. Generate follow-up rounds based on missed points.
9. Add an optional `--offline-grading` mode using sentence-transformer similarity + key-point coverage.
10. Persist `key_points` with each saved question and allow resume via `--session-id`.

Files:
- `workflows/offline_mode.py`
- `db/repo.py`
- `db/bootstrap.py`
- `services/offline_grader.py`
- `services/review_service.py`
- `tests/test_db_repo.py`

Commands:
```bash
uv run python brain_gym_app.py --mode offline --file article.txt --questions 5 --rounds 3
uv run python brain_gym_app.py --mode offline --file article.txt --questions 5 --offline-grading
uv run python brain_gym_app.py --mode offline --session-id 12 --offline-grading
```

Acceptance criteria:
- question banks save correctly to SQLite
- offline answers can be graded and persisted
- follow-up round generation is tied to missed points
- `--offline-grading` can score saved answers without using the LLM grading API
- a resumed session can continue answering pending questions without losing prior work

---

### Phase 6 — Review loop and missed-point targeting
Priority: P1

Tasks:
1. Aggregate missed points across attempts.
2. Build a weak-point prioritization score.
3. Create `review_queue` entries from missed concepts.
4. Add `--review` mode to revisit weak points from latest or selected session.
5. Generate follow-up questions focused on previous misses.
6. Track question-level mastery progress.

Files:
- `services/review_service.py`
- `workflows/review_mode.py`
- `tests/test_review_service.py`

Commands:
```bash
python brain_gym_app.py --mode review --file article.txt
python brain_gym_app.py --mode review --session-id 12
```

Acceptance criteria:
- weak-point review uses previous misses as target context
- question generation avoids repeating identical weak points endlessly
- review queue updates after each grading call

---

### Phase 7 — Spaced repetition scheduler
Priority: P1

Tasks:
1. Add review intervals: 1d, 3d, 7d, 14d, 30d.
2. Track due_at and last_reviewed_at.
3. Build scheduler that prioritizes due items.
4. Add `--review` or `--resume` commands for due items.
5. Add per-question mastery score update.

Files:
- `services/scheduler.py`
- `workflows/resume_mode.py`
- `tests/test_scheduler.py`

Commands:
```bash
python brain_gym_app.py --mode review --due-only
python brain_gym_app.py --mode resume --session-id 12
```

Acceptance criteria:
- due items are surfaced before new content
- review intervals extend appropriately as mastery improves
- users can resume interrupted sessions without losing progress

---

### Phase 8 — Analytics and personalization
Priority: P1

Tasks:
1. Compute per-session averages and trends.
2. Aggregate question-level difficulty and mastery information.
3. Add recommendations for next question type or topic.
4. Support user preferences such as target score, volume, and mode.
5. Add summary output for `--stats`.

Files:
- `services/analytics.py`
- `services/recommendations.py`
- `tests/test_analytics.py`

Commands:
```bash
python brain_gym_app.py --stats
python brain_gym_app.py --mode live --target-score 4.0 --questions 8
```

Acceptance criteria:
- summary statistics render in human-readable format
- recommendations are based on actual history, not random heuristics
- user settings persist in SQLite

---

### Phase 9 — Mixed mode
Priority: P2

Tasks:
1. Create `workflows/mixed_mode.py`.
2. Allow generation of a question bank once.
3. Offer user choice: live answer / offline answer / batch grade / review due items.
4. Maintain same persistence model across all subpaths.

Files:
- `workflows/mixed_mode.py`
- `app/session_orchestrator.py`

Commands:
```bash
python brain_gym_app.py --mode mixed --file article.txt --questions 10
```

Acceptance criteria:
- one generated bank can feed multiple study paths
- user can choose practice style without re-generating content
- progress remains consistent across the chosen mode

---

### Phase 10 — Optional web/desktop front-end
Priority: P3

Tasks:
1. Expose REST API for session and question operations.
2. Build lightweight front-end shell for the same workflows.
3. Keep SQLite as the backend source of truth.
4. Add UI for question display, answer entry, scoring overview, and review queue.

Files:
- `ui/api.py`
- `ui/web/templates/*.html`
- `ui/web/static/*.js`

Commands:
```bash
uvicorn ui.api:app --reload
```

Acceptance criteria:
- frontend can create sessions and submit answers
- same backend logic powers CLI and UI
- session state aligns across terminal and web interface

## 6. Suggested CLI command inventory

### Core commands
```bash
python brain_gym_app.py --mode live --file article.txt
python brain_gym_app.py --mode live --url https://example.com/article
python brain_gym_app.py --mode live --youtube https://youtu.be/abcd1234
python brain_gym_app.py --mode live --text "paste article text"
```

### Offline commands
```bash
python brain_gym_app.py --mode offline --file article.txt --questions 5 --rounds 3
python brain_gym_app.py --mode offline --url https://example.com/article --questions 10
```

### Review commands
```bash
python brain_gym_app.py --mode review --session-id 12
python brain_gym_app.py --mode review --due-only
python brain_gym_app.py --mode resume --session-id 12
```

### Analytics and utility commands
```bash
python brain_gym_app.py --stats
python brain_gym_app.py --help
python scripts/reset_db.py
python scripts/demo_run.py
```

### Future commands
```bash
python brain_gym_app.py --mode mixed --file article.txt --questions 7
python brain_gym_app.py --mode live --difficulty hard
python brain_gym_app.py --mode review --topic "history"
```

## 7. Feature backlog by option

### 7.1 Mixed mode
- Create a `mixed_mode.py` workflow
- Question bank generated once
- User chooses live / stored / review path
- Session persists selected branch and progress

### 7.2 Difficulty ladder
- Add `difficulty` and `level_distribution` settings
- Increase complexity after repeated high scores
- Decrease complexity when performance drops
- Expose config in `user_preferences`

### 7.3 Spaced repetition
- Add review intervals and due calculations
- Introduce `next_review_at` and `mastery_score`
- Prioritize due questions before new content

### 7.4 Multi-source context blending
- Extend `source_type` and `source_context`
- Combine article, notes, transcript, and summaries for generation and grading
- Tag each question to the context used

### 7.5 Personalization
- Add profile settings for article focus, target score, preferred volume, and review frequency
- Store user preferences in SQLite
- Let the scheduler and generator adapt automatically over time

### 7.6 UI shell
- Build API surface for session operations
- Reuse same service and persistence layer
- Add a minimal frontend once CLI/back-end is stable

## 8. Backlog execution summary

Recommended order for the first implementation sprint:
1. bootstrap + config + CLI
2. database schema + repo layer
3. article loader
4. LLM service abstraction
5. live mode
6. offline mode
7. review loop
8. spaced repetition
9. analytics
10. mixed mode
11. UI layer

## 9. Definition of done for each phase

### Minimum viable app
- live flow works end-to-end
- offline flow works end-to-end
- data persists in SQLite
- question generation and grading are saved
- review loop uses missed points

### Mature product version
- spaced repetition works
- analytics and recommendations are active
- mixed mode and UI mode are available
- user preferences are stored and used

## 10. Recommended next step
Start by implementing the following concrete first milestone:

- `brain_gym_app.py`
- `app/cli.py`
- `app/config.py`
- `db/bootstrap.py`
- `db/repo.py`
- `services/article_loader.py`
- `services/llm_client.py`
- `workflows/live_mode.py`
- `workflows/offline_mode.py`

This is the shortest path to getting a working, testable version of the app before adding review, scheduling, and UI layers.

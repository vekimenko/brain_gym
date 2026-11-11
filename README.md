# Brain Gym — Active Reading

Brain Gym is an active-reading app that turns an article into a guided practice loop.
It supports both live practice and offline question-bank workflows, persists progress in SQLite,
and helps the user keep returning to weak points until they improve.

## What it does

1. Accepts an article from a URL, YouTube transcript, local file, or pasted text.
2. Generates questions grounded in the article content.
3. Lets the user answer either live or later from saved question sets.
4. Grades answers with a rubric-style LLM evaluation.
5. Tracks correctness, completeness, clarity, evidence use, and missed points.
6. Generates follow-up questions from weak areas.
7. Saves progress in SQLite so sessions can be resumed, reviewed, or re-run later.

This is retrieval practice (the "testing effect") applied to real reading — one of the more promising ways to keep cognition active.

## Modes

### Live mode
Live mode is the most direct workflow:
1. Generate a question.
2. User answers it.
3. LLM scores the answer.
4. Show feedback and a hint.
5. Retry until the target score is reached or the user skips.
6. Continue to the next question.

Example:

```bash
python brain_gym_app.py --mode live --file article.txt --target-score 4.5 --max-retries 2
```

### Offline mode
Offline mode creates a saved question bank in SQLite, letting the user answer questions later:
1. Generate a question set.
2. Save it to SQLite.
3. User answers questions from the database.
4. Grade the saved answers.
5. Generate another round based on missed points.
6. Repeat as needed.

Example:

```bash
python brain_gym_app.py --mode offline --file article.txt --questions 5 --rounds 3
```

### Review mode
Review mode is designed to re-visit weak points from previous sessions and generate follow-up practice around the user’s gaps.

Example:

```bash
python brain_gym_app.py --mode review --session-id 12
```

### Mixed mode
A future-mode option that allows the user to generate one bank and then choose whether to practice live, offline, or review weak points.

## Setup

Use the repo virtual environment for the project:

```bash
cd brain-gym
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set the LLM keys and model settings in `.env` or your shell:

```bash
# .env
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini
LLM_GRADE_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
```

Optional:

```bash
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4.1-mini
export LLM_GRADE_MODEL=gpt-4.1-mini
export LLM_BASE_URL=https://api.openai.com/v1
```

## Usage

```bash
python brain_gym_app.py --mode live --url https://example.com/article
python brain_gym_app.py --mode live --youtube https://www.youtube.com/watch?v=...
python brain_gym_app.py --mode live --file article.txt
python brain_gym_app.py --mode live --text "Paste article content here"

python brain_gym_app.py --mode offline --file article.txt --questions 5 --rounds 3
python brain_gym_app.py --mode review --session-id 12
python brain_gym_app.py --help
```

## SQLite-backed progress

The app keeps learning progress in the local SQLite database (`reading_sessions.db`).
This includes:
- sessions
- questions
- attempts
- grades
- missed-point tags
- review queue and scheduling data (planned next)

This makes it possible to resume sessions, re-grade content, and revisit weak points.

## Scoring model

Answers are evaluated on:
- correctness
- completeness
- clarity
- evidence use
- overall score

The app also records:
- missed points
- short feedback
- improvement hints

## Current roadmap status

Implemented:
- CLI app entrypoint
- SQLite bootstrap and repo layer
- article loading from URL, text, file, and YouTube transcript
- live workflow
- offline workflow
- shared LLM client and grading utilities

Planned next:
- review-mode weak-point targeting
- spaced repetition scheduling
- analytics and summaries
- mixed-mode launch flow
- optional web or desktop UI

## Notes on the science

Observational studies consistently link cognitively stimulating activity
(reading, games, courses) with lower dementia risk, though causality is not
proven and no intervention is guaranteed to prevent dementia. Physical
exercise, blood-pressure control, hearing, sleep, and social contact belong
in the mix too.

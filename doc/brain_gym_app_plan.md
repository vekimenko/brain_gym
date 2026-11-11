# Brain Gym App Refactor Plan

## Goal
Turn the current active-reading script into a small app with two user flows:

1. Offline mode: generate a question bank, save it to SQLite, let the user answer later, grade the answers, and continue with follow-up questions based on missed points.
2. Live mode: ask one question at a time, score each answer immediately, provide feedback/hints, and keep retrying until the answer reaches the target score or the user skips.

## Proposed architecture

- Keep the existing article ingestion logic and LLM wrappers.
- Add a SQLite-backed session store that tracks:
  - sessions
  - generated questions
  - user answers
  - grading metrics
  - progress state and retry counts
- Expose a clean CLI that can run both flows without forcing the old one-shot behavior.

## Workflow details

### Offline mode
1. Load article text from URL, file, or pasted text.
2. Generate a batch of questions plus ideal answers.
3. Save them in SQLite with a session record and question status.
4. User answers pending questions from the database.
5. LLM grades each answer against the article and the ideal answer.
6. Save correctness / completeness / clarity / missed points / feedback.
7. If more gap-driven questions are needed, generate a follow-up batch that references previous questions and misses.
8. Repeat until the user stops or the bank is complete.

### Live mode
1. Generate a question based on the article or a focused missed-point list.
2. Prompt the user for the answer.
3. Grade the answer immediately and show metrics plus a short improvement hint.
4. Keep retrying the same question until the score reaches the target threshold or the user skips.
5. Save the attempt history to SQLite.
6. Continue to the next question as long as the session is active.

## Database schema

Use SQLite tables for:

- `sessions` — app session metadata and mode
- `questions` — question text, expected answer, source article, level, status
- `answers` — user responses and repeated attempts
- `grades` — metrics from the LLM judge
- `progress` — summary of current session state and targets

## Additional options to explore

- Mixed mode: generate a bank once, then allow either live practice or offline review.
- Difficulty ladder: raise or lower question complexity based on the last score.
- Spaced repetition: re-ask weak questions on a schedule.
- Multi-source practice: mix article + notes + transcripts into the question set.
- Web or desktop front-end: a lightweight UI around the same SQLite workflow.

## Implementation notes

- Keep backward compatibility with the existing CLI input options.
- Use the current `article_cache` and `question_sets` schema as the base persistence layer.
- Add data models for `Question`, `Attempt`, and `SessionState` to keep the code readable and testable.
- Validate with a CLI smoke test (`--help` and a focused offline generation run).

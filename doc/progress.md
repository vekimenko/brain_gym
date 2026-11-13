# Implementation Progress

## Status
- Started: 2026-11-11
- Phase: Offline mode and local grading refactor complete
- Current objective: keep the app's offline workflow resumable and support local grading without requiring an LLM.

## Completed
- Reviewed the existing active-reading flow and identified the reusable pieces for an app-level session model.
- Added the app entrypoint (`brain_gym_app.py`) and CLI parsing for live/offline flows.
- Created the implementation backlog and plan documents in `doc/`.
- Created project structure under `app/`, `db/`, `services/`, `workflows/`, `scripts/`, and `tests/`.
- Added the config helper, CLI parser, DB bootstrap, repo layer, and persistence for sessions/questions/attempts/grades.
- Implemented offline question bank generation and saved question persistence with resume support.
- Added an optional local grading path using sentence-transformers embeddings and key-point coverage.
- Updated the app to persist `key_points` and to let users resume unfinished offline sessions via `--session-id`.
- Validated the refactor using `uv` and CLI compilation checks.

## In progress
- Final polish and documentation cleanup for the offline grading flow.

## Next steps
1. Add a dedicated review/retry workflow for weak points from prior offline sessions.
2. Expand the local grader with stronger mismatch detection for contradictions or missing required claims.
3. Continue validating the app against real question banks and answer examples.
4. Add stronger review scheduling and follow-up generation for resumed offline sessions.
5. Connect offline grading results to a real weak-point queue so the app can automatically re-ask missed concepts.

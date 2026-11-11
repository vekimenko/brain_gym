# Brain Gym — Active Reading

An interactive quiz loop that turns any article into a retrieval-practice session.

## How it works

1. You give it an article (URL, file, or pasted text).
2. The LLM writes questions at four levels: recall, comprehension, inference, synthesis.
3. You answer each one out loud (voice-to-text) or by typing.
4. The LLM grades each answer on correctness, completeness, and clarity (0–5),
   and lists the points you missed.
5. The next round of questions specifically targets what you missed.
6. Repeat until you say "stop". You get a session summary at the end.

This is retrieval practice (the "testing effect") applied to real reading —
one of the better-supported ways to keep cognition active.

## Setup

```bash
cd brain-gym
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then set your LLM credentials (any OpenAI-compatible endpoint works —
OpenAI, OpenRouter, Together, or a local Ollama server). The project now loads
variables from a `.env` file automatically if present:

```bash
# .env
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini
LLM_GRADE_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
WHISPER_MODE=local
```

Or set them manually in your shell:

```bash
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4.1-mini
export LLM_GRADE_MODEL=gpt-4.1-mini
export LLM_BASE_URL=https://api.openai.com/v1
```

## Use

```bash
python active_reading.py --url https://www.economist.com/some-article
python active_reading.py --youtube https://www.youtube.com/watch?v=...   # quizzes the video's transcript
python active_reading.py --file article.txt
python active_reading.py --review     # re-quiz the weak spots from your last session
python active_reading.py --stats      # progress across past sessions
```

Speak your answers when prompted (up to 90 seconds each; Ctrl+C to stop
recording early). Say "stop" to end the session and get your summary.
Add `--no-voice` to type instead, `--questions 5` for more questions per round,
and `--model gpt-4.1-mini --grade-model gpt-4.1-mini` to pin a specific cost-efficient combo.

### Voice options

| Mode | How | Notes |
|---|---|---|
| `local` (default) | faster-whisper runs on your machine | Free, offline, private |
| `api` | OpenAI Whisper API | Better accuracy, costs pennies |
| `off` | type answers | `--no-voice` |

```bash
export WHISPER_MODE=api   # or local / off
```

## Roadmap ideas

- Difficulty adaptation: increase question depth when you score 4+ consistently.
- True spaced repetition: schedule reviews of missed points at growing intervals (1 day, 3 days, 7 days) instead of only "latest session".
- Progress dashboard: score trends and a streak calendar across sessions.
- Web UI or desktop app shell around the core loop.

## Notes on the science

Observational studies consistently link cognitively stimulating activity
(reading, games, courses) with lower dementia risk, though causality is not
proven and no intervention is guaranteed to prevent dementia. Physical
exercise, blood-pressure control, hearing, sleep, and social contact belong
in the mix too.

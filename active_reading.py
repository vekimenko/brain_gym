#!/usr/bin/env python3
"""
Active Reading Brain Gym
========================
Turn any article into an interactive quiz session:

  1. You give it an article (URL or text file).
  2. An LLM generates questions at several depth levels.
  3. You answer each question out loud (voice -> text via Whisper)
     or by typing.
  4. The LLM grades your answer (correctness, completeness, clarity)
     and tells you what you missed.
  5. New questions are generated targeting the gaps. Repeat until
     you say "stop".

Usage:
    python active_reading.py --url https://example.com/article
    python active_reading.py --youtube https://youtube.com/watch?v=...
    python active_reading.py --file article.txt
    python active_reading.py --text "paste or pipe article text"
    python active_reading.py --review          # re-quiz last session's weak spots
    python active_reading.py --stats           # progress across past sessions

Configuration (environment variables):
    LLM_API_KEY      API key for any OpenAI-compatible endpoint
    LLM_BASE_URL     e.g. https://api.openai.com/v1 (default)
    LLM_MODEL        e.g. gpt-4.1-mini (default; best cost/performance balance)
    LLM_GRADE_MODEL  optional override for grading; defaults to LLM_MODEL
    WHISPER_MODE     local | api | off   (default: local, falls back to typing)

Optional local speech recognition uses faster-whisper (free, offline).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import textwrap
import time
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# ---------------------------------------------------------------------------
# LLM client (any OpenAI-compatible endpoint: OpenAI, OpenRouter, Ollama, ...)
# ---------------------------------------------------------------------------

from openai import OpenAI

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if load_dotenv is not None:
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)


def make_client() -> OpenAI:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit(
            "Set LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL).\n"
            "Works with OpenAI, OpenRouter, Together, or a local Ollama server."
        )
    return OpenAI(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    )


def llm(client: OpenAI, system: str, user: str, model: str) -> str:
    """Single-shot chat completion."""

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_token": 800
    }

    if not model.startswith("gpt-5"):
        kwargs["temperature"] = 0.4

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def llm_json(client: OpenAI, system: str, user: str, model: str):
    """Chat completion constrained to JSON; tolerant fallback extraction."""
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }

    if not model.startswith("gpt-5"):
        kwargs["temperature"] = 0.4

    try:
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or ""
        return json.loads(raw)
    except (json.JSONDecodeError, KeyError, AttributeError):
        # Compatibility fallback for endpoints that do not support
        # response_format or occasionally return fenced JSON.
        raw = llm(client, system, user, model)
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            raise RuntimeError(f"LLM returned non-JSON output:\n{raw[:500]}")


# ---------------------------------------------------------------------------
# Article acquisition
# ---------------------------------------------------------------------------

def fetch_article(url: str) -> str:
    """Download a URL and extract the main article text."""
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (brain-gym/0.1)"}
    html = requests.get(url, headers=headers, timeout=30).text
    try:
        import trafilatura  # best-quality extraction if installed

        text = trafilatura.extract(html, output_format="txt", include_comments=False)
        if text and len(text) > 400:
            return text
    except ImportError:
        pass
    # crude fallback: strip tags
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_youtube_transcript(url: str) -> tuple[str, str]:
    """Fetch a YouTube video's transcript. Returns (text, title)."""
    import requests
    from youtube_transcript_api import YouTubeTranscriptApi

    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    if not m:
        raise ValueError(f"Could not find a YouTube video ID in {url}")
    video_id = m.group(1)

    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id)  # prefers manual captions, falls back to auto
    text = " ".join(snippet.text for snippet in fetched)

    try:
        title = (
            requests.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
                timeout=10,
            )
            .json()
            .get("title", video_id)
        )
    except Exception:
        title = video_id
    return text, title


# ---------------------------------------------------------------------------
# Session persistence (spaced-repetition seed)
# ---------------------------------------------------------------------------

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reading_sessions.db")


def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS article_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_hash TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            title TEXT,
            article_text TEXT NOT NULL,
            summary TEXT,
            facts TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS question_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            article_hash TEXT,
            article_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            notes TEXT,
            FOREIGN KEY(article_hash) REFERENCES article_cache(article_hash)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER NOT NULL,
            question_index INTEGER NOT NULL,
            level TEXT NOT NULL,
            question_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            answer TEXT,
            graded INTEGER NOT NULL DEFAULT 0,
            correctness REAL,
            completeness REAL,
            clarity REAL,
            missed_points TEXT,
            feedback TEXT,
            FOREIGN KEY(set_id) REFERENCES question_sets(id)
        )
        """
    )
    conn.commit()
    conn.close()


def article_hash(article: str) -> str:
    return hashlib.sha256(article.strip().encode("utf-8")).hexdigest()


def get_article_cache(article: str, source: str, title: str | None = None):
    ensure_db()
    h = article_hash(article)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT article_hash, source, title, article_text, summary, facts FROM article_cache WHERE article_hash = ?",
        (h,),
    ).fetchone()
    if row:
        conn.close()
        return row
    summary = summarize_article_text(article)
    facts = extract_article_facts(article)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO article_cache (article_hash, source, title, article_text, summary, facts, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (h, source, title, article, summary, json.dumps(facts), now, now),
    )
    conn.commit()
    conn.close()
    return (h, source, title, article, summary, json.dumps(facts))


def summarize_article_text(article: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", article.strip())
    text = " ".join(sentences[:10])
    return text[:4000] if len(text) > 4000 else text


def extract_article_facts(article: str):
    facts = []
    for line in re.split(r"(?<=[.!?])\s+", article.strip()):
        line = line.strip()
        if len(line.split()) < 8:
            continue
        facts.append(line)
    return facts[:20]


def article_evidence_for_question(article: str, question: str):
    cached = get_article_cache(article, "inline", None)
    facts = json.loads(cached[5]) if cached and cached[5] else []
    if not facts:
        return article[:3000]
    scored = []
    q_tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", question.lower()))
    for fact in facts:
        overlap = len(q_tokens.intersection(set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", fact.lower()))))
        score = overlap + (0.15 if fact.lower() in question.lower() else 0)
        scored.append((score, fact))
    scored.sort(reverse=True)
    evidence = "\n".join(fact for _, fact in scored[:5])
    return evidence or article[:3000]


def save_session(history, source: str, article: str):
    """Persist a finished session so it can be reviewed later."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    data = {
        "started": time.strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "article": article,
        "answers": [
            {
                "level": q.level,
                "question": q.text,
                "answer": ans,
                "correctness": g.correctness,
                "completeness": g.completeness,
                "clarity": g.clarity,
                "missed_points": g.missed_points,
                "feedback": g.feedback,
            }
            for (q, ans, g) in history
        ],
    }
    path = os.path.join(SESSIONS_DIR, time.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  session saved: {path}")


def latest_session():
    if not os.path.isdir(SESSIONS_DIR):
        return None
    files = sorted(f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json"))
    if not files:
        return None
    with open(os.path.join(SESSIONS_DIR, files[-1]), encoding="utf-8") as f:
        return json.load(f)


def save_question_set(article: str, source: str, questions: list[Question]):
    ensure_db()
    article_record = get_article_cache(article, source)
    article_hash_value = article_record[0] if article_record else article_hash(article)
    conn = sqlite3.connect(DB_PATH)
    set_id = conn.execute(
        "INSERT INTO question_sets (created_at, source, article_hash, article_text, status) VALUES (?, ?, ?, ?, 'pending')",
        (time.strftime("%Y-%m-%d %H:%M:%S"), source, article_hash_value, article),
    ).lastrowid
    for index, q in enumerate(questions, start=1):
        conn.execute(
            "INSERT INTO questions (set_id, question_index, level, question_text, status) VALUES (?, ?, ?, ?, 'pending')",
            (set_id, index, q.level, q.text),
        )
    conn.commit()
    conn.close()
    return set_id


def get_pending_question_sets():
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, created_at, source, article_text FROM question_sets WHERE status = 'pending' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows


def read_question_answers(set_id: int):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, question_index, level, question_text, answer FROM questions WHERE set_id = ? ORDER BY question_index ASC",
        (set_id,),
    ).fetchall()
    conn.close()
    return rows


def update_question_answer(question_id: int, answer: str):
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE questions SET answer = ?, status = 'answered' WHERE id = ?",
        (answer, question_id),
    )
    conn.commit()
    conn.close()


def grade_saved_answers(set_id: int, client: OpenAI, model: str):
    rows = read_question_answers(set_id)
    if not rows:
        return []

    conn = sqlite3.connect(DB_PATH)
    article_row = conn.execute(
        "SELECT article_text FROM question_sets WHERE id = ?",
        (set_id,),
    ).fetchone()
    conn.close()
    article = article_row[0] if article_row else ""

    items = []
    for qid, question_index, level, question_text, answer in rows:
        if not answer or not answer.strip():
            continue
        evidence = article_evidence_for_question(article, question_text)
        items.append({
            "question_id": qid,
            "question_index": question_index,
            "level": level,
            "question": question_text,
            "answer": answer,
            "evidence": evidence,
        })
    if not items:
        return []

    prompt = (
        "ARTICLE EVIDENCE:\n"
        + "\n\n".join(f"[{item['question_index']}] {item['evidence']}" for item in items)
        + "\n\nGRADE EACH ANSWER BELOW against the article evidence only. "
        "Return JSON with a 'results' array. Each result must have: "
        "'question_index', 'correctness', 'completeness', 'clarity', 'missed_points', 'feedback'.\n\n"
    )
    for item in items:
        prompt += (
            f"QUESTION {item['question_index']} [{item['level']}]:\n{item['question']}\n\n"
            f"USER ANSWER:\n{item['answer']}\n\n"
        )
    prompt += "JSON FORMAT: {\"results\": [{\"question_index\": 1, \"correctness\": 0-5, \"completeness\": 0-5, \"clarity\": 0-5, \"missed_points\": [\"...\"], \"feedback\": \"two sentences max\"}]}"

    data = llm_json(client, GRADE_SYSTEM, prompt, model)
    results = data.get("results", []) if isinstance(data, dict) else []
    if not isinstance(results, list):
        raise RuntimeError(f"Unexpected batch grading output: {data}")

    parsed = {int(item.get("question_index")): item for item in results if isinstance(item, dict) and "question_index" in item}
    graded = []
    conn = sqlite3.connect(DB_PATH)
    for qid, question_index, level, question_text, answer in rows:
        if not answer or not answer.strip():
            continue
        result = parsed.get(question_index, {})
        grade = Grade(
            correctness=float(result.get("correctness", 0)),
            completeness=float(result.get("completeness", 0)),
            clarity=float(result.get("clarity", 0)),
            missed_points=list(result.get("missed_points", [])),
            feedback=str(result.get("feedback", "")),
        )
        conn.execute(
            "UPDATE questions SET graded = 1, correctness = ?, completeness = ?, clarity = ?, missed_points = ?, feedback = ?, status = 'graded' WHERE id = ?",
            (
                grade.correctness,
                grade.completeness,
                grade.clarity,
                json.dumps(grade.missed_points),
                grade.feedback,
                qid,
            ),
        )
        graded.append((Question(question_index, level, question_text), answer, grade))
    conn.execute("UPDATE question_sets SET status = 'graded' WHERE id = ?", (set_id,))
    conn.commit()
    conn.close()
    return graded


def show_stats():
    if not os.path.isdir(SESSIONS_DIR):
        print("No sessions recorded yet. Run one first.")
        return
    rows = []
    for name in sorted(f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")):
        with open(os.path.join(SESSIONS_DIR, name), encoding="utf-8") as f:
            s = json.load(f)
        answers = s.get("answers", [])
        if not answers:
            continue
        n = len(answers)
        avg = lambda k: sum(a[k] for a in answers) / n
        rows.append((s.get("started", name), s.get("source", "?")[:50], n, avg("correctness"), avg("completeness")))
    if not rows:
        print("No graded answers recorded yet.")
        return
    print(f"{'date':<18}{'source':<52}{'#ans':>4}  {'corr':>4}  {'compl':>4}")
    for date, source, n, corr, compl in rows:
        print(f"{date:<18}{source:<52}{n:>4}  {corr:>4.1f}  {compl:>4.1f}")


# ---------------------------------------------------------------------------
# Voice input (microphone -> text)
# ---------------------------------------------------------------------------

WHISPER_MODE = os.environ.get("WHISPER_MODE", "local").lower()


def _record_seconds(seconds: float, samplerate: int = 16000):
    import queue

    import numpy as np
    import sounddevice as sd

    q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    print(f"  ... recording ({seconds:.0f}s max, press Ctrl+C early to stop)")
    with sd.InputStream(samplerate=samplerate, channels=1, callback=callback):
        chunks = []
        try:
            while sum(len(c) for c in chunks) < seconds * samplerate:
                chunks.append(q.get())
        except KeyboardInterrupt:
            pass
    if not chunks:
        raise RuntimeError("nothing recorded")
    return np.concatenate(chunks)[:, 0]


def transcribe_local(audio, samplerate: int = 16000) -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel("base.en")  # upgrade to "small.en" for accuracy
    segments, _ = model.transcribe(audio.astype("float32"), language="en")
    return " ".join(s.text for s in segments).strip()


def transcribe_api(client: OpenAI, audio, samplerate: int = 16000) -> str:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes((audio * 32767).astype("int16").tobytes())
    buf.seek(0)
    buf.name = "answer.wav"
    resp = client.audio.transcriptions.create(
        model="whisper-1", file=buf, file_format="wav"
    )
    return (resp.text or "").strip()


def get_answer(client: OpenAI, allow_voice: bool) -> str:
    """Capture the user's spoken or typed answer."""
    if allow_voice and WHISPER_MODE in ("local", "api"):
        try:
            audio = _record_seconds(seconds=90)
            if WHISPER_MODE == "local":
                return transcribe_local(audio)
            return transcribe_api(client, audio)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # mic missing, whisper not installed, ...
            print(f"  (voice input unavailable: {exc} — type instead)")
    print("  your answer > ", end="", flush=True)
    return sys.stdin.readline().strip()


# ---------------------------------------------------------------------------
# Question generation and grading
# ---------------------------------------------------------------------------

QUESTION_SYSTEM = """You are a Socratic tutor designing an active-recall session.
You write questions grounded ONLY in the article the user provides.
Questions span four levels: recall (facts), comprehension (meaning),
inference (implications), and synthesis (connect to broader ideas).
Return STRICT JSON, no prose outside JSON."""

GRADE_SYSTEM = """You grade answers to reading-comprehension questions strictly but fairly.
Judge ONLY against the article content. Ignore spoken-word disfluencies.
Return STRICT JSON, no prose outside JSON."""


@dataclass
class Question:
    id: int
    level: str
    text: str


@dataclass
class Grade:
    correctness: float
    completeness: float
    clarity: float
    missed_points: list[str] = field(default_factory=list)
    feedback: str = ""


def choose_model_for_task(kind: str, explicit_model: str | None = None) -> str:
    """Pick a good default model for generation vs grading.

    For this app, the best overall default is a compact reasoning-capable model
    like gpt-4.1-mini: strong enough for quiz generation and rubric-based grading,
    but much cheaper than a full flagship model. This helps keep each round cheap
    without sacrificing quality on short structured prompts.
    """
    if explicit_model:
        return explicit_model
    default = os.environ.get("LLM_MODEL", "gpt-4.1-mini")
    if kind == "grade":
        return os.environ.get("LLM_GRADE_MODEL", default)
    return default


def article_context(article: str) -> str:
    return f"ARTICLE:\n{article.strip()}\n\n"

def generate_questions(client, model, article, n, focus=None):
    """Generate n questions, optionally focused on missed points."""

    context = article_context(article)

    if focus:
        prompt = (
                context
                + "The user previously missed these points:\n"
                + "\n".join(f"- {p}" for p in focus)
                + f"\n\nWrite {n} NEW questions that specifically probe the missed "
                  "points and closely related ideas. Avoid repeating earlier questions.\n"
                  'Return JSON: {"questions": [{"id": 1, "level": "recall", "text": "..."}]}'
        )
    else:
        prompt = (
                context
                + f"Write {n} questions spanning the four levels "
                  "(recall, comprehension, inference, synthesis).\n"
                  'Return JSON: {"questions": [{"id": 1, "level": "recall", "text": "..."}]}'
        )
    data = llm_json(client, QUESTION_SYSTEM, prompt, model)
    return [
        Question(int(q["id"]), q.get("level", "?"), q["text"])
        for q in data.get("questions", data if isinstance(data, list) else [])
    ]


def grade_answer(client, model, article, question, answer):
    evidence = article_evidence_for_question(article, question)
    prompt = (
            "ARTICLE EVIDENCE:\n"
            + evidence
            + f"\n\nQUESTION:\n{question}\n\nUSER ANSWER:\n{answer}\n\n"
              "Grade the answer using only the evidence above. If the evidence is insufficient, you may fall back to the full article text only after noting the gap. Return JSON:\n"
              '{"correctness": 0-5, "completeness": 0-5, "clarity": 0-5, '
              '"missed_points": ["..."], "feedback": "two sentences max"}'
    )
    data = llm_json(client, GRADE_SYSTEM, prompt, model)
    return Grade(
        correctness=float(data.get("correctness", 0)),
        completeness=float(data.get("completeness", 0)),
        clarity=float(data.get("clarity", 0)),
        missed_points=list(data.get("missed_points", [])),
        feedback=str(data.get("feedback", "")),
    )


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def print_wrap(text: str, indent: str = "  "):
    for line in textwrap.wrap(text, width=88):
        print(indent + line)


def run_session(
    article: str,
    rounds: int,
    questions_per_round: int,
    voice: bool,
    source: str = "article",
    initial_missed: list[str] | None = None,
    persist_to_db: bool = False,
):
    client = make_client()
    generate_model = choose_model_for_task("generate")
    grade_model = choose_model_for_task("grade")

    history: list[tuple[Question, str, Grade]] = []
    missed: list[str] = []
    round_no = 0

    print(f"\nSource loaded ({len(article.split())} words). Using model: {generate_model} (quiz) / {grade_model} (grade)\n")

    while round_no < rounds:
        round_no += 1
        focus = missed if round_no > 1 else initial_missed
        questions = generate_questions(client, generate_model, article, questions_per_round, focus)

        if persist_to_db:
            set_id = save_question_set(article, source, questions)
            print(f"\n=== ROUND {round_no} ===")
            print(f"  Saved {len(questions)} questions to SQLite database (set_id={set_id}).")
            print("  Open the database in a SQLite browser and fill in the answer column for each question.")
            print("  Then rerun with --grade-db <set_id> to score those answers.")
            return

        print(f"\n=== ROUND {round_no} " + ("(targeting what you missed)" if focus else "") + " ===")
        for q in questions:
            print(f"\n[{q.level.upper()}] {q.text}")
            answer = get_answer(client, voice)
            if not answer:
                print("  (empty answer — skipped)")
                continue
            if answer.strip().lower() in ("stop", "quit", "exit"):
                print("\nStopping early — here's your summary.")
                summarize(history, rounds)
                save_session(history, source, article)
                return
            grade = grade_answer(client, grade_model, article, q.text, answer)
            history.append((q, answer, grade))
            missed.extend(grade.missed_points)
            print(f"\n  scores: correctness {grade.correctness}/5, "
                  f"completeness {grade.completeness}/5, clarity {grade.clarity}/5")
            print_wrap(grade.feedback)

    summarize(history, rounds)
    save_session(history, source, article)


def summarize(history, rounds):
    if not history:
        print("No answers graded. Bye.")
        return
    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    n = len(history)
    c = sum(g.correctness for _, _, g in history) / n
    comp = sum(g.completeness for _, _, g in history) / n
    cl = sum(g.clarity for _, _, g in history) / n
    print(f"answers: {n}   avg correctness: {c:.1f}/5   "
          f"completeness: {comp:.1f}/5   clarity: {cl:.1f}/5")
    for q, _, g in history[-3:]:
        print_wrap(f"last Q [{q.level}]: {q.text}")
        print_wrap(f"  -> {g.feedback}", "    ")
    print("Done. Regular retrieval practice like this is the whole point — see you tomorrow.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Active reading brain gym")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="article URL")
    src.add_argument("--youtube", help="YouTube video URL (uses its transcript)")
    src.add_argument("--file", help="path to a text file")
    src.add_argument("--text", help="article text directly")
    src.add_argument("--review", action="store_true", help="re-quiz the weak spots from your last session")
    src.add_argument("--stats", action="store_true", help="show progress across past sessions")
    ap.add_argument("--rounds", type=int, default=99, help="max rounds (default: until you stop)")
    ap.add_argument("--questions", type=int, default=15, help="questions per round")
    ap.add_argument("--no-voice", action="store_true", help="type answers instead")
    ap.add_argument("--model", help="override the generation model (defaults to LLM_MODEL)")
    ap.add_argument("--grade-model", help="override the grading model (defaults to LLM_GRADE_MODEL or LLM_MODEL)")
    ap.add_argument("--save-db", action="store_true", help="save generated questions to SQLite for later answer entry in a DB browser")
    ap.add_argument("--grade-db", type=int, help="grade all answered questions in a saved SQLite set by ID")
    args = ap.parse_args()

    if args.grade_db is not None:
        ensure_db()
        client = make_client()
        model = choose_model_for_task("grade")
        history = grade_saved_answers(args.grade_db, client, model)
        if not history:
            print(f"No answered questions found in set_id={args.grade_db}.")
            return
        print(f"\nGraded {len(history)} answered question(s) from set {args.grade_db}.")
        for q, ans, g in history:
            print(f"\n[{q.level.upper()}] {q.text}")
            print(f"  your answer: {ans}")
            print(f"  scores: correctness {g.correctness}/5, completeness {g.completeness}/5, clarity {g.clarity}/5")
            print_wrap(g.feedback)
        return

    if args.stats:
        show_stats()
        return

    if args.grade_db is not None:
        ensure_db()
        client = make_client()
        model = choose_model_for_task("grade")
        history = grade_saved_answers(args.grade_db, client, model)
        if not history:
            print(f"No answered questions found in set_id={args.grade_db}.")
            return
        print(f"\nGraded {len(history)} answered question(s) from set {args.grade_db}.")
        for q, ans, g in history:
            print(f"\n[{q.level.upper()}] {q.text}")
            print(f"  your answer: {ans}")
            print(f"  scores: correctness {g.correctness}/5, completeness {g.completeness}/5, clarity {g.clarity}/5")
            print_wrap(g.feedback)
        return

    if args.review:
        session = latest_session()
        if not session:
            sys.exit("No previous session found — run one first.")
        missed = sorted({p for a in session.get("answers", []) for p in a.get("missed_points", [])})
        if not missed:
            sys.exit("You missed nothing last time. Start a new article instead.")
        print(f"Reviewing {len(missed)} weak point(s) from: {session.get('source', 'last session')}")
        run_session(
            session["article"],
            args.rounds,
            args.questions,
            voice=not args.no_voice,
            source=f"review: {session.get('source', 'last session')}",
            initial_missed=missed,
        )
        return

    if args.url:
        article = fetch_article(args.url)
        source = args.url
    elif args.youtube:
        article, title = fetch_youtube_transcript(args.youtube)
        source = f"youtube: {title}"
    elif args.file:
        article = open(args.file, encoding="utf-8").read()
        source = args.file
    else:
        article = args.text
        source = "pasted text"

    if len(article.split()) < 80:
        sys.exit("Could not extract a substantial article from that source.")

    os.environ["LLM_MODEL"] = args.model or os.environ.get("LLM_MODEL", "gpt-4.1-mini")
    if args.grade_model:
        os.environ["LLM_GRADE_MODEL"] = args.grade_model

    run_session(
        article,
        args.rounds,
        args.questions,
        voice=not args.no_voice,
        source=source,
        persist_to_db=args.save_db,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted — bye.")

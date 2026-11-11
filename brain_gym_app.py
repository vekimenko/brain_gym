#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import textwrap
import time
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from active_reading import (
    article_evidence_for_question,
    choose_model_for_task,
    fetch_article,
    fetch_youtube_transcript,
    llm_json,
    make_client,
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "reading_sessions.db")

if load_dotenv is not None:
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_gym_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_value TEXT,
            article_text TEXT NOT NULL,
            title TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_gym_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_index INTEGER NOT NULL,
            level TEXT NOT NULL,
            question_text TEXT NOT NULL,
            ideal_answer TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES brain_gym_sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_gym_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'answered',
            created_at TEXT NOT NULL,
            FOREIGN KEY(question_id) REFERENCES brain_gym_questions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_gym_grades (
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
            FOREIGN KEY(question_id) REFERENCES brain_gym_questions(id),
            FOREIGN KEY(attempt_id) REFERENCES brain_gym_attempts(id)
        )
        """
    )
    conn.commit()
    conn.close()


def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_article_from_args(args: argparse.Namespace) -> tuple[str, str, str, str | None]:
    if args.url:
        article = fetch_article(args.url)
        return article, "url", args.url, None
    if args.youtube:
        article, title = fetch_youtube_transcript(args.youtube)
        return article, "youtube", args.youtube, title
    if args.file:
        with open(args.file, "r", encoding="utf-8") as handle:
            article = handle.read()
        return article, "file", args.file, None
    if args.text:
        return args.text, "text", "pasted text", None
    raise ValueError("No article source provided")


def create_session(mode: str, article: str, source_type: str, source_value: str, title: str | None = None) -> int:
    ensure_db()
    now = now_iso()
    conn = get_conn()
    row = conn.execute(
        """
        INSERT INTO brain_gym_sessions (mode, source_type, source_value, article_text, title, status, created_at, updated_at, config_json)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, '{}')
        """,
        (mode, source_type, source_value, article, title, now, now),
    )
    conn.commit()
    session_id = row.lastrowid
    conn.close()
    return session_id


def save_questions(session_id: int, questions: list[dict[str, Any]]) -> list[int]:
    conn = get_conn()
    now = now_iso()
    ids: list[int] = []
    for index, item in enumerate(questions, start=1):
        row = conn.execute(
            """
            INSERT INTO brain_gym_questions (session_id, question_index, level, question_text, ideal_answer, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                session_id,
                index,
                item.get("level", "recall"),
                item.get("question") or item.get("text") or "",
                item.get("ideal_answer") or "",
                now,
                now,
            ),
        )
        ids.append(row.lastrowid)
    conn.commit()
    conn.close()
    return ids


def fetch_pending_questions(session_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM brain_gym_questions WHERE session_id = ? AND status = 'pending' ORDER BY question_index ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


def mark_question_answered(question_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE brain_gym_questions SET status = 'answered', updated_at = ? WHERE id = ?",
        (now_iso(), question_id),
    )
    conn.commit()
    conn.close()


def mark_question_skipped(question_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE brain_gym_questions SET status = 'skipped', updated_at = ? WHERE id = ?",
        (now_iso(), question_id),
    )
    conn.commit()
    conn.close()


def save_attempt(question_id: int, answer: str, attempt_no: int) -> int:
    conn = get_conn()
    row = conn.execute(
        "INSERT INTO brain_gym_attempts (question_id, attempt_no, answer_text, status, created_at) VALUES (?, ?, ?, 'answered', ?)",
        (question_id, attempt_no, answer, now_iso()),
    )
    conn.commit()
    attempt_id = row.lastrowid
    conn.close()
    return attempt_id


def save_grade(question_id: int, attempt_id: int, grade: dict[str, Any]) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO brain_gym_grades (
            question_id, attempt_id, correctness, completeness, clarity, evidence_use, overall_score,
            missed_points, feedback, hint, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            attempt_id,
            float(grade.get("correctness", 0)),
            float(grade.get("completeness", 0)),
            float(grade.get("clarity", 0)),
            float(grade.get("evidence_use", 0)),
            float(grade.get("overall_score", 0)),
            json.dumps(grade.get("missed_points", []), ensure_ascii=False),
            grade.get("feedback") or "",
            grade.get("hint") or "",
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()


def generate_question_bank(client: Any, model: str, article: str, count: int, focus: list[str] | None = None) -> list[dict[str, Any]]:
    context = f"ARTICLE:\n{article.strip()}\n\n"
    if focus:
        context += "PRIOR WEAK POINTS TO TARGET:\n" + "\n".join(f"- {point}" for point in focus[:12]) + "\n\n"
    prompt = (
        context
        + f"Generate {count} high-quality active-reading questions grounded only in the article. "
        + "For each question include: level, question, and ideal_answer. "
        + "Use levels like recall, comprehension, inference, and synthesis. "
        + "If focus points are provided, make the questions target those gaps and related ideas. "
        + "Return JSON only in the format {\"questions\": [{\"id\": 1, \"level\": \"recall\", \"question\": \"...\", \"ideal_answer\": \"...\"}]}."
    )
    payload = llm_json(client, "You create careful reading-comprehension questions grounded only in the provided article. Return strict JSON only.", prompt, model)
    questions = payload.get("questions") if isinstance(payload, dict) else []
    if not isinstance(questions, list):
        raise RuntimeError(f"Unexpected question generation output: {payload}")
    cleaned: list[dict[str, Any]] = []
    for idx, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "id": int(item.get("id", idx)),
                "level": str(item.get("level", "recall")),
                "question": str(item.get("question") or item.get("text") or "").strip(),
                "ideal_answer": str(item.get("ideal_answer") or item.get("expected_answer") or "").strip(),
            }
        )
    return cleaned[:count]


def judge_answer(client: Any, model: str, article: str, question: str, ideal_answer: str, answer: str) -> dict[str, Any]:
    evidence = article_evidence_for_question(article, question)
    prompt = (
        "ARTICLE EVIDENCE:\n"
        + evidence
        + "\n\nQUESTION:\n"
        + question
        + "\n\nIDEAL ANSWER:\n"
        + ideal_answer
        + "\n\nUSER ANSWER:\n"
        + answer
        + "\n\nJudge strictly against the article evidence. Return JSON with these keys only: "
        + "{\"correctness\": 0-5, \"completeness\": 0-5, \"clarity\": 0-5, \"evidence_use\": 0-5, \"missed_points\": [\"...\"], \"feedback\": \"...\", \"hint\": \"...\"}."
    )
    payload = llm_json(client, "You evaluate reading responses carefully and fairly. Return strict JSON only.", prompt, model)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected grading output: {payload}")
    correctness = float(payload.get("correctness", 0) or 0)
    completeness = float(payload.get("completeness", 0) or 0)
    clarity = float(payload.get("clarity", 0) or 0)
    evidence_use = float(payload.get("evidence_use", 0) or 0)
    missed_points = payload.get("missed_points") or []
    if not isinstance(missed_points, list):
        missed_points = [str(missed_points)]
    overall = round((correctness + completeness + clarity + evidence_use) / 4.0, 2)
    return {
        "correctness": correctness,
        "completeness": completeness,
        "clarity": clarity,
        "evidence_use": evidence_use,
        "overall_score": overall,
        "missed_points": [str(p) for p in missed_points],
        "feedback": str(payload.get("feedback") or ""),
        "hint": str(payload.get("hint") or ""),
    }


def print_score_summary(grade: dict[str, Any]) -> None:
    print(
        "  scores: correctness={:.1f}, completeness={:.1f}, clarity={:.1f}, evidence_use={:.1f}, overall={:.1f}".format(
            float(grade.get("correctness", 0)),
            float(grade.get("completeness", 0)),
            float(grade.get("clarity", 0)),
            float(grade.get("evidence_use", 0)),
            float(grade.get("overall_score", 0)),
        )
    )
    if grade.get("feedback"):
        print("  feedback:", grade["feedback"])
    if grade.get("hint"):
        print("  hint:", grade["hint"])
    if grade.get("missed_points"):
        print("  missed points:", "; ".join(grade["missed_points"]))


def run_offline_mode(args: argparse.Namespace) -> None:
    article, source_type, source_value, title = load_article_from_args(args)
    client = make_client()
    generate_model = choose_model_for_task("generate")
    grade_model = choose_model_for_task("grade")
    session_id = create_session("offline", article, source_type, source_value, title)
    print(f"Offline session started (session_id={session_id}).")
    print(f"Source: {source_type} :: {source_value}")

    queued_focus: list[str] = []
    max_rounds = max(1, args.rounds or 3)
    for round_no in range(1, max_rounds + 1):
        batch = generate_question_bank(client, generate_model, article, args.questions, queued_focus if queued_focus else None)
        if not batch:
            print("No questions generated; stopping offline session.")
            break
        save_questions(session_id, batch)
        pending = fetch_pending_questions(session_id)
        print(f"\n=== Offline round {round_no} ===")
        for q in pending:
            question_text = q["question_text"]
            ideal_answer = q["ideal_answer"]
            print(f"\n[{q['level'].upper()}] {question_text}")
            answer = input("Your answer > ").strip()
            if not answer:
                print("Empty answer saved as skipped.")
                mark_question_skipped(q["id"])
                continue
            if answer.strip().lower() in {"skip", "pass", "stop"}:
                mark_question_skipped(q["id"])
                print("Question skipped.")
                continue
            attempt_id = save_attempt(q["id"], answer, 1)
            grade = judge_answer(client, grade_model, article, question_text, ideal_answer, answer)
            save_grade(q["id"], attempt_id, grade)
            mark_question_answered(q["id"])
            print_score_summary(grade)
            queued_focus.extend(grade.get("missed_points", []))

        if round_no >= max_rounds:
            print("Maximum offline rounds reached.")
            break

        continue_prompt = input("Generate another follow-up round based on missed points? [y/N]: ").strip().lower()
        if continue_prompt not in {"y", "yes"}:
            break

    print("\nOffline session complete. Progress was saved in SQLite.")


def run_live_mode(args: argparse.Namespace) -> None:
    article, source_type, source_value, title = load_article_from_args(args)
    client = make_client()
    generate_model = choose_model_for_task("generate")
    grade_model = choose_model_for_task("grade")
    session_id = create_session("live", article, source_type, source_value, title)
    print(f"Live session started (session_id={session_id}).")

    target_score = float(args.target_score or 4.5)
    focus: list[str] = []
    while True:
        batch = generate_question_bank(client, generate_model, article, 1, focus if focus else None)
        if not batch:
            print("No question generated; exiting.")
            break
        saved_ids = save_questions(session_id, batch)
        qid = saved_ids[0]
        question_row = get_question_by_id(qid)
        question_text = question_row["question_text"]
        ideal_answer = question_row["ideal_answer"]
        print(f"\n[{question_row['level'].upper()}] {question_text}")

        answer = input("Your answer > ").strip()
        if answer.strip().lower() in {"skip", "pass", "stop"}:
            mark_question_skipped(qid)
            print("Question skipped. You can continue with a new one or exit.")
            cont = input("Continue? [Y/n]: ").strip().lower()
            if cont in {"n", "no"}:
                break
            continue

        attempt_id = save_attempt(qid, answer, 1)
        grade = judge_answer(client, grade_model, article, question_text, ideal_answer, answer)
        save_grade(qid, attempt_id, grade)
        mark_question_answered(qid)
        print_score_summary(grade)
        focus = grade.get("missed_points", [])

        if float(grade.get("overall_score", 0)) >= target_score:
            print("Target score reached. Nice work.")
            choice = input("Next question? [Y/n]: ").strip().lower()
            if choice in {"n", "no"}:
                break
            continue

        retry_count = 1
        while retry_count < max(2, int(args.max_retries or 2)):
            choice = input("Try again with a better answer? [Y/n]: ").strip().lower()
            if choice in {"n", "no"}:
                break
            retry_count += 1
            improved = input("Revised answer > ").strip()
            if improved.strip().lower() in {"skip", "pass", "stop"}:
                break
            attempt_id = save_attempt(qid, improved, retry_count)
            grade = judge_answer(client, grade_model, article, question_text, ideal_answer, improved)
            save_grade(qid, attempt_id, grade)
            print_score_summary(grade)
            focus = grade.get("missed_points", [])
            if float(grade.get("overall_score", 0)) >= target_score:
                print("Target score reached on a retry.")
                break
        cont = input("Continue to the next question? [Y/n]: ").strip().lower()
        if cont in {"n", "no"}:
            break

    print("\nLive session saved in SQLite.")


def get_question_by_id(question_id: int) -> sqlite3.Row:
    conn = get_conn()
    row = conn.execute("SELECT * FROM brain_gym_questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    if row is None:
        raise RuntimeError(f"Question not found: {question_id}")
    return row


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Brain Gym app: active-reading practice with SQLite-backed progress")
    parser.add_argument("--mode", choices=["live", "offline"], default="live", help="Select the workflow mode")
    parser.add_argument("--url", help="URL to fetch and read")
    parser.add_argument("--youtube", help="YouTube URL to transcribe and study")
    parser.add_argument("--file", help="Path to a local text article")
    parser.add_argument("--text", help="Article text to paste directly")
    parser.add_argument("--questions", type=int, default=5, help="Questions to generate per round")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum number of offline follow-up rounds")
    parser.add_argument("--target-score", type=float, default=4.5, help="Target overall score for a live retry to count as complete")
    parser.add_argument("--max-retries", type=int, default=2, help="Maximum retries per live question")
    parser.add_argument("--model", help="Override the generation model")
    parser.add_argument("--grade-model", help="Override the grading model")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not any([args.url, args.youtube, args.file, args.text]):
        parser.error("Provide an article input via --url, --youtube, --file, or --text.")
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.grade_model:
        os.environ["LLM_GRADE_MODEL"] = args.grade_model

    if args.mode == "offline":
        run_offline_mode(args)
    else:
        run_live_mode(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSession interrupted. Progress saved in SQLite.")
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

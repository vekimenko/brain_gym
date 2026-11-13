from __future__ import annotations

import json
from typing import Any

from db.bootstrap import bootstrap
from db.repo import Repo
from services.article_loader import load_article_from_args
from services.llm_client import choose_model_for_task, generate_question_bank, judge_answer, make_client, print_score_summary
from services.offline_grader import grade_answer_local


def _extract_key_points(question: dict[str, Any]) -> list[str]:
    raw_points = question.get("key_points") or []
    if isinstance(raw_points, str):
        try:
            raw_points = json.loads(raw_points)
        except json.JSONDecodeError:
            raw_points = [raw_points]
    if not isinstance(raw_points, list):
        raw_points = [str(raw_points)]
    return [str(point).strip() for point in raw_points if str(point).strip()]


def _grade_answer(args: Any, article: str, question: dict[str, Any], answer: str) -> dict[str, Any]:
    if bool(getattr(args, "offline_grading", False)):
        return grade_answer_local(
            question.get("question", ""),
            question.get("ideal_answer", ""),
            answer,
            _extract_key_points(question),
        )
    client = make_client()
    grade_model = choose_model_for_task("grade", args.grade_model)
    return judge_answer(client, grade_model, article, question["question"], question.get("ideal_answer", ""), answer)


def run_offline_mode(args: Any, repo: Repo | None = None) -> None:
    bootstrap()
    repo = repo or Repo()
    resume_session_id = getattr(args, "resume_session_id", None) or getattr(args, "session_id", None)
    offline_grading = bool(getattr(args, "offline_grading", False))

    if resume_session_id is not None:
        session_id = int(resume_session_id)
        session = repo.get_session_by_id(session_id)
        if session is None:
            raise ValueError(f"No session found for id={session_id}")
        article = session["article_text"]
        print(f"Resuming offline session {session_id}.")
        pending_questions = repo.list_pending_questions(session_id)
        if not pending_questions:
            print("This session has no pending questions. Nothing to do.")
            return
        question_rows = pending_questions
    else:
        article, source_type, source_value, title = load_article_from_args(args)
        client = make_client()
        generate_model = choose_model_for_task("generate", args.model)
        session_id = repo.create_session(
            mode="offline",
            source_type=source_type,
            source_value=source_value,
            article_text=article,
            title=title,
            config={"questions": getattr(args, "questions", 10), "rounds": getattr(args, "rounds", 3), "offline_grading": offline_grading},
        )
        print(f"Offline session started (session_id={session_id}). You can resume it later with --session-id {session_id}.")

        focus: list[str] = []
        rounds = max(1, int(getattr(args, "rounds", 3) or 3))
        for round_no in range(1, rounds + 1):
            batch = generate_question_bank(client, generate_model, article, int(getattr(args, "questions", 10) or 10), focus if focus else None)
            if not batch:
                break

            print(f"\n=== Offline round {round_no} ===")
            round_questions = []
            for index, question in enumerate(batch, start=1):
                qid = repo.add_question(
                    session_id,
                    index,
                    question.get("level", "recall"),
                    question.get("question", ""),
                    question.get("ideal_answer", ""),
                    None,
                    _extract_key_points(question),
                )
                question["db_id"] = qid
                question["key_points"] = _extract_key_points(question)
                round_questions.append({"id": qid, "question": question})

            for q in round_questions:
                row = q["question"]
                qid = q["id"]
                print(f"\n[{row.get('level', 'recall').upper()}] {row['question']}")
                answer = input("Your answer > ").strip()
                if not answer:
                    repo.mark_question_status(qid, "skipped")
                    print("Empty answer stored as skipped.")
                    continue
                if answer.strip().lower() in {"skip", "pass", "stop"}:
                    repo.mark_question_status(qid, "skipped")
                    print("Question skipped.")
                    continue
                attempt_id = repo.add_attempt(qid, answer, 1)
                grade = _grade_answer(args, article, row, answer)
                repo.add_grade(qid, attempt_id, grade)
                repo.mark_question_status(qid, "answered")
                print_score_summary(grade)
                focus.extend(grade.get("missed_points", []))

            if round_no < rounds:
                response = input("Generate another follow-up round based on missed points? [y/N]: ").strip().lower()
                if response not in {"y", "yes"}:
                    break

        print("\nOffline session complete. Progress was saved in SQLite.")
        return

    for row in pending_questions:
        question = {
            "question": row["question_text"],
            "level": row["level"],
            "ideal_answer": row["ideal_answer"] or "",
            "key_points": json.loads(row["key_points"]) if row["key_points"] else [],
        }
        print(f"\n[{question.get('level', 'recall').upper()}] {question['question']}")
        answer = input("Your answer > ").strip()
        if not answer:
            repo.mark_question_status(row["id"], "skipped")
            print("Empty answer stored as skipped.")
            continue
        if answer.strip().lower() in {"skip", "pass", "stop"}:
            repo.mark_question_status(row["id"], "skipped")
            print("Question skipped.")
            continue
        attempt_id = repo.add_attempt(row["id"], answer, 1)
        grade = _grade_answer(args, article, question, answer)
        repo.add_grade(row["id"], attempt_id, grade)
        repo.mark_question_status(row["id"], "answered")
        print_score_summary(grade)

    print("\nResume session complete. Progress was saved in SQLite.")

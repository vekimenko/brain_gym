from __future__ import annotations

from typing import Any

from app.config import get_llm_model
from db.bootstrap import bootstrap
from db.repo import Repo
from services.article_loader import load_article_from_args
from services.llm_client import choose_model_for_task, generate_question_bank, judge_answer, make_client, print_score_summary


def run_live_mode(args: Any, repo: Repo | None = None) -> None:
    bootstrap()
    repo = repo or Repo()
    article, source_type, source_value, title = load_article_from_args(args)
    client = make_client()
    generate_model = choose_model_for_task("generate", args.model)
    grade_model = choose_model_for_task("grade", args.grade_model)

    session_id = repo.create_session(
        mode="live",
        source_type=source_type,
        source_value=source_value,
        article_text=article,
        title=title,
        config={"target_score": getattr(args, "target_score", 4.5), "max_retries": getattr(args, "max_retries", 2)},
    )
    print(f"Live session started (session_id={session_id}).")

    focus: list[str] = []
    target_score = float(getattr(args, "target_score", 4.5) or 4.5)
    while True:
        batch = generate_question_bank(client, generate_model, article, 1, focus if focus else None)
        if not batch:
            print("No question generated; exiting.")
            break
        question = batch[0]
        qid = repo.add_question(
            session_id,
            1,
            question.get("level", "recall"),
            question.get("question", ""),
            question.get("ideal_answer", ""),
            None,
        )
        print(f"\n[{question.get('level', 'recall').upper()}] {question['question']}")

        answer = input("Your answer > ").strip()
        if answer.strip().lower() in {"skip", "pass", "stop"}:
            repo.mark_question_status(qid, "skipped")
            print("Question skipped. Do you want to continue?")
            cont = input("Continue? [Y/n]: ").strip().lower()
            if cont in {"n", "no"}:
                break
            continue

        attempt_id = repo.add_attempt(qid, answer, 1)
        grade = judge_answer(client, grade_model, article, question["question"], question.get("ideal_answer", ""), answer)
        repo.add_grade(qid, attempt_id, grade)
        repo.mark_question_status(qid, "answered")
        print_score_summary(grade)
        focus = list(grade.get("missed_points", []))

        if float(grade.get("overall_score", 0) or 0) >= target_score:
            print("Target score reached. Nice work.")
            choice = input("Next question? [Y/n]: ").strip().lower()
            if choice in {"n", "no"}:
                break
            continue

        retries = max(2, int(getattr(args, "max_retries", 2) or 2))
        for retry_no in range(1, retries):
            choice = input("Try again with a better answer? [Y/n]: ").strip().lower()
            if choice in {"n", "no"}:
                break
            improved = input("Revised answer > ").strip()
            if improved.strip().lower() in {"skip", "pass", "stop"}:
                break
            attempt_id = repo.add_attempt(qid, improved, retry_no + 1)
            grade = judge_answer(client, grade_model, article, question["question"], question.get("ideal_answer", ""), improved)
            repo.add_grade(qid, attempt_id, grade)
            print_score_summary(grade)
            focus = list(grade.get("missed_points", []))
            if float(grade.get("overall_score", 0) or 0) >= target_score:
                print("Target score reached on retry.")
                break

        cont = input("Continue to the next question? [Y/n]: ").strip().lower()
        if cont in {"n", "no"}:
            break

    print("\nLive session saved in SQLite.")

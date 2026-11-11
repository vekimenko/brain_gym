from __future__ import annotations

from typing import Any

from db.bootstrap import bootstrap
from db.repo import Repo
from services.article_loader import load_article_from_args
from services.llm_client import choose_model_for_task, generate_question_bank, judge_answer, make_client, print_score_summary


def run_offline_mode(args: Any, repo: Repo | None = None) -> None:
    bootstrap()
    repo = repo or Repo()
    article, source_type, source_value, title = load_article_from_args(args)
    client = make_client()
    generate_model = choose_model_for_task("generate", args.model)
    grade_model = choose_model_for_task("grade", args.grade_model)

    session_id = repo.create_session(
        mode="offline",
        source_type=source_type,
        source_value=source_value,
        article_text=article,
        title=title,
        config={"questions": getattr(args, "questions", 5), "rounds": getattr(args, "rounds", 3)},
    )
    print(f"Offline session started (session_id={session_id}).")

    focus: list[str] = []
    rounds = max(1, int(getattr(args, "rounds", 3) or 3))
    for round_no in range(1, rounds + 1):
        batch = generate_question_bank(client, generate_model, article, int(getattr(args, "questions", 5) or 5), focus if focus else None)
        if not batch:
            break

        print(f"\n=== Offline round {round_no} ===")
        for index, question in enumerate(batch, start=1):
            qid = repo.add_question(
                session_id,
                index,
                question.get("level", "recall"),
                question.get("question", ""),
                question.get("ideal_answer", ""),
                None,
            )
            print(f"\n[{question.get('level', 'recall').upper()}] {question['question']}")
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
            grade = judge_answer(client, grade_model, article, question["question"], question.get("ideal_answer", ""), answer)
            repo.add_grade(qid, attempt_id, grade)
            repo.mark_question_status(qid, "answered")
            print_score_summary(grade)
            focus.extend(grade.get("missed_points", []))

        if round_no < rounds:
            response = input("Generate another follow-up round based on missed points? [y/N]: ").strip().lower()
            if response not in {"y", "yes"}:
                break

    print("\nOffline session complete. Progress was saved in SQLite.")

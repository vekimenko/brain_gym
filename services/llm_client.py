from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from app.config import get_llm_model


def make_client() -> OpenAI:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set LLM_API_KEY (or OPENAI_API_KEY) before running Brain Gym."
        )
    return OpenAI(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    )


def llm(client: OpenAI, system: str, user: str, model: str) -> str:
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 800,
    }
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def llm_json(client: OpenAI, system: str, user: str, model: str) -> Any:
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }
    try:
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or ""
        return json.loads(raw)
    except Exception:
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
            raise RuntimeError(f"LLM returned non-JSON output: {raw[:500]}")


def article_context(article: str) -> str:
    return f"ARTICLE:\n{article.strip()}\n\n"


def generate_question_bank(client: Any, model: str, article: str, count: int, focus: list[str] | None = None) -> list[dict[str, Any]]:
    context = article_context(article)
    if focus:
        context += "PRIOR WEAK POINTS TO TARGET:\n" + "\n".join(f"- {point}" for point in focus[:12]) + "\n\n"
    prompt = (
        context
        + f"Generate {count} active-reading questions grounded only in the article. "
        + "Each question must include: id, level, question, ideal_answer. "
        + "Use levels like recall, comprehension, inference, and synthesis. "
        + "If focus points are provided, target them and closely related ideas. "
        + 'Return JSON in the form {"questions": [{"id": 1, "level": "recall", "question": "...", "ideal_answer": "..."}]}'
    )
    payload = llm_json(
        client,
        "You are a strict reading tutor. Return JSON only and keep all questions grounded in the article.",
        prompt,
        model,
    )
    questions = payload.get("questions") if isinstance(payload, dict) else []
    if not isinstance(questions, list):
        raise RuntimeError(f"Unexpected question generation response: {payload}")
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


def article_evidence_for_question(article: str, question: str) -> str:
    text = article.strip()
    if not text:
        return ""
    q_tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", question.lower()))
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored = []
    for sentence in sentences:
        sentence_tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", sentence.lower()))
        overlap = len(q_tokens.intersection(sentence_tokens))
        score = overlap + (0.2 if sentence.lower() in question.lower() else 0)
        if score > 0:
            scored.append((score, sentence))
    scored.sort(reverse=True)
    if scored:
        return "\n".join(s for _, s in scored[:5])
    return text[:2000]


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
        + "\n\nJudge strictly against the article. Return JSON with exactly these keys only: "
        + '{"correctness": 0-5, "completeness": 0-5, "clarity": 0-5, "evidence_use": 0-5, "missed_points": ["..."], "feedback": "...", "hint": "..."}'
    )
    payload = llm_json(
        client,
        "You evaluate answers carefully and fairly. Use the article evidence only. Return JSON only.",
        prompt,
        model,
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected grading response: {payload}")
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
        f"  scores: correctness={float(grade.get('correctness', 0)):.1f}, completeness={float(grade.get('completeness', 0)):.1f}, clarity={float(grade.get('clarity', 0)):.1f}, evidence_use={float(grade.get('evidence_use', 0)):.1f}, overall={float(grade.get('overall_score', 0)):.1f}"
    )
    if grade.get("feedback"):
        print("  feedback:", grade["feedback"])
    if grade.get("hint"):
        print("  hint:", grade["hint"])
    # if grade.get("missed_points"):
    #     print("  missed points:", "; ".join(grade["missed_points"]))


def choose_model_for_task(kind: str, explicit_model: str | None = None) -> str:
    return get_llm_model(kind, explicit_model)

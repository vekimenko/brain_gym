from __future__ import annotations

import re
from typing import Any

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:  # pragma: no cover - optional dependency
    SentenceTransformer = None  # type: ignore[assignment]
    util = None  # type: ignore[assignment]

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "if", "in", "into", "is", "it", "its",
    "of", "on", "or", "that", "the", "their", "there", "they", "this", "to",
    "was", "were", "will", "with", "you", "your", "we", "our", "them", "than",
    "then", "these", "those", "about", "after", "before", "because", "between",
    "over", "under", "through", "more", "most", "some", "such",
}
_MODEL = None


def _get_model():
    global _MODEL
    if SentenceTransformer is None or util is None:
        return None
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if w and w not in _STOPWORDS and len(w) > 2]
    return " ".join(words)


def _split_key_points(ideal_answer: str, max_points: int = 8) -> list[str]:
    text = (ideal_answer or "").strip()
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+|;\s*|\n+", text)
    points = [p.strip() for p in parts if p.strip()]
    if len(points) <= 1:
        subparts = [p.strip() for p in re.split(r",\s*|\band\b\s+", text) if p.strip()]
        if subparts:
            points = subparts
    cleaned: list[str] = []
    for point in points:
        if len(point) < 12:
            continue
        cleaned.append(point)
        if len(cleaned) >= max_points:
            break
    if not cleaned:
        cleaned = [text]
    return cleaned[:max_points]


def _token_overlap_score(ideal: str, answer: str) -> float:
    ideal_tokens = set(_normalize_text(ideal).split())
    answer_tokens = set(_normalize_text(answer).split())
    if not ideal_tokens or not answer_tokens:
        return 0.0
    overlap = len(ideal_tokens.intersection(answer_tokens))
    return overlap / max(len(ideal_tokens), 1)


def _local_semantic_similarity(ideal: str, answer: str) -> float:
    if not ideal.strip() or not answer.strip():
        return 0.0
    model = _get_model()
    if model is None:
        return _token_overlap_score(ideal, answer)
    embeddings = model.encode([ideal, answer], normalize_embeddings=True)
    return float(util.cos_sim(embeddings[0], embeddings[1]))


def grade_answer_local(question: str, ideal_answer: str, answer: str, key_points: list[str] | None = None) -> dict[str, Any]:
    answer_text = (answer or "").strip()
    if not answer_text:
        missed = _split_key_points(ideal_answer) or ([ideal_answer.strip()] if ideal_answer.strip() else [])
        return {
            "correctness": 0.0,
            "completeness": 0.0,
            "clarity": 0.0,
            "evidence_use": 0.0,
            "overall_score": 0.0,
            "missed_points": missed,
            "feedback": "No answer was provided.",
            "hint": "Try to answer the question directly from the source material.",
        }

    ideal_text = ideal_answer or ""
    points = key_points or _split_key_points(ideal_text)
    if not points:
        points = [ideal_text.strip()] if ideal_text.strip() else []

    semantic = _local_semantic_similarity(ideal_text, answer_text)
    semantic = max(0.0, min(1.0, semantic))

    if SentenceTransformer is not None and util is not None:
        model = _get_model()
        if model is not None:
            point_embeddings = model.encode(points, normalize_embeddings=True)
            answer_embedding = model.encode(answer_text, normalize_embeddings=True)
            sims = util.cos_sim(answer_embedding, point_embeddings)[0]
            scores = [float(v) for v in sims]
        else:
            scores = [_token_overlap_score(point, answer_text) for point in points]
    else:
        scores = [_token_overlap_score(point, answer_text) for point in points]

    matched = [point for point, score in zip(points, scores) if score >= 0.55]
    missed = [point for point, score in zip(points, scores) if score < 0.55]
    coverage = len(matched) / len(points) if points else 1.0
    key_term = _token_overlap_score(ideal_text, answer_text)

    overall = 0.55 * semantic + 0.35 * coverage + 0.10 * key_term
    overall_5 = round(max(0.0, min(5.0, overall * 5.0)), 2)
    correctness = round(max(0.0, min(5.0, semantic * 5.0)), 2)
    completeness = round(max(0.0, min(5.0, coverage * 5.0)), 2)
    answer_words = max(1, len(answer_text.split()))
    clarity = round(max(0.0, min(5.0, 2.0 + (min(answer_words, 25) / 25.0) * 3.0)), 2)

    if missed:
        feedback = f"Your answer captures the main idea but missed key points: {'; '.join(missed[:2])}"
        hint = "Include the main facts or ideas from the ideal answer in your response."
    elif semantic >= 0.55:
        feedback = "Strong answer: the main idea and most relevant details are covered."
        hint = "You can add a little more specificity or evidence if needed."
    else:
        feedback = "Your answer is only partly aligned with the source material."
        hint = "Restate the core point more directly and include key evidence or definitions."

    return {
        "correctness": correctness,
        "completeness": completeness,
        "clarity": clarity,
        "evidence_use": round(max(0.0, min(5.0, key_term * 5.0)), 2),
        "overall_score": overall_5,
        "missed_points": missed,
        "feedback": feedback,
        "hint": hint,
    }

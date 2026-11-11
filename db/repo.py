from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.config import get_db_path


class Repo:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or get_db_path()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_session(self, mode: str, source_type: str, source_value: str, article_text: str, title: str | None = None, config: dict[str, Any] | None = None) -> int:
        conn = self.connect()
        now = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            """
            INSERT INTO sessions (mode, source_type, source_value, article_text, title, status, created_at, updated_at, config_json)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (mode, source_type, source_value, article_text, title, now, now, json.dumps(config or {}, ensure_ascii=False)),
        )
        conn.commit()
        session_id = row.lastrowid
        conn.close()
        return session_id

    def add_question(self, session_id: int, question_index: int, level: str, question_text: str, ideal_answer: str | None = None, source_context: str | None = None) -> int:
        conn = self.connect()
        now = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            """
            INSERT INTO questions (session_id, question_index, level, question_text, ideal_answer, source_context, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (session_id, question_index, level, question_text, ideal_answer or "", source_context or "", now, now),
        )
        conn.commit()
        qid = row.lastrowid
        conn.close()
        return qid

    def list_pending_questions(self, session_id: int):
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM questions WHERE session_id = ? AND status = 'pending' ORDER BY question_index ASC",
            (session_id,),
        ).fetchall()
        conn.close()
        return rows

    def mark_question_status(self, question_id: int, status: str) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE questions SET status = ?, updated_at = ? WHERE id = ?",
            (status, __import__("time").strftime("%Y-%m-%d %H:%M:%S"), question_id),
        )
        conn.commit()
        conn.close()

    def add_attempt(self, question_id: int, answer_text: str, attempt_no: int) -> int:
        conn = self.connect()
        now = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            "INSERT INTO attempts (question_id, attempt_no, answer_text, status, created_at) VALUES (?, ?, ?, 'answered', ?)",
            (question_id, attempt_no, answer_text, now),
        )
        conn.commit()
        attempt_id = row.lastrowid
        conn.close()
        return attempt_id

    def add_grade(self, question_id: int, attempt_id: int, grade: dict[str, Any]) -> None:
        conn = self.connect()
        now = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            INSERT INTO grades (question_id, attempt_id, correctness, completeness, clarity, evidence_use, overall_score, missed_points, feedback, hint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                attempt_id,
                float(grade.get("correctness", 0) or 0),
                float(grade.get("completeness", 0) or 0),
                float(grade.get("clarity", 0) or 0),
                float(grade.get("evidence_use", 0) or 0),
                float(grade.get("overall_score", 0) or 0),
                json.dumps(grade.get("missed_points", []), ensure_ascii=False),
                grade.get("feedback") or "",
                grade.get("hint") or "",
                now,
            ),
        )
        conn.commit()
        conn.close()

    def get_question_by_id(self, question_id: int):
        conn = self.connect()
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        conn.close()
        return row

    def get_session_by_id(self, session_id: int):
        conn = self.connect()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        return row

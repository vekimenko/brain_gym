from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from app.config import get_db_path


def ensure_db() -> None:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
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
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_index INTEGER NOT NULL,
            level TEXT NOT NULL,
            question_text TEXT NOT NULL,
            ideal_answer TEXT,
            source_context TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'answered',
            created_at TEXT NOT NULL,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grades (
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
            FOREIGN KEY(question_id) REFERENCES questions(id),
            FOREIGN KEY(attempt_id) REFERENCES attempts(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            concept_key TEXT,
            priority_score REAL NOT NULL DEFAULT 0,
            due_at TEXT,
            last_reviewed_at TEXT,
            review_count INTEGER NOT NULL DEFAULT 0,
            mastery_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(question_id) REFERENCES questions(id),
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            avg_correctness REAL,
            avg_completeness REAL,
            avg_clarity REAL,
            avg_overall REAL,
            question_count INTEGER,
            mastered_count INTEGER,
            weak_point_count INTEGER,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def default_config() -> dict:
    return {
        "target_score": 4.5,
        "max_retries": 2,
        "question_count": 5,
        "review_intervals_days": [1, 3, 7, 14, 30],
        "difficulty": "adaptive",
    }


def bootstrap() -> None:
    ensure_db()
    conn = sqlite3.connect(get_db_path())
    existing = conn.execute("SELECT COUNT(*) FROM user_preferences").fetchone()[0]
    if existing == 0:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        payload = json.dumps(default_config(), ensure_ascii=False)
        conn.execute(
            "INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)",
            ("app_config", payload, now),
        )
    conn.commit()
    conn.close()

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).with_name("lab.sqlite3")

DROP_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cohort TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    age INTEGER,
    score REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits > 0)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score REAL,
    status TEXT NOT NULL DEFAULT 'active',
    enrolled_on TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE (student_id, course_id)
);
"""

STUDENTS = [
    ("Ana Nguyen", "A1", "ana.nguyen@example.edu", 20, 92.5),
    ("Bao Tran", "A1", "bao.tran@example.edu", 22, 76.0),
    ("Chi Pham", "B2", "chi.pham@example.edu", 21, 88.0),
    ("Duc Le", "B2", "duc.le@example.edu", 23, 84.0),
    ("Eve Miller", "C3", "eve.miller@example.edu", 20, 97.0),
]

COURSES = [
    ("MCP101", "Model Context Protocol Basics", 3),
    ("SQL201", "Practical SQLite", 4),
    ("AI305", "AI Tool Integration", 3),
]

ENROLLMENTS = [
    (1, 1, 93.0, "completed", "2026-01-12"),
    (1, 2, 88.5, "active", "2026-02-05"),
    (2, 1, 76.0, "active", "2026-01-15"),
    (3, 2, 91.0, "completed", "2026-01-20"),
    (4, 3, 84.0, "active", "2026-02-10"),
    (5, 1, 97.0, "completed", "2026-01-18"),
    (5, 3, 95.0, "active", "2026-02-14"),
]


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    student_count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    if student_count:
        return

    conn.executemany(
        """
        INSERT INTO students (name, cohort, email, age, score)
        VALUES (?, ?, ?, ?, ?)
        """,
        STUDENTS,
    )
    conn.executemany(
        """
        INSERT INTO courses (code, title, credits)
        VALUES (?, ?, ?)
        """,
        COURSES,
    )
    conn.executemany(
        """
        INSERT INTO enrollments (student_id, course_id, score, status, enrolled_on)
        VALUES (?, ?, ?, ?, ?)
        """,
        ENROLLMENTS,
    )


def create_database(db_path: str | Path = DEFAULT_DB_PATH, *, reset: bool = False) -> Path:
    """Create the SQLite lab database and seed it if it is empty."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        if reset:
            conn.executescript(DROP_SQL)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        _seed_if_empty(conn)

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the SQLite lab database.")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path. Defaults to implementation/lab.sqlite3.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep existing rows and only create missing tables.",
    )
    args = parser.parse_args()

    db_path = create_database(args.db, reset=not args.no_reset)
    print(f"SQLite lab database ready: {db_path}")


if __name__ == "__main__":
    main()


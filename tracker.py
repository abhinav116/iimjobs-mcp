import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "applications.db"


class ApplicationTracker:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE,
                title TEXT,
                company TEXT,
                location TEXT,
                salary TEXT,
                job_url TEXT,
                status TEXT DEFAULT 'applied',
                applied_at TEXT,
                resume_version TEXT,
                notes TEXT
            )
        """)
        self.conn.commit()

    def add(self, job_id: str, title: str, company: str, location: str,
            salary: str, job_url: str, resume_version: str = "original"):
        try:
            self.conn.execute("""
                INSERT INTO applications
                (job_id, title, company, location, salary, job_url, status, applied_at, resume_version)
                VALUES (?, ?, ?, ?, ?, ?, 'applied', ?, ?)
            """, (job_id, title, company, location, salary, job_url,
                  datetime.now().isoformat(), resume_version))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already applied

    def already_applied(self, job_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row is not None

    def get_all(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT job_id, title, company, location, salary, status, applied_at, job_url
            FROM applications ORDER BY applied_at DESC
        """).fetchall()
        keys = ["job_id", "title", "company", "location", "salary", "status", "applied_at", "job_url"]
        return [dict(zip(keys, row)) for row in rows]

    def update_status(self, job_id: str, status: str, notes: str = ""):
        self.conn.execute(
            "UPDATE applications SET status = ?, notes = ? WHERE job_id = ?",
            (status, notes, job_id)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

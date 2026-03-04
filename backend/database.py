import os
import json
import sqlite3
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "intelli_credit.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                company_name TEXT,
                extracted_financials TEXT,
                scoring_result TEXT,
                validation_warnings TEXT,
                cam_pdf_path TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def save_analysis(
    analysis_id: str,
    company_name: str,
    financials: Dict[str, Any],
    scoring: Dict[str, Any],
    warnings: List[str],
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO analyses
               (id, company_name, extracted_financials, scoring_result, validation_warnings)
               VALUES (?, ?, ?, ?, ?)""",
            (
                analysis_id,
                company_name,
                json.dumps(financials),
                json.dumps(scoring),
                json.dumps(warnings),
            ),
        )
        conn.commit()


def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    return dict(row) if row else None


def update_cam_path(analysis_id: str, pdf_path: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE analyses SET cam_pdf_path = ? WHERE id = ?",
            (pdf_path, analysis_id),
        )
        conn.commit()


def list_analyses() -> List[Dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, company_name, created_at, cam_pdf_path FROM analyses ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]

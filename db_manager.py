"""SQLite persistence for assets, interactions, and research hypotheses."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DBManager:
    """Create and access the project's evidence database."""

    def __init__(self, db_path: str | Path = "evidence.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Create the required tables if they do not already exist."""
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS Assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    tech_stack TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'discovered'
                );

                CREATE TABLE IF NOT EXISTS Interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER,
                    request TEXT NOT NULL,
                    response TEXT NOT NULL,
                    error_fingerprint TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (asset_id) REFERENCES Assets(id)
                );

                CREATE TABLE IF NOT EXISTS Hypotheses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER,
                    hypothesis_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    evidence_interaction_id INTEGER,
                    FOREIGN KEY (asset_id) REFERENCES Assets(id),
                    FOREIGN KEY (evidence_interaction_id) REFERENCES Interactions(id)
                );
                """
            )

    def upsert_asset(
        self, url: str, tech_stack: str = "", status: str = "discovered"
    ) -> int:
        """Insert an asset, or refresh its metadata, and return its ID."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM Assets WHERE url = ? ORDER BY id LIMIT 1", (url,)
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE Assets SET tech_stack = ?, status = ? WHERE id = ?",
                    (tech_stack, status, row["id"]),
                )
                return int(row["id"])
            cursor = connection.execute(
                "INSERT INTO Assets (url, tech_stack, status) VALUES (?, ?, ?)",
                (url, tech_stack, status),
            )
            return int(cursor.lastrowid)

    def add_interaction(
        self,
        request: str,
        response: str,
        asset_id: int | None = None,
        error_fingerprint: str | None = None,
    ) -> int:
        """Save a request/response record with an ISO-8601 UTC timestamp."""
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO Interactions
                    (asset_id, request, response, error_fingerprint, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (asset_id, request, response, error_fingerprint, timestamp),
            )
            return int(cursor.lastrowid)

    def add_hypothesis(
        self,
        asset_id: int | None,
        hypothesis_text: str,
        status: str = "proposed",
        evidence_interaction_id: int | None = None,
    ) -> int:
        """Save a hypothesis and its optional evidence interaction."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO Hypotheses
                    (asset_id, hypothesis_text, status, evidence_interaction_id)
                VALUES (?, ?, ?, ?)
                """,
                (asset_id, hypothesis_text, status, evidence_interaction_id),
            )
            return int(cursor.lastrowid)

    def recent_context(self, limit: int = 12) -> str:
        """Return concise persisted context for inclusion in the agent prompt."""
        limit = max(1, min(int(limit), 50))
        with self._connect() as connection:
            interactions = connection.execute(
                """
                SELECT i.request, i.response, i.timestamp, a.url AS asset_url
                FROM Interactions AS i
                LEFT JOIN Assets AS a ON a.id = i.asset_id
                ORDER BY i.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            hypotheses = connection.execute(
                """
                SELECT h.hypothesis_text, h.status, a.url AS asset_url
                FROM Hypotheses AS h
                LEFT JOIN Assets AS a ON a.id = h.asset_id
                ORDER BY h.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

        if not interactions and not hypotheses:
            return ""

        lines = ["Previously saved research context:"]
        if interactions:
            lines.append("Recent interactions (oldest to newest):")
            for row in reversed(interactions):
                target = f" [asset: {row['asset_url']}]" if row["asset_url"] else ""
                request = str(row["request"])[:1200]
                response = str(row["response"])[:1600]
                lines.append(f"- {row['timestamp']}{target} | request: {request} | response: {response}")
        if hypotheses:
            lines.append("Recent hypotheses:")
            for row in reversed(hypotheses):
                target = f" [asset: {row['asset_url']}]" if row["asset_url"] else ""
                lines.append(f"- ({row['status']}){target} {row['hypothesis_text'][:1200]}")
        return "\n".join(lines)

    def list_assets(self) -> list[dict[str, Any]]:
        """Return all known assets as dictionaries."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, url, tech_stack, status FROM Assets ORDER BY id"
            ).fetchall()
            return [dict(row) for row in rows]

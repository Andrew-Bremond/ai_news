"""SQLite persistence. One file, committed to the repo, no server."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid          TEXT PRIMARY KEY,   -- "{source}:{external_id}", version-stripped
    source       TEXT NOT NULL,      -- arxiv | rss
    source_name  TEXT NOT NULL,      -- cs.AI, "Lawfare", ...
    external_id  TEXT NOT NULL,
    title        TEXT NOT NULL,
    abstract     TEXT,
    authors      TEXT,
    url          TEXT,
    published    TEXT,               -- ISO8601
    updated      TEXT,
    categories   TEXT,
    profile      TEXT NOT NULL,

    heuristic_score REAL DEFAULT 0,
    llm_score       REAL,
    llm_one_liner   TEXT,
    llm_why         TEXT,

    first_seen   TEXT DEFAULT CURRENT_TIMESTAMP,
    digest_date  TEXT                -- set once it ships; prevents re-surfacing
);
CREATE INDEX IF NOT EXISTS idx_items_profile_pub ON items(profile, published DESC);
CREATE INDEX IF NOT EXISTS idx_items_undigested  ON items(profile, digest_date);
"""

FIELDS = (
    "uid source source_name external_id title abstract authors url "
    "published updated categories profile"
).split()


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_items(conn: sqlite3.Connection, items: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """Insert new items; refresh metadata on ones we've seen.

    Returns (new, refreshed). Never clears digest_date — an item that already
    shipped stays shipped even if arXiv posts a v2.
    """
    items = list(items)
    if not items:
        return 0, 0

    uids = [it["uid"] for it in items]
    marks_in = ",".join("?" for _ in uids)
    existing = {
        r[0] for r in conn.execute(f"SELECT uid FROM items WHERE uid IN ({marks_in})", uids)
    }

    cols = ", ".join(FIELDS)
    marks = ", ".join("?" for _ in FIELDS)
    update = ", ".join(f"{f}=excluded.{f}" for f in ("title", "abstract", "updated", "url"))

    conn.executemany(
        f"INSERT INTO items ({cols}) VALUES ({marks}) "
        f"ON CONFLICT(uid) DO UPDATE SET {update}",
        [[it.get(f) for f in FIELDS] for it in items],
    )
    conn.commit()

    new = sum(1 for u in uids if u not in existing)
    return new, len(uids) - new


def undigested(conn: sqlite3.Connection, profile: str, since_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE profile = ? AND digest_date IS NULL "
        "AND (published >= ? OR published IS NULL) ORDER BY published DESC",
        (profile, since_iso),
    ).fetchall()


def set_heuristic(conn: sqlite3.Connection, scores: dict[str, float]) -> None:
    conn.executemany(
        "UPDATE items SET heuristic_score = ? WHERE uid = ?",
        [(v, k) for k, v in scores.items()],
    )
    conn.commit()


def set_llm(conn: sqlite3.Connection, uid: str, score: float, one_liner: str, why: str) -> None:
    conn.execute(
        "UPDATE items SET llm_score = ?, llm_one_liner = ?, llm_why = ? WHERE uid = ?",
        (score, one_liner, why, uid),
    )
    conn.commit()


def mark_digested(conn: sqlite3.Connection, uids: list[str], date_iso: str) -> None:
    conn.executemany(
        "UPDATE items SET digest_date = ? WHERE uid = ?", [(date_iso, u) for u in uids]
    )
    conn.commit()

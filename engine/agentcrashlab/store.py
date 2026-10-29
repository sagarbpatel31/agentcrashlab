from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("ACL_DATA_DIR", ROOT / ".agentcrashlab"))
_lock = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "lab.sqlite", timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS documents (kind TEXT, id TEXT, body TEXT, updated TEXT, PRIMARY KEY(kind,id))")
    db.execute("CREATE TABLE IF NOT EXISTS events (run_id TEXT, seq INTEGER, body TEXT, PRIMARY KEY(run_id,seq))")
    try:
        with db:
            yield db
    finally:
        db.close()


def put(kind, doc):
    with _lock, connection() as db:
        db.execute("INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,updated=excluded.updated", (kind, doc["id"], json.dumps(doc), now()))
    return doc


def get(kind, identifier):
    with connection() as db:
        row = db.execute("SELECT body FROM documents WHERE kind=? AND id=?", (kind, identifier)).fetchone()
    if not row:
        raise KeyError(f"{kind} {identifier} does not exist")
    return json.loads(row[0])


def listing(kind):
    with connection() as db:
        rows = db.execute("SELECT body FROM documents WHERE kind=? ORDER BY updated DESC LIMIT 100", (kind,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def event(run_id, item):
    with _lock, connection() as db:
        db.execute("INSERT INTO events VALUES (?,?,?)", (run_id, item["seq"], json.dumps(item)))


def events(run_id):
    with connection() as db:
        rows = db.execute("SELECT body FROM events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def metrics(agent_id):
    with connection() as db:
        row = db.execute("SELECT COUNT(*), SUM(json_extract(body,'$.status')='fail'), SUM(COALESCE(json_extract(body,'$.fault_coverage.activated'),0)) FROM documents WHERE kind='run' AND json_extract(body,'$.agent_id')=? AND json_extract(body,'$.status')!='running'", (agent_id,)).fetchone()
        verified = db.execute("SELECT COUNT(*) FROM documents WHERE kind='repair' AND json_extract(body,'$.agent_id')=? AND json_extract(body,'$.status')='verified'", (agent_id,)).fetchone()[0]
    return {"executed": row[0], "failures": row[1] or 0, "activated": row[2] or 0, "verified": verified}

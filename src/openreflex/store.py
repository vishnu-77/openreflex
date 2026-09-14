import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Model, NODE_MODELS, Relation
from .project import home

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('Task','Context','CandidatePath','Execution','ToolCall','Outcome','Experience','Lesson')),
    data TEXT NOT NULL CHECK(json_valid(data))
);
CREATE INDEX IF NOT EXISTS nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS nodes_task ON nodes(json_extract(data, '$.task_id'));
CREATE INDEX IF NOT EXISTS nodes_execution ON nodes(json_extract(data, '$.execution_id'));
CREATE TABLE IF NOT EXISTS edges (
    source TEXT NOT NULL REFERENCES nodes(id),
    relation TEXT NOT NULL CHECK(relation IN ('used','caused','failed_with','resolved_by','recommended_for')),
    target TEXT NOT NULL REFERENCES nodes(id),
    PRIMARY KEY(source,relation,target)
);
CREATE INDEX IF NOT EXISTS edges_target ON edges(target);
CREATE TABLE IF NOT EXISTS sessions (
    agent TEXT NOT NULL,
    session_id TEXT NOT NULL,
    execution_id TEXT NOT NULL REFERENCES nodes(id),
    PRIMARY KEY(agent,session_id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    execution_id TEXT REFERENCES nodes(id),
    kind TEXT NOT NULL,
    received_at REAL NOT NULL
);
PRAGMA user_version = 1;
"""


BUSY_TIMEOUT_SECONDS = 8
SCHEMA_VERSION = 1


def _field(name: str) -> str:
    if not name.isidentifier():
        raise ValueError("Invalid field name")
    return name


def database_path(project: Path) -> Path:
    key = hashlib.sha256(os.path.normcase(str(project.resolve())).encode()).hexdigest()[:24]
    return home() / "projects" / key / "experience.sqlite3"


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Parallel tool calls start many hook processes at once; on a busy machine a lock holder can be descheduled
        # for seconds. Wait long enough to ride that out, but stay under the agents' 10s hook timeout.
        self.db = sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.db.close()
            raise ValueError("Database schema is newer than this engine")
        if version < SCHEMA_VERSION:
            # Only a fresh database pays for schema setup. Re-running it on every hook process meant autocommit
            # writes outside BEGIN IMMEDIATE, which in WAL mode can fail instantly with SQLITE_BUSY under contention.
            if self.db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                self.db.execute("PRAGMA journal_mode=WAL")
            with self.transaction():
                if self.db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            self.db.execute(statement)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def put(self, node: Model):
        self.db.execute(
            "INSERT INTO nodes VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (node.id, type(node).__name__, node.model_dump_json()),
        )

    def get(self, node_id: str):
        row = self.db.execute("SELECT kind,data FROM nodes WHERE id=?", (node_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown graph node")
        return NODE_MODELS[row["kind"]].model_validate_json(row["data"])

    def list(self, kind: str, field: str | None = None, value: str | None = None, limit: int = 1000):
        sql = "SELECT data FROM nodes WHERE kind=?"
        args: list = [kind]
        if field:
            sql += f" AND json_extract(data,'$.{_field(field)}')=?"
            args.append(value)
        sql += " ORDER BY rowid DESC LIMIT ?"
        args.append(limit)
        return [NODE_MODELS[kind].model_validate_json(r[0]) for r in self.db.execute(sql, args)]

    def find(self, kind: str, limit: int = 1000, **fields):
        """Nodes of a kind whose top-level JSON fields equal the given values; filtering happens in SQLite."""
        sql = "SELECT data FROM nodes WHERE kind=?"
        args: list = [kind]
        for name, value in fields.items():
            sql += f" AND json_extract(data,'$.{_field(name)}')=?"
            args.append(value)
        sql += " ORDER BY rowid DESC LIMIT ?"
        args.append(limit)
        return [NODE_MODELS[kind].model_validate_json(r[0]) for r in self.db.execute(sql, args)]

    def link(self, source: str, relation: Relation, target: str):
        self.db.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?)", (source, relation, target))

    def delete(self, node_id: str):
        self.db.execute("DELETE FROM edges WHERE source=? OR target=?", (node_id, node_id))
        self.db.execute("DELETE FROM nodes WHERE id=?", (node_id,))

    def forget_execution(self, execution_id: str):
        """Drop the session binding and event records that point at an execution being deleted."""
        self.db.execute("DELETE FROM sessions WHERE execution_id=?", (execution_id,))
        self.db.execute("DELETE FROM events WHERE execution_id=?", (execution_id,))

    def exists(self, node_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone() is not None

    def bind_session(self, agent: str, session: str, execution_id: str):
        self.db.execute(
            "INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(agent,session_id) DO UPDATE SET execution_id=excluded.execution_id",
            (agent, session, execution_id),
        )

    def latest(self, agent: str, session: str):
        """The session's most recent execution, whether or not it has ended."""
        row = self.db.execute("SELECT execution_id FROM sessions WHERE agent=? AND session_id=?", (agent, session)).fetchone()
        return self.get(row[0]) if row else None

    def active(self, agent: str, session: str):
        execution = self.latest(agent, session)
        return execution if execution is not None and execution.ended_at is None else None

    def record_event(self, event_id: str, execution_id: str | None, kind: str, at: float) -> bool:
        """Returns False when the event was already seen, so retried hooks stay idempotent."""
        cursor = self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?)", (event_id, execution_id, kind, at))
        return cursor.rowcount == 1

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str, overwrite: bool = True):
        verb = "DO UPDATE SET value=excluded.value" if overwrite else "DO NOTHING"
        self.db.execute(f"INSERT INTO meta VALUES(?,?) ON CONFLICT(key) {verb}", (key, value))

    def edges(self, source: str | None = None, relation: str | None = None, target: str | None = None):
        clauses, args = [], []
        for column, value in (("source", source), ("relation", relation), ("target", target)):
            if value is not None:
                clauses.append(f"{column}=?")
                args.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return [dict(r) for r in self.db.execute("SELECT * FROM edges" + where, args)]

    def graph(self, node_id: str, limit: int = 50):
        node = self.get(node_id)
        edges = [dict(r) for r in self.db.execute(
            "SELECT * FROM edges WHERE source=? OR target=? LIMIT ?", (node_id, node_id, min(limit, 100))
        )]
        ids = {node_id} | {e[k] for e in edges for k in ("source", "target")}
        return {"root": node.id, "nodes": [{"kind": type(n).__name__, **n.model_dump()} for n in map(self.get, ids)], "edges": edges}

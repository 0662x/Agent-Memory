from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import EvidenceType, FeedbackType, LifecycleStatus, MemoryKind, ReflectionPhase, ReviewStatus, TraceOperation
from .time_utils import clamp, content_hash, json_dumps, json_loads, make_id, now_iso
from .recall import tokenize

SCHEMA_VERSION = 1
DATABASE_FILENAME = "life_memory.db"


def default_hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".hermes"


def _sqlite_supports_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp._life_memory_fts_probe USING fts5(content)")
        conn.execute("DROP TABLE temp._life_memory_fts_probe")
        return True
    except sqlite3.DatabaseError:
        return False


class LifeMemoryRepository:
    def __init__(
        self,
        hermes_home: str | os.PathLike[str] | None = None,
        db_path: str | os.PathLike[str] | None = None,
    ) -> None:
        home = Path(hermes_home).expanduser() if hermes_home is not None else default_hermes_home()
        self.db_path = Path(db_path).expanduser() if db_path is not None else home / DATABASE_FILENAME
        self._conn: sqlite3.Connection | None = None
        self.fts_enabled = False

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def initialize(self) -> None:
        with self.transaction() as tx:
            self._create_core_schema(tx)
            self.fts_enabled = self._create_fts_if_available(tx)
            existing = tx.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
            if existing is None or existing["version"] is None:
                tx.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_iso()),
                )
            elif int(existing["version"]) < SCHEMA_VERSION:
                tx.execute(
                    "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_iso()),
                )

    def _create_core_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS life_memories (
                memory_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                classification TEXT NOT NULL,
                classification_reason TEXT NOT NULL,
                classification_confidence REAL NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                primary_category TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                context_json TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                feedback_score REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                source_ref TEXT,
                status TEXT NOT NULL,
                review_status TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                source_count INTEGER NOT NULL DEFAULT 1,
                unique_query_count INTEGER NOT NULL DEFAULT 0,
                days_seen_count INTEGER NOT NULL DEFAULT 1,
                promotion_score REAL NOT NULL DEFAULT 0,
                promotion_path TEXT,
                promotion_reason TEXT,
                decay_reason TEXT,
                last_confirmed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                scope TEXT,
                authority TEXT,
                action_boundary TEXT,
                injection_risk REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                access_count INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_life_memories_content_hash
                ON life_memories(content_hash);
            CREATE INDEX IF NOT EXISTS idx_life_memories_status
                ON life_memories(status);
            CREATE INDEX IF NOT EXISTS idx_life_memories_category
                ON life_memories(primary_category);

            CREATE TABLE IF NOT EXISTS memory_evidence (
                evidence_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL REFERENCES life_memories(memory_id) ON DELETE CASCADE,
                evidence_type TEXT NOT NULL,
                content TEXT,
                content_hash TEXT NOT NULL,
                source_ref TEXT,
                event_date TEXT,
                weight REAL NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_evidence_memory_id
                ON memory_evidence(memory_id);

            CREATE TABLE IF NOT EXISTS memory_links (
                link_id TEXT PRIMARY KEY,
                from_memory_id TEXT NOT NULL REFERENCES life_memories(memory_id) ON DELETE CASCADE,
                to_memory_id TEXT NOT NULL REFERENCES life_memories(memory_id) ON DELETE CASCADE,
                relation TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK (from_memory_id <> to_memory_id)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_links_from
                ON memory_links(from_memory_id);
            CREATE INDEX IF NOT EXISTS idx_memory_links_to
                ON memory_links(to_memory_id);

            CREATE TABLE IF NOT EXISTS memory_feedback (
                feedback_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL REFERENCES life_memories(memory_id) ON DELETE CASCADE,
                feedback_type TEXT NOT NULL,
                note TEXT,
                replacement_content TEXT,
                target_memory_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_feedback_memory_id
                ON memory_feedback(memory_id);

            CREATE TABLE IF NOT EXISTS memory_traces (
                trace_id TEXT PRIMARY KEY,
                memory_id TEXT,
                operation TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                input_hash TEXT,
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_traces_memory_id
                ON memory_traces(memory_id);
            CREATE INDEX IF NOT EXISTS idx_memory_traces_operation
                ON memory_traces(operation);

            CREATE TABLE IF NOT EXISTS reflection_runs (
                run_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                input_window_json TEXT NOT NULL,
                candidate_count INTEGER NOT NULL,
                applied_count INTEGER NOT NULL,
                report_path TEXT,
                status TEXT NOT NULL,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS reflection_reports (
                report_id TEXT PRIMARY KEY,
                report_type TEXT NOT NULL,
                report_date TEXT,
                session_ids_json TEXT NOT NULL,
                content TEXT NOT NULL,
                source_memory_ids_json TEXT NOT NULL,
                source_evidence_ids_json TEXT NOT NULL,
                created_by_run_id TEXT,
                review_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def _create_fts_if_available(self, conn: sqlite3.Connection) -> bool:
        if not _sqlite_supports_fts5(conn):
            return False
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS life_memories_fts
                USING fts5(memory_id UNINDEXED, content, primary_category, tags)
                """
            )
            return True
        except sqlite3.DatabaseError:
            return False

    def get_schema_version(self) -> int | None:
        row = self.connect().execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
        if row is None or row["version"] is None:
            return None
        return int(row["version"])

    def append_trace(
        self,
        *,
        operation: TraceOperation | str,
        actor: str,
        reason: str,
        memory_id: str | None = None,
        input_text: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> str:
        trace_id = make_id("trace")
        operation_value = operation.value if isinstance(operation, TraceOperation) else operation
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_traces (
                    trace_id, memory_id, operation, actor, reason, input_hash,
                    before_json, after_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    memory_id,
                    operation_value,
                    actor,
                    reason,
                    content_hash(input_text) if input_text is not None else None,
                    json_dumps(before) if before is not None else None,
                    json_dumps(after) if after is not None else None,
                    now_iso(),
                ),
            )
        return trace_id

    def write_evidence(
        self,
        *,
        memory_id: str,
        evidence_type: EvidenceType | str,
        content: str | None,
        source_ref: str | None = None,
        event_date: str | None = None,
        weight: float = 1.0,
        confidence: float = 1.0,
    ) -> str:
        evidence_id = make_id("evidence")
        evidence_value = evidence_type.value if isinstance(evidence_type, EvidenceType) else evidence_type
        safe_content = content or ""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_evidence (
                    evidence_id, memory_id, evidence_type, content, content_hash,
                    source_ref, event_date, weight, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    memory_id,
                    evidence_value,
                    content,
                    content_hash(safe_content),
                    source_ref,
                    event_date,
                    clamp(weight),
                    clamp(confidence),
                    now_iso(),
                ),
            )
        return evidence_id

    def write_memory_link(
        self,
        *,
        from_memory_id: str,
        to_memory_id: str,
        relation: str,
        reason: str,
    ) -> str:
        link_id = make_id("link")
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_links (
                    link_id, from_memory_id, to_memory_id, relation, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (link_id, from_memory_id, to_memory_id, relation, reason, now_iso()),
            )
        return link_id

    def find_memory_by_content_hash(self, content_hash_value: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT * FROM life_memories
            WHERE content_hash = ? AND status <> ?
            """,
            (content_hash_value, LifecycleStatus.DELETED.value),
        )

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        row = self.connect().execute(
            "SELECT * FROM life_memories WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return map_memory_row(row) if row is not None else None

    def create_memory(
        self,
        *,
        content: str,
        classification: str,
        classification_reason: str,
        classification_confidence: float,
        primary_category: str,
        tags: tuple[str, ...] | list[str],
        context: dict[str, Any],
        importance: float,
        confidence: float,
        source: str,
        source_ref: str | None,
        sensitivity: str,
        injection_risk: float,
        status: str = LifecycleStatus.YOUNG.value,
        review_status: str = ReviewStatus.PENDING.value,
        promotion_path: str | None = None,
        promotion_reason: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        authority: str | None = None,
        action_boundary: str | None = None,
        evidence_type: EvidenceType | str = EvidenceType.ASSISTANT_TOOL_CALL,
        kind: MemoryKind | str = MemoryKind.DIRECT,
    ) -> dict[str, Any]:
        memory_id = make_id("mem")
        evidence_id = make_id("evidence")
        trace_id = make_id("trace")
        now = now_iso()
        created_valid_from = valid_from or now
        hash_value = content_hash(content)
        evidence_value = evidence_type.value if isinstance(evidence_type, EvidenceType) else evidence_type
        kind_value = kind.value if isinstance(kind, MemoryKind) else kind
        authority_value = authority or ("user_direct" if source == "user_explicit" else source)

        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO life_memories (
                    memory_id, kind, classification, classification_reason,
                    classification_confidence, content, content_hash, primary_category,
                    tags_json, context_json, importance, confidence, feedback_score,
                    source, source_ref, status, review_status, sensitivity,
                    evidence_count, source_count, unique_query_count, days_seen_count,
                    promotion_score, promotion_path, promotion_reason, decay_reason,
                    last_confirmed_at, valid_from, valid_until, scope, authority,
                    action_boundary, injection_risk, created_at, updated_at,
                    last_accessed_at, access_count, deleted_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                    ?, ?, ?, ?, ?, 1, 1, 0, 1, 0, ?, ?, NULL,
                    ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, 0, NULL
                )
                """,
                (
                    memory_id,
                    kind_value,
                    classification,
                    classification_reason,
                    clamp(classification_confidence),
                    content,
                    hash_value,
                    primary_category,
                    json_dumps(list(tags)),
                    json_dumps(context),
                    clamp(importance),
                    clamp(confidence),
                    source,
                    source_ref,
                    status,
                    review_status,
                    sensitivity,
                    promotion_path,
                    promotion_reason,
                    now if status == LifecycleStatus.ACTIVE.value else None,
                    created_valid_from,
                    valid_until,
                    authority_value,
                    action_boundary,
                    clamp(injection_risk),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO memory_evidence (
                    evidence_id, memory_id, evidence_type, content, content_hash,
                    source_ref, event_date, weight, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    memory_id,
                    evidence_value,
                    content,
                    hash_value,
                    source_ref,
                    now[:10],
                    1.0,
                    clamp(confidence),
                    now,
                ),
            )
            if self.fts_enabled:
                conn.execute(
                    """
                    INSERT INTO life_memories_fts (memory_id, content, primary_category, tags)
                    VALUES (?, ?, ?, ?)
                    """,
                    (memory_id, content, primary_category, " ".join(tags)),
                )
            conn.execute(
                """
                INSERT INTO memory_traces (
                    trace_id, memory_id, operation, actor, reason, input_hash,
                    before_json, after_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    trace_id,
                    memory_id,
                    TraceOperation.STORE.value,
                    "plugin",
                    classification_reason,
                    hash_value,
                    json_dumps(
                        {
                            "outcome": "success",
                            "status": status,
                            "primary_category": primary_category,
                            "sensitivity": sensitivity,
                        }
                    ),
                    now,
                ),
            )

        return {
            "memory_id": memory_id,
            "evidence_id": evidence_id,
            "trace_id": trace_id,
            "status": status,
            "valid_from": created_valid_from,
            "valid_until": valid_until,
        }

    def record_declined_store_trace(
        self,
        *,
        content: str,
        reason: str,
        outcome: str,
        classification: str | None = None,
        sensitivity: str | None = None,
    ) -> str:
        return self.append_trace(
            operation=TraceOperation.STORE,
            actor="plugin",
            reason=reason,
            input_text=content,
            after={
                "outcome": outcome,
                "classification": classification,
                "sensitivity": sensitivity,
            },
        )

    def record_feedback(
        self,
        *,
        memory_id: str,
        feedback_type: FeedbackType | str,
        note: str | None = None,
        replacement_content: str | None = None,
        target_memory_id: str | None = None,
    ) -> str:
        feedback_id = make_id("feedback")
        feedback_value = feedback_type.value if isinstance(feedback_type, FeedbackType) else feedback_type
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_feedback (
                    feedback_id, memory_id, feedback_type, note,
                    replacement_content, target_memory_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    memory_id,
                    feedback_value,
                    note,
                    replacement_content,
                    target_memory_id,
                    now_iso(),
                ),
            )
        return feedback_id

    def adjust_feedback_score(self, memory_id: str, delta: float) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE life_memories
                SET feedback_score = max(0, min(1, feedback_score + ?)),
                    updated_at = ?
                WHERE memory_id = ?
                """,
                (float(delta), now_iso(), memory_id),
            )

    def update_memory_status(
        self,
        memory_id: str,
        *,
        status: LifecycleStatus | str,
        decay_reason: str | None = None,
        review_status: ReviewStatus | str | None = None,
    ) -> None:
        status_value = status.value if isinstance(status, LifecycleStatus) else status
        review_value = (
            review_status.value
            if isinstance(review_status, ReviewStatus)
            else review_status
        )
        assignments = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status_value, now_iso()]
        if decay_reason is not None:
            assignments.append("decay_reason = ?")
            params.append(decay_reason)
        if review_value is not None:
            assignments.append("review_status = ?")
            params.append(review_value)
        params.append(memory_id)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE life_memories SET {', '.join(assignments)} WHERE memory_id = ?",
                tuple(params),
            )

    def supersede_memory(self, old_memory_id: str, new_memory_id: str, *, reason: str) -> tuple[str, str]:
        forward = self.write_memory_link(
            from_memory_id=old_memory_id,
            to_memory_id=new_memory_id,
            relation="superseded_by",
            reason=reason,
        )
        reverse = self.write_memory_link(
            from_memory_id=new_memory_id,
            to_memory_id=old_memory_id,
            relation="supersedes",
            reason=reason,
        )
        self.update_memory_status(
            old_memory_id,
            status=LifecycleStatus.ARCHIVED,
            decay_reason="superseded",
        )
        return forward, reverse

    def link_duplicate(self, memory_id: str, target_memory_id: str, *, reason: str) -> str:
        return self.write_memory_link(
            from_memory_id=memory_id,
            to_memory_id=target_memory_id,
            relation="duplicate_of",
            reason=reason,
        )

    def merge_memory(self, memory_id: str, target_memory_id: str, *, reason: str) -> str:
        link_id = self.write_memory_link(
            from_memory_id=memory_id,
            to_memory_id=target_memory_id,
            relation="merged_into",
            reason=reason,
        )
        self.update_memory_status(memory_id, status=LifecycleStatus.ARCHIVED, decay_reason="merged")
        return link_id

    def delete_memory(self, memory_id: str, *, reason: str) -> str | None:
        memory = self.get_memory(memory_id)
        if memory is None or memory["status"] == LifecycleStatus.DELETED.value:
            return None
        trace_id = make_id("trace")
        now = now_iso()
        redacted = "[deleted memory content redacted]"
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE life_memories
                SET content = ?,
                    context_json = ?,
                    status = ?,
                    deleted_at = ?,
                    updated_at = ?,
                    decay_reason = ?
                WHERE memory_id = ?
                """,
                (
                    redacted,
                    json_dumps({}),
                    LifecycleStatus.DELETED.value,
                    now,
                    now,
                    "deleted_by_user",
                    memory_id,
                ),
            )
            conn.execute(
                """
                UPDATE memory_evidence
                SET content = ?
                WHERE memory_id = ?
                """,
                ("[deleted evidence content redacted]", memory_id),
            )
            if self.fts_enabled:
                conn.execute("DELETE FROM life_memories_fts WHERE memory_id = ?", (memory_id,))
            conn.execute(
                """
                INSERT INTO memory_traces (
                    trace_id, memory_id, operation, actor, reason, input_hash,
                    before_json, after_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    memory_id,
                    TraceOperation.FORGET.value,
                    "plugin",
                    reason,
                    memory["content_hash"],
                    json_dumps({"status": memory["status"], "content_hash": memory["content_hash"]}),
                    json_dumps({"status": LifecycleStatus.DELETED.value}),
                    now,
                ),
            )
        return trace_id

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = self.connect().execute(query, params).fetchone()
        return row_to_dict(row) if row is not None else None

    def search_memories(
        self,
        *,
        query: str,
        limit: int = 50,
        categories: tuple[str, ...] | list[str] = (),
        include_archived: bool = False,
        include_sensitive: bool = False,
    ) -> list[dict[str, Any]]:
        terms = tokenize(query)
        if not terms:
            return []
        if self.fts_enabled:
            try:
                rows = self._search_memories_fts(
                    terms=terms,
                    limit=limit,
                    categories=categories,
                    include_archived=include_archived,
                    include_sensitive=include_sensitive,
                )
                if rows:
                    return [map_memory_row(row) for row in rows]
            except sqlite3.DatabaseError:
                pass
        rows = self._search_memories_like(
            terms=terms,
            limit=limit,
            categories=categories,
            include_archived=include_archived,
            include_sensitive=include_sensitive,
        )
        return [map_memory_row(row) for row in rows]

    def _search_memories_fts(
        self,
        *,
        terms: tuple[str, ...],
        limit: int,
        categories: tuple[str, ...] | list[str],
        include_archived: bool,
        include_sensitive: bool,
    ) -> list[sqlite3.Row]:
        where = [
            "memory_id IN (SELECT memory_id FROM life_memories_fts WHERE life_memories_fts MATCH ?)",
            "status <> ?",
            "(valid_until IS NULL OR valid_until > ?)",
        ]
        fts_query = " OR ".join(f"{term}*" for term in terms)
        params: list[Any] = [fts_query, LifecycleStatus.DELETED.value, now_iso()]
        if not include_archived:
            where.append("status <> ?")
            params.append(LifecycleStatus.ARCHIVED.value)
        if not include_sensitive:
            where.append("sensitivity = ?")
            params.append("normal")
        if categories:
            placeholders = ", ".join("?" for _ in categories)
            where.append(f"primary_category IN ({placeholders})")
            params.extend(categories)
        params.append(max(1, min(int(limit), 200)))
        return self.connect().execute(
            f"""
            SELECT * FROM life_memories
            WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

    def _search_memories_like(
        self,
        *,
        terms: tuple[str, ...],
        limit: int,
        categories: tuple[str, ...] | list[str],
        include_archived: bool,
        include_sensitive: bool,
    ) -> list[sqlite3.Row]:
        where = ["status <> ?", "(valid_until IS NULL OR valid_until > ?)"]
        params: list[Any] = [LifecycleStatus.DELETED.value, now_iso()]
        if not include_archived:
            where.append("status <> ?")
            params.append(LifecycleStatus.ARCHIVED.value)
        if not include_sensitive:
            where.append("sensitivity = ?")
            params.append("normal")
        if categories:
            placeholders = ", ".join("?" for _ in categories)
            where.append(f"primary_category IN ({placeholders})")
            params.extend(categories)

        term_clauses = []
        for term in terms:
            term_clauses.append(
                "(lower(content) LIKE ? OR lower(primary_category) LIKE ? OR lower(tags_json) LIKE ?)"
            )
            pattern = f"%{term.lower()}%"
            params.extend([pattern, pattern, pattern])
        where.append("(" + " OR ".join(term_clauses) + ")")
        params.append(max(1, min(int(limit), 200)))
        return self.connect().execute(
            f"""
            SELECT * FROM life_memories
            WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

    def update_access(self, memory_ids: list[str] | tuple[str, ...]) -> None:
        if not memory_ids:
            return
        now = now_iso()
        with self.transaction() as conn:
            for memory_id in memory_ids:
                conn.execute(
                    """
                    UPDATE life_memories
                    SET access_count = access_count + 1,
                        last_accessed_at = ?,
                        unique_query_count = unique_query_count + 1,
                        updated_at = ?
                    WHERE memory_id = ?
                    """,
                    (now, now, memory_id),
                )

    def list_reflection_memories(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            """
            SELECT * FROM life_memories
            WHERE status <> ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (LifecycleStatus.DELETED.value, max(1, min(int(limit), 500))),
        ).fetchall()
        return [map_memory_row(row) for row in rows]

    def list_expired_recent_state_memories(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            """
            SELECT * FROM life_memories
            WHERE status NOT IN (?, ?)
              AND valid_until IS NOT NULL
              AND valid_until <= ?
              AND tags_json LIKE ?
            ORDER BY valid_until ASC
            """,
            (
                LifecycleStatus.DELETED.value,
                LifecycleStatus.ARCHIVED.value,
                now_iso(),
                '%"recent_state"%',
            ),
        ).fetchall()
        return [map_memory_row(row) for row in rows]

    def update_memory_tags(self, memory_id: str, tags: tuple[str, ...] | list[str]) -> None:
        normalized = []
        seen = set()
        for tag in tags:
            value = str(tag).strip().lower().replace("-", "_").replace(" ", "_")
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE life_memories
                SET tags_json = ?, updated_at = ?
                WHERE memory_id = ?
                """,
                (json_dumps(normalized), now_iso(), memory_id),
            )
            if self.fts_enabled:
                row = conn.execute(
                    "SELECT content, primary_category FROM life_memories WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
                if row is not None:
                    conn.execute("DELETE FROM life_memories_fts WHERE memory_id = ?", (memory_id,))
                    conn.execute(
                        """
                        INSERT INTO life_memories_fts (memory_id, content, primary_category, tags)
                        VALUES (?, ?, ?, ?)
                        """,
                        (memory_id, row["content"], row["primary_category"], " ".join(normalized)),
                    )

    def refresh_memory_evidence_counts(self, memory_id: str) -> dict[str, int] | None:
        row = self.connect().execute(
            """
            SELECT
                COUNT(*) AS evidence_count,
                COUNT(DISTINCT COALESCE(source_ref, evidence_id)) AS source_count,
                COUNT(DISTINCT COALESCE(event_date, substr(created_at, 1, 10))) AS days_seen_count
            FROM memory_evidence
            WHERE memory_id = ?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            return None
        counts = {
            "evidence_count": int(row["evidence_count"] or 0),
            "source_count": max(1, int(row["source_count"] or 0)),
            "days_seen_count": max(1, int(row["days_seen_count"] or 0)),
        }
        promotion_score = min(
            1.0,
            counts["evidence_count"] * 0.18
            + counts["source_count"] * 0.16
            + counts["days_seen_count"] * 0.12,
        )
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE life_memories
                SET evidence_count = ?,
                    source_count = ?,
                    days_seen_count = ?,
                    promotion_score = max(promotion_score, ?),
                    updated_at = ?
                WHERE memory_id = ?
                """,
                (
                    counts["evidence_count"],
                    counts["source_count"],
                    counts["days_seen_count"],
                    promotion_score,
                    now_iso(),
                    memory_id,
                ),
            )
        return counts

    def start_reflection_run(
        self,
        *,
        phase: ReflectionPhase | str,
        input_window: dict[str, Any],
        notes: str | None = None,
    ) -> str:
        run_id = make_id("reflect")
        phase_value = phase.value if isinstance(phase, ReflectionPhase) else phase
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO reflection_runs (
                    run_id, phase, started_at, completed_at, input_window_json,
                    candidate_count, applied_count, report_path, status, notes
                )
                VALUES (?, ?, ?, NULL, ?, 0, 0, NULL, ?, ?)
                """,
                (run_id, phase_value, now_iso(), json_dumps(input_window), "running", notes),
            )
        return run_id

    def complete_reflection_run(
        self,
        run_id: str,
        *,
        candidate_count: int,
        applied_count: int,
        status: str = "completed",
        report_path: str | None = None,
        notes: str | None = None,
    ) -> None:
        assignments = [
            "completed_at = ?",
            "candidate_count = ?",
            "applied_count = ?",
            "status = ?",
        ]
        params: list[Any] = [now_iso(), int(candidate_count), int(applied_count), status]
        if report_path is not None:
            assignments.append("report_path = ?")
            params.append(report_path)
        if notes is not None:
            assignments.append("notes = ?")
            params.append(notes)
        params.append(run_id)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE reflection_runs SET {', '.join(assignments)} WHERE run_id = ?",
                tuple(params),
            )

    def get_reflection_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connect().execute(
            "SELECT * FROM reflection_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        data = row_to_dict(row)
        data["input_window"] = json_loads(data.pop("input_window_json"), default={})
        return data

    def write_reflection_report(
        self,
        *,
        report_type: str,
        content: str,
        report_date: str | None = None,
        session_ids: tuple[str, ...] | list[str] = (),
        source_memory_ids: tuple[str, ...] | list[str] = (),
        source_evidence_ids: tuple[str, ...] | list[str] = (),
        created_by_run_id: str | None = None,
        review_status: ReviewStatus | str = ReviewStatus.PENDING,
    ) -> str:
        report_id = make_id("report")
        review_value = review_status.value if isinstance(review_status, ReviewStatus) else review_status
        now = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO reflection_reports (
                    report_id, report_type, report_date, session_ids_json, content,
                    source_memory_ids_json, source_evidence_ids_json, created_by_run_id,
                    review_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    report_type,
                    report_date,
                    json_dumps(list(session_ids)),
                    content,
                    json_dumps(list(source_memory_ids)),
                    json_dumps(list(source_evidence_ids)),
                    created_by_run_id,
                    review_value,
                    now,
                    now,
                ),
            )
        return report_id

    def write_reflection_candidate_link(
        self,
        *,
        from_memory_id: str,
        to_memory_id: str,
        relation: str,
        reason: str,
    ) -> str:
        existing = self.fetch_one(
            """
            SELECT * FROM memory_links
            WHERE from_memory_id = ? AND to_memory_id = ? AND relation = ?
            """,
            (from_memory_id, to_memory_id, relation),
        )
        if existing is not None:
            return str(existing["link_id"])
        return self.write_memory_link(
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
            relation=relation,
            reason=reason,
        )

    def list_recent_memory_activity(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            """
            SELECT * FROM life_memories
            WHERE status <> ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (LifecycleStatus.DELETED.value, max(1, min(int(limit), 500))),
        ).fetchall()
        return [map_memory_row(row) for row in rows]

    def export_review_data(
        self,
        *,
        include_archive: bool = True,
        include_sensitive: str = "summary_only",
    ) -> dict[str, Any]:
        include_sensitive_rows = include_sensitive == "summary_only"
        memories = self._export_memory_rows(
            include_archive=include_archive,
            include_sensitive=include_sensitive_rows,
        )
        return {
            "memories": memories,
            "reports": self._export_report_rows(),
        }

    def _export_memory_rows(
        self,
        *,
        include_archive: bool,
        include_sensitive: bool,
    ) -> list[dict[str, Any]]:
        where = ["status <> ?"]
        params: list[Any] = [LifecycleStatus.DELETED.value]
        if not include_archive:
            where.append("status <> ?")
            params.append(LifecycleStatus.ARCHIVED.value)
        if not include_sensitive:
            where.append("sensitivity = ?")
            params.append("normal")
        rows = self.connect().execute(
            f"""
            SELECT * FROM life_memories
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE status
                    WHEN 'reinforced' THEN 0
                    WHEN 'active' THEN 1
                    WHEN 'pattern_candidate' THEN 2
                    WHEN 'young' THEN 3
                    WHEN 'archived' THEN 4
                    ELSE 5
                END,
                updated_at DESC
            """,
            tuple(params),
        ).fetchall()
        return [map_memory_row(row) for row in rows]

    def _export_report_rows(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            """
            SELECT * FROM reflection_reports
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]

    def write_export_trace(self, *, target_dir: str, files: list[str]) -> str:
        return self.append_trace(
            operation=TraceOperation.EXPORT_REVIEW,
            actor="plugin",
            reason="Exported read-only life memory review files.",
            after={"target_dir": target_dir, "files": files},
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def map_memory_row(row: sqlite3.Row) -> dict[str, Any]:
    data = row_to_dict(row)
    data["tags"] = json_loads(data.pop("tags_json"), default=[])
    data["context"] = json_loads(data.pop("context_json"), default={})
    return data

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, Optional

from .models import (
    Inspection,
    InspectionNote,
    InspectionType,
    SessionToken,
    Truck,
    TruckAssignment,
    User,
    UserRole,
)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Database:
    """SQLite backed persistence for the truck inspection domain."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trucks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier TEXT NOT NULL UNIQUE,
                    description TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_type TEXT NOT NULL,
                    truck_id INTEGER NOT NULL REFERENCES trucks(id),
                    ranger_id INTEGER NOT NULL REFERENCES users(id),
                    escalate_visibility INTEGER NOT NULL DEFAULT 0,
                    responses TEXT NOT NULL,
                    photo_urls TEXT NOT NULL,
                    video_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS inspection_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id INTEGER NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
                    author_id INTEGER NOT NULL REFERENCES users(id),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS truck_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    truck_id INTEGER NOT NULL REFERENCES trucks(id),
                    ranger_id INTEGER NOT NULL REFERENCES users(id),
                    start_inspection_id INTEGER NOT NULL REFERENCES inspections(id),
                    end_inspection_id INTEGER REFERENCES inspections(id),
                    start_miles INTEGER NOT NULL,
                    end_miles INTEGER,
                    checked_out_at TEXT NOT NULL,
                    returned_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_truck_assignments_active
                    ON truck_assignments(truck_id)
                    WHERE returned_at IS NULL;
            """
        )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        with self._connect() as conn:
            yield conn

    # User operations
    def add_user(self, name: str, email: str, password_hash: str, role: UserRole) -> User:
        now = _utcnow()
        created_at = _format_datetime(now)
        with self.session() as conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, email, password_hash, role.value, created_at),
            )
            user_id = cursor.lastrowid
        return User(id=user_id, name=name, email=email, password_hash=password_hash, role=role, created_at=now)

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row else None

    def get_user(self, user_id: int) -> Optional[User]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def list_users_by_roles(self, roles: Iterable[UserRole]) -> Iterable[User]:
        role_list = list(roles)
        if not role_list:
            return []
        placeholders = ",".join("?" for _ in role_list)
        with self.session() as conn:
            rows = conn.execute(
                f"SELECT * FROM users WHERE role IN ({placeholders}) ORDER BY name",
                tuple(role.value for role in role_list),
            ).fetchall()
        return [_row_to_user(row) for row in rows]

    def list_rangers(self) -> Iterable[User]:
        return self.list_users_by_roles([UserRole.RANGER])

    # Truck operations
    def add_truck(self, identifier: str, description: Optional[str], active: bool = True) -> Truck:
        with self.session() as conn:
            cursor = conn.execute(
                "INSERT INTO trucks (identifier, description, active) VALUES (?, ?, ?)",
                (identifier, description, 1 if active else 0),
            )
            truck_id = cursor.lastrowid
        return Truck(id=truck_id, identifier=identifier, description=description, active=active)

    def get_truck(self, truck_id: int) -> Optional[Truck]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM trucks WHERE id = ?", (truck_id,)).fetchone()
        return _row_to_truck(row) if row else None

    def get_truck_by_identifier(self, identifier: str) -> Optional[Truck]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM trucks WHERE identifier = ?", (identifier,)).fetchone()
        return _row_to_truck(row) if row else None

    def list_active_trucks(self) -> Iterable[Truck]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM trucks WHERE active = 1 ORDER BY identifier").fetchall()
        for row in rows:
            yield _row_to_truck(row)

    # Inspection operations
    def add_inspection(
        self,
        inspection_type: InspectionType,
        truck_id: int,
        ranger_id: int,
        escalate_visibility: bool,
        responses: Dict[str, Any],
        photo_urls: Iterable[str],
        video_url: Optional[str],
    ) -> Inspection:
        now = _utcnow()
        created_at = _format_datetime(now)
        with self.session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO inspections (
                    inspection_type, truck_id, ranger_id, escalate_visibility,
                    responses, photo_urls, video_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inspection_type.value,
                    truck_id,
                    ranger_id,
                    1 if escalate_visibility else 0,
                    json.dumps(responses),
                    json.dumps(list(photo_urls)),
                    video_url,
                    created_at,
                    created_at,
                ),
            )
            inspection_id = cursor.lastrowid
        return Inspection(
            id=inspection_id,
            inspection_type=inspection_type,
            truck_id=truck_id,
            ranger_id=ranger_id,
            escalate_visibility=escalate_visibility,
            responses=responses,
            photo_urls=list(photo_urls),
            video_url=video_url,
            created_at=now,
            updated_at=now,
        )

    def update_inspection_timestamp(self, inspection_id: int, updated_at: datetime) -> None:
        with self.session() as conn:
            conn.execute(
                "UPDATE inspections SET updated_at = ? WHERE id = ?",
                (_format_datetime(updated_at), inspection_id),
            )

    def get_inspection(self, inspection_id: int) -> Optional[Inspection]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
        return _row_to_inspection(row) if row else None

    def list_inspections(
        self,
        *,
        truck_id: Optional[int] = None,
        ranger_id: Optional[int] = None,
    ) -> Iterable[Inspection]:
        query = "SELECT * FROM inspections"
        params: list[Any] = []
        clauses: list[str] = []
        if truck_id is not None:
            clauses.append("truck_id = ?")
            params.append(truck_id)
        if ranger_id is not None:
            clauses.append("ranger_id = ?")
            params.append(ranger_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"

        with self.session() as conn:
            rows = conn.execute(query, params).fetchall()
        for row in rows:
            yield _row_to_inspection(row)

    # Notes operations
    def add_note(self, inspection_id: int, author_id: int, content: str) -> InspectionNote:
        now = _utcnow()
        created_at = _format_datetime(now)
        with self.session() as conn:
            cursor = conn.execute(
                "INSERT INTO inspection_notes (inspection_id, author_id, content, created_at) VALUES (?, ?, ?, ?)",
                (inspection_id, author_id, content, created_at),
            )
            note_id = cursor.lastrowid
        return InspectionNote(id=note_id, inspection_id=inspection_id, author_id=author_id, content=content, created_at=now)

    def list_notes(self, inspection_id: int) -> Iterable[InspectionNote]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM inspection_notes WHERE inspection_id = ? ORDER BY created_at ASC",
                (inspection_id,),
            ).fetchall()
        for row in rows:
            yield _row_to_note(row)

    # Session token operations
    def add_session_token(self, user_id: int, token: str, expires_at: datetime) -> SessionToken:
        created_at = _utcnow()
        with self.session() as conn:
            cursor = conn.execute(
                "INSERT INTO session_tokens (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    token,
                    _format_datetime(created_at),
                    _format_datetime(expires_at),
                ),
            )
            token_id = cursor.lastrowid
        return SessionToken(id=token_id, user_id=user_id, token=token, created_at=created_at, expires_at=expires_at)

    def get_session_token(self, token: str) -> Optional[SessionToken]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM session_tokens WHERE token = ?", (token,)).fetchone()
        return _row_to_session_token(row) if row else None

    def purge_expired_tokens(self, now: Optional[datetime] = None) -> None:
        now = now or _utcnow()
        with self.session() as conn:
            conn.execute("DELETE FROM session_tokens WHERE expires_at < ?", (_format_datetime(now),))

    # Assignment operations
    def add_assignment(
        self,
        *,
        truck_id: int,
        ranger_id: int,
        start_inspection_id: int,
        start_miles: int,
    ) -> TruckAssignment:
        now = _utcnow()
        with self.session() as conn:
            cursor = conn.execute(
                """
                INSERT INTO truck_assignments (
                    truck_id, ranger_id, start_inspection_id, start_miles, checked_out_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (truck_id, ranger_id, start_inspection_id, start_miles, _format_datetime(now)),
            )
            assignment_id = cursor.lastrowid
        assignment = self.get_assignment(assignment_id)
        assert assignment is not None
        return assignment

    def close_assignment(
        self,
        assignment_id: int,
        *,
        end_inspection_id: int,
        end_miles: int,
    ) -> TruckAssignment:
        returned_at = _utcnow()
        with self.session() as conn:
            conn.execute(
                """
                UPDATE truck_assignments
                SET end_inspection_id = ?, end_miles = ?, returned_at = ?
                WHERE id = ?
                """,
                (end_inspection_id, end_miles, _format_datetime(returned_at), assignment_id),
            )
        assignment = self.get_assignment(assignment_id)
        assert assignment is not None
        return assignment

    def get_assignment(self, assignment_id: int) -> Optional[TruckAssignment]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM truck_assignments WHERE id = ?", (assignment_id,)).fetchone()
        return _row_to_assignment(row) if row else None

    def get_active_assignment_for_truck(self, truck_id: int) -> Optional[TruckAssignment]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM truck_assignments WHERE truck_id = ? AND returned_at IS NULL",
                (truck_id,),
            ).fetchone()
        return _row_to_assignment(row) if row else None

    def get_active_assignment_for_ranger(self, ranger_id: int) -> Optional[TruckAssignment]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM truck_assignments WHERE ranger_id = ? AND returned_at IS NULL",
                (ranger_id,),
            ).fetchone()
        return _row_to_assignment(row) if row else None

    def list_active_assignments(self) -> Iterable[TruckAssignment]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM truck_assignments WHERE returned_at IS NULL",
            ).fetchall()
        for row in rows:
            yield _row_to_assignment(row)

    def list_assignments(self) -> Iterable[TruckAssignment]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM truck_assignments").fetchall()
        for row in rows:
            yield _row_to_assignment(row)


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        created_at=_parse_datetime(row["created_at"]),
    )


def _row_to_truck(row: sqlite3.Row) -> Truck:
    return Truck(
        id=row["id"],
        identifier=row["identifier"],
        description=row["description"],
        active=bool(row["active"]),
    )


def _row_to_inspection(row: sqlite3.Row) -> Inspection:
    return Inspection(
        id=row["id"],
        inspection_type=InspectionType(row["inspection_type"]),
        truck_id=row["truck_id"],
        ranger_id=row["ranger_id"],
        escalate_visibility=bool(row["escalate_visibility"]),
        responses=json.loads(row["responses"]),
        photo_urls=json.loads(row["photo_urls"]),
        video_url=row["video_url"],
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


def _row_to_note(row: sqlite3.Row) -> InspectionNote:
    return InspectionNote(
        id=row["id"],
        inspection_id=row["inspection_id"],
        author_id=row["author_id"],
        content=row["content"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _row_to_session_token(row: sqlite3.Row) -> SessionToken:
    return SessionToken(
        id=row["id"],
        user_id=row["user_id"],
        token=row["token"],
        created_at=_parse_datetime(row["created_at"]),
        expires_at=_parse_datetime(row["expires_at"]),
    )


def _row_to_assignment(row: sqlite3.Row) -> TruckAssignment:
    return TruckAssignment(
        id=row["id"],
        truck_id=row["truck_id"],
        ranger_id=row["ranger_id"],
        start_inspection_id=row["start_inspection_id"],
        end_inspection_id=row["end_inspection_id"],
        start_miles=row["start_miles"],
        end_miles=row["end_miles"],
        checked_out_at=_parse_datetime(row["checked_out_at"]),
        returned_at=_parse_datetime(row["returned_at"]) if row["returned_at"] else None,
    )


def _utcnow() -> datetime:
    return datetime.utcnow()


def _format_datetime(value: datetime) -> str:
    return value.strftime(ISO_FORMAT)


def _parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, ISO_FORMAT)

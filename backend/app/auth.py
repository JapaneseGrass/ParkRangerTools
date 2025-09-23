from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .database import Database
from .models import SessionToken, User, UserRole

TOKEN_BYTES = 32
TOKEN_EXPIRY_MINUTES = 12 * 60


@dataclass(slots=True)
class AuthService:
    database: Database

    def register_user(self, name: str, email: str, password: str, role: UserRole) -> User:
        password_hash = self._hash_password(password)
        return self.database.add_user(name, email, password_hash, role)

    def authenticate(self, email: str, password: str) -> Optional[SessionToken]:
        user = self.database.get_user_by_email(email)
        if not user:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        expires_at = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
        return self.database.add_session_token(user.id, token, expires_at)

    def get_user_for_token(self, token: str) -> Optional[User]:
        if not token:
            return None
        session = self.database.get_session_token(token)
        if not session:
            return None
        if session.expires_at < datetime.utcnow():
            return None
        return self.database.get_user(session.user_id)

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return f"{salt}${digest}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            salt, digest = stored.split("$", 1)
        except ValueError:
            return False
        check = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return secrets.compare_digest(check, digest)

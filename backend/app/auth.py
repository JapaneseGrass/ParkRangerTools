from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .database import Database
from .models import SessionToken, User, UserRole

ALLOWED_EMAIL_ROLES: dict[str, UserRole] = {
    "alex.ranger@example.com": UserRole.RANGER,
    "sam.supervisor@example.com": UserRole.SUPERVISOR,
    "angel.rodriguezii@denvergov.org": UserRole.RANGER,
    "test@email.com": UserRole.RANGER,
}

TOKEN_BYTES = 32
TOKEN_EXPIRY_MINUTES = 12 * 60


@dataclass
class AuthService:
    database: Database

    def register_user(
        self,
        name: str,
        email: str,
        password: str,
        role: Optional[UserRole] = None,
        ranger_number: Optional[str] = None,
    ) -> User:
        normalized = email.strip().lower()
        expected_role = ALLOWED_EMAIL_ROLES.get(normalized)
        if expected_role is None:
            raise ValueError("Registration is restricted to approved park ranger accounts.")
        if role is None:
            role = expected_role
        if role != expected_role:
            raise ValueError("Role does not match approved account permissions.")
        if not ranger_number or not ranger_number.strip():
            raise ValueError("Ranger number is required.")
        password_hash = self._hash_password(password)
        return self.database.add_user(name, normalized, password_hash, role, ranger_number.strip())

    def authenticate(self, email: str, password: str) -> Optional[SessionToken]:
        normalized = email.strip().lower()
        user = self.database.get_user_by_email(normalized)
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

    def update_password(self, email: str, new_password: str) -> User:
        normalized = email.strip().lower()
        if normalized not in ALLOWED_EMAIL_ROLES:
            raise ValueError("Password updates are restricted to approved park ranger accounts.")
        user = self.database.get_user_by_email(normalized)
        if not user:
            raise LookupError("Account not found.")
        password_hash = self._hash_password(new_password)
        self.database.update_user_password(user.id, password_hash)
        return self.database.get_user(user.id)

    def update_profile(self, user_id: int, *, name: str, ranger_number: Optional[str]) -> User:
        if not name.strip():
            raise ValueError("Name cannot be empty.")
        number_clean = ranger_number.strip() if ranger_number else None
        if not number_clean:
            raise ValueError("Ranger number is required.")
        return self.database.update_user_profile(user_id, name.strip(), number_clean)

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

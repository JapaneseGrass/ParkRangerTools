from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .database import Database
from .models import SessionToken, User, UserRole

ALLOWED_EMAIL_ROLES: dict[str, UserRole] = {
    "ranger@email.com": UserRole.RANGER,
    "supervisor@email.com": UserRole.SUPERVISOR,
    "angel.rodriguezii@denvergov.org": UserRole.RANGER,
    "test@email.com": UserRole.RANGER,
    "reserve@example.com": UserRole.RANGER,
    "other.reserve@example.com": UserRole.RANGER,
    "owner@example.com": UserRole.RANGER,
    "super.reserve@example.com": UserRole.SUPERVISOR,
    "super.check@example.com": UserRole.SUPERVISOR,
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
        *,
        security_responses: list[tuple[str, str]],
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
        prepared_questions = self._prepare_security_questions(security_responses)
        return self.database.add_user(
            name,
            normalized,
            password_hash,
            role,
            ranger_number.strip(),
            prepared_questions,
        )

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

    def update_password(self, email: str, new_password: str, security_answers: list[str]) -> User:
        normalized = email.strip().lower()
        if normalized not in ALLOWED_EMAIL_ROLES:
            raise ValueError("Password updates are restricted to approved park ranger accounts.")
        user = self.database.get_user_by_email(normalized)
        if not user:
            raise LookupError("Account not found.")
        if not user.security_questions:
            raise ValueError("Security questions are not configured for this account.")
        if len(user.security_questions) != len(security_answers):
            raise ValueError("All security questions must be answered.")
        for entry, answer in zip(user.security_questions, security_answers):
            if not self._verify_answer(answer, entry.get("answer_hash", "")):
                raise ValueError("Security answers did not match our records.")
        password_hash = self._hash_password(new_password)
        self.database.update_user_password(user.id, password_hash)
        return self.database.get_user(user.id)

    def set_security_questions(self, email: str, security_responses: list[tuple[str, str]]) -> User:
        normalized = email.strip().lower()
        user = self.database.get_user_by_email(normalized)
        if not user:
            raise LookupError("Account not found.")
        prepared = self._prepare_security_questions(security_responses)
        return self.database.update_user_security_questions(user.id, prepared)

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

    def _prepare_security_questions(self, responses: list[tuple[str, str]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for question, answer in responses:
            q = question.strip()
            a = answer.strip()
            if not q or not a:
                raise ValueError("Security questions and answers are required.")
            cleaned.append({"question": q, "answer_hash": self._hash_answer(a)})
        if len(cleaned) != 3:
            raise ValueError("Please provide exactly three security questions and answers.")
        return cleaned

    def _hash_answer(self, answer: str) -> str:
        normalized = answer.strip().lower()
        salt = secrets.token_hex(8)
        digest = hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()
        return f"{salt}${digest}"

    def _verify_answer(self, answer: str, stored: str) -> bool:
        if not stored:
            return False
        try:
            salt, digest = stored.split("$", 1)
        except ValueError:
            return False
        normalized = answer.strip().lower()
        check = hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()
        return secrets.compare_digest(check, digest)

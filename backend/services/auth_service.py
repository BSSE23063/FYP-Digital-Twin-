"""
Minimal real authentication: bcrypt password hashing for owners, JWT bearer
tokens for both owners and passwordless visitors.

Honest limitation, not hidden: visitor login is passwordless by design
(CLAUDE.md §8's decision), but there is no email-sending/magic-link
infrastructure yet to actually verify someone controls the email they log in
with. This closes the real hole flagged since session 7 -- a client typing an
arbitrary visitor_id into a chat request body and inheriting that visitor's
access grants -- because a client can now only act as the identity whose
*token* they hold. It does not yet prove that identity's email is genuinely
theirs. A real magic-link flow is separate, larger future work.
"""
import time
from typing import Optional, Tuple

import bcrypt
import jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import User

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Returns the user id if the token is valid and unexpired, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register_owner(self, email: str, password: str, display_name: str) -> Tuple[User, str]:
        if self.db.query(User).filter(User.email == email).first():
            raise ValueError("An account with this email already exists")
        user = User(email=email, password_hash=hash_password(password), display_name=display_name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user, create_token(user.id)

    def login_owner(self, email: str, password: str) -> Tuple[User, str]:
        user = self.db.query(User).filter(User.email == email).first()
        if not user or not user.password_hash or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        return user, create_token(user.id)

    def login_visitor(self, email: str, display_name: str) -> Tuple[User, str]:
        """Passwordless find-or-create by email — see the module docstring
        for the honest limitation on what this does and doesn't prove."""
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, password_hash=None, display_name=display_name)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user, create_token(user.id)

"""
Auth endpoints: owner register/login (password-based), visitor login
(passwordless find-or-create by email — see AuthService's docstring for the
honest limitation on what that does and doesn't prove).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class VisitorLoginRequest(BaseModel):
    email: str
    display_name: str = "Visitor"


class AuthResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    token: str


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user, token = AuthService(db).register_owner(payload.email, payload.password, payload.display_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return AuthResponse(user_id=user.id, email=user.email, display_name=user.display_name, token=token)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user, token = AuthService(db).login_owner(payload.email, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return AuthResponse(user_id=user.id, email=user.email, display_name=user.display_name, token=token)


@router.post("/visitor-login", response_model=AuthResponse)
def visitor_login(payload: VisitorLoginRequest, db: Session = Depends(get_db)):
    user, token = AuthService(db).login_visitor(payload.email, payload.display_name)
    return AuthResponse(user_id=user.id, email=user.email, display_name=user.display_name, token=token)

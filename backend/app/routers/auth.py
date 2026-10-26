"""Auth router: POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me.

Cookie behaviour
----------------
The session token is sent in an httpOnly, SameSite=Lax cookie named "session".

httpOnly:
  The JavaScript running on the page cannot read the cookie via document.cookie.
  This prevents XSS from stealing the session token.

SameSite=Lax:
  The cookie is sent on same-site requests and top-level cross-site GET navigations,
  but NOT on cross-site POST/PUT/DELETE requests.  This eliminates the most common
  CSRF attack vector (see app/dependencies.py for the full CSRF analysis).

Secure:
  The cookie Secure flag is controlled by Settings.session_cookie_secure
  (True by default in production). In local development and test settings, it
  is set to False so plain HTTP works. The Host header is never used to determine
  security flags because Host is client-controlled ("localhost.evil.com" matches
  startswith("localhost")).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.db.session import get_db
from app.dependencies import SESSION_COOKIE_NAME, require_current_user
from app.models.user import User
from app.services.auth_service import AuthError, login, logout, register

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours, matches auth_service


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password must not be empty.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public representation of the current user.  No password_hash exposed."""

    id: int
    email: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    """Write the session cookie on response.

    secure is driven by settings.session_cookie_secure (True in prod, False in local dev).
    The Host header is client-controlled and must never decide a security flag
    (e.g. "localhost.evil.com" matches startswith("localhost")).
    samesite="lax" prevents cross-site POST CSRF (see dependencies.py).
    httponly=True prevents JS from reading the cookie value.
    """
    app_settings: Settings = getattr(request.app.state, "settings", settings)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=app_settings.session_cookie_secure,
        max_age=_SESSION_MAX_AGE_SECONDS,
        path="/",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserResponse, status_code=201)
def register_user(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Register a new user and log them in immediately.

    On success: creates the account, issues a session cookie, returns 201.
    On duplicate email: returns 409.
    On weak password: returns 422.
    """
    try:
        user = register(db, email=str(body.email), password=body.password)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # Log the user in immediately by creating a session
    try:
        _, token = login(db, email=str(body.email), password=body.password)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    _set_session_cookie(response, token, request)
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=UserResponse)
def login_user(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Authenticate and issue a session cookie.

    On success: returns 200 with user info and sets the session cookie.
    On bad credentials: returns 401 with a GENERIC message (does not reveal
    whether the email exists).
    On rate-limit exceeded: returns 429.
    """
    try:
        user, token = login(db, email=str(body.email), password=body.password)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    _set_session_cookie(response, token, request)
    return UserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    """Invalidate the current session.

    Deletes the session row from the DB (server-side invalidation) and clears
    the cookie.  Returns 204 even if no valid session was present.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        logout(db, token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserResponse)
def me(
    current_user: User = Depends(require_current_user),
) -> UserResponse:
    """Return the currently authenticated user.

    Returns 401 if no valid session cookie is present.
    This endpoint can be used by the frontend to check login state on load.
    """
    return UserResponse(id=current_user.id, email=current_user.email)

"""FastAPI dependencies for authentication.

These are reusable Depends() callables that routers import.

WHY A REUSABLE DEPENDENCY:
  Rather than extracting the session cookie and validating the token in every
  route handler, we define a single FastAPI dependency that handles all of this.
  Any router that needs an authenticated user simply declares:

      current_user: User = Depends(require_current_user)

  This means:
    - auth logic is in one place (not scattered across routes)
    - the dependency is testable in isolation
    - T2.2 projects endpoints can reuse it without copying code

CSRF IMPLICATIONS OF COOKIE AUTH:
  httpOnly cookies are automatically sent by the browser on every same-origin
  and cross-origin request (subject to SameSite policy).  This creates a
  Cross-Site Request Forgery (CSRF) risk: a malicious page on evil.com could
  POST to /auth/logout or to a future /projects endpoint and the browser would
  attach the session cookie.

  Mitigations in place:
    1. SameSite=Lax:  the cookie is sent with top-level GET navigations and
       same-site requests, but NOT with cross-site POST/PUT/DELETE requests
       from an <img>, <form> or XHR.  This eliminates the most common CSRF
       attack vector without requiring a CSRF token.
    2. allow_origins is an explicit list: the browser will not attach CORS
       headers for disallowed origins, and the CORS preflight for POST will
       fail — the request never reaches our handler.
    3. allow_credentials=True is paired with explicit origins.  Combining
       allow_credentials=True with allow_origins=["*"] is forbidden by the
       browser (the browser will refuse to attach credentials to a wildcard-
       origin response).  Our existing no-wildcard validator ensures this.

  Residual risk: SameSite=Lax does NOT protect state-changing requests
  triggered by top-level navigations (e.g., a <a href="POST">) but those
  are unusual.  If CSRF risk becomes a concern in production, add the
  Double-Submit-Cookie or Synchronizer Token pattern.
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_current_user

SESSION_COOKIE_NAME = "session"


def get_optional_user(
    db: Session = Depends(get_db),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> User | None:
    """Return the current User if a valid session cookie is present, else None."""
    return get_current_user(db, session)


def require_current_user(
    user: User | None = Depends(get_optional_user),
) -> User:
    """Require a valid session.  Raises 401 if no valid session cookie is present.

    Use this dependency in any route that requires authentication:

        @router.get("/me")
        def me(current_user: User = Depends(require_current_user)):
            ...
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user

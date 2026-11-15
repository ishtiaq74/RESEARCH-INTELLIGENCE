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
  httpOnly cookies are automatically attached by browsers to matching requests.
  Without proper defenses, this creates a Cross-Site Request Forgery (CSRF) risk:
  a malicious site on evil.com could trigger a request to our API, and the victim's
  browser would attach their session cookie.

  Understanding how our defenses work (and what they do and do not do):

  1. SameSite=Lax cookie attribute:
     - Withholds the session cookie from cross-site asynchronous requests
       (fetch, XMLHttpRequest, <img>, <iframe>).
     - Withholds the cookie from cross-site top-level non-GET navigations
       (such as cross-site <form method="POST"> submissions).
     - HOWEVER, the cookie IS sent on cross-site top-level GET navigations
       (such as clicking a normal link <a href="...">). Therefore, NO state-changing
       operation may ever be implemented using the HTTP GET method. All mutations
       must use POST, PUT, PATCH, or DELETE.

  2. Why CORS is NOT a CSRF defense:
     - CORS (Cross-Origin Resource Sharing) does NOT prevent a browser from
       sending a request to the server. It only controls whether the browser
       allows JavaScript on the calling page to read the server's response.
     - "Simple" cross-origin requests (such as form POSTs or text/plain POSTs)
       are dispatched immediately by the browser without a preflight OPTIONS check.
       Even if CORS blocks the response from being read, the state-changing action
       on the server would have already executed.

  3. Same-site vs same-origin and the explicit Origin check:
     - "Same-site" (defined by registrable domain / eTLD+1) is broader than "same-origin"
       (which requires identical scheme, host, and port).
     - Two different ports on localhost (e.g. localhost:3000 and localhost:9999) or
       different subdomains share the same site. A page on another port could therefore
       trigger requests that attach SameSite=Lax cookies.
     - To close this gap, our OriginCheckMiddleware verifies the Origin header on
       every state-changing request (POST, PUT, PATCH, DELETE). If an Origin header is
       present and does not match our explicit allowed list (cors_origins_list), the
       server immediately rejects the request with HTTP 403 Forbidden without
       executing the route handler. Requests without an Origin header (such as curl
       or native API clients) remain allowed.
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

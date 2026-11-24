"""Repositories package — database access layer."""
from app.repositories.document_repository import (
    DuplicateDocumentError,
    count_documents,
    create_document,
    delete_document,
    find_by_sha256,
    get_document,
    list_documents,
)
from app.repositories.project_repository import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.repositories.session_repository import (
    create_session,
    delete_expired_sessions,
    delete_session_by_token,
    get_session_by_token,
)
from app.repositories.user_repository import (
    DuplicateEmailError,
    create_user,
    get_user_by_email,
    get_user_by_id,
)

__all__ = [
    "DuplicateDocumentError",
    "DuplicateEmailError",
    "count_documents",
    "create_document",
    "create_project",
    "create_session",
    "create_user",
    "delete_document",
    "delete_expired_sessions",
    "delete_project",
    "delete_session_by_token",
    "find_by_sha256",
    "get_document",
    "get_project",
    "get_session_by_token",
    "get_user_by_email",
    "get_user_by_id",
    "list_documents",
    "list_projects",
    "update_project",
]

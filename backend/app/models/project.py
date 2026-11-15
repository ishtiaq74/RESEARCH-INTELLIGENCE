"""SQLAlchemy ORM model for projects.

WHY A SEPARATE FILE:
  Keeping the Project model in its own module mirrors the structure of user.py
  and prevents the models package from growing into an unmaintainable monolith.
  Each model file declares one domain object.

WHY owner_id IS NOT NULLABLE:
  Every project must belong to a user.  A project without an owner would be
  invisible and unmanageable.  NOT NULL + FK enforces this at the database
  level so orphan rows are structurally impossible.

WHY OWNERSHIP BELONGS IN THE DATA LAYER:
  Enforcing owner_id only in the router leaves a gap: any internal call
  (service, background job, future endpoint) can bypass the check if the
  developer forgets to add it.  Putting owner_id in every repository query
  means the filter is always present, regardless of the caller.  A query like
  "get project by id" that ignores owner_id would expose every user's data to
  the first caller — the router cannot be the last line of defense.
"""
from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.user import Base, User


class Project(Base):
    """A research project owned by a single user.

    Columns
    -------
    id         : surrogate primary key
    owner_id   : FK → users.id (NOT NULL, indexed, CASCADE DELETE)
    name       : human-readable project name (max 200 chars)
    created_at : UTC timestamp, set once at insert
    updated_at : UTC timestamp, updated on every write
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )

    owner: Mapped[User] = relationship("User", back_populates="projects")

    def __repr__(self) -> str:
        return f"<Project id={self.id} owner_id={self.owner_id} name={self.name!r}>"

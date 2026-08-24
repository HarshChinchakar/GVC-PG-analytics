"""Application users and their location access grants.

Only two kinds of humans log in: the owner (super admin) and per-PG managers.
Residents are records, never users -- there is no resident portal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole, sql_in
from app.core.types import GUID, TZDateTime
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.location import Location


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person who can log into the portal.

    `password_hash` is nullable on purpose: in production Supabase Auth owns the
    credential and this row is only the profile plus role, linked by
    `auth_user_id`. Locally we authenticate against the hash so development does
    not require a Supabase project.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, unique=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    location_grants: Mapped[list["UserLocation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(sql_in("role", UserRole), name="role_valid"),
        CheckConstraint("length(trim(email)) > 0", name="email_not_blank"),
    )

    # -- convenience, used by the access layer -----------------------------
    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def granted_location_ids(self) -> set[uuid.UUID]:
        return {g.location_id for g in self.location_grants}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} role={self.role}>"


class UserLocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one manager access to one PG.

    Modelled as a join table rather than a `location_id` column on `users`
    because the owner has already said locations 4 and 5 are coming, and a
    manager covering two buildings during a handover is an ordinary situation
    that should not require a schema change. Super admins need no rows here --
    their access is implied by their role.
    """

    __tablename__ = "user_locations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="location_grants")
    location: Mapped["Location"] = relationship(back_populates="user_grants")

    __table_args__ = (
        UniqueConstraint("user_id", "location_id", name="user_location_unique"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserLocation user={self.user_id} location={self.location_id}>"

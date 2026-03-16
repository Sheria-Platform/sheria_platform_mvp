# services/api/app/memory/user_repository.py
"""User account CRUD -- registration, approval, activation, status management."""

from datetime import datetime, timedelta

from sqlalchemy import select, update

from services.api.app.config import settings
from services.api.app.memory.models import AsyncSessionLocal, User


def _user_to_dict(row: User) -> dict:
    """Serialise a ``User`` ORM row to a plain dict (excludes hashed_password from most uses)."""
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "full_name": row.full_name,
        "role": row.role,
        "court_station": row.court_station,
        "staff_number": row.staff_number,
        "status": row.status,
        "hashed_password": row.hashed_password,
        "activation_token": row.activation_token,
        "approved_by": row.approved_by,
        "activation_token_expires_at": row.activation_token_expires_at.isoformat()
        if row.activation_token_expires_at
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    }


class UserRepository:
    """Async repository for user account management."""

    async def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        court_station: str,
        role: str,
        staff_number: str | None = None,
    ) -> None:
        """Insert a new user row with status ``pending``.

        Called when judicial staff submit a registration request.  The
        account cannot be used until an administrator approves it and the
        user activates it via the emailed link.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    User(
                        username=username,
                        email=email,
                        full_name=full_name,
                        court_station=court_station,
                        role=role,
                        staff_number=staff_number,
                        status="pending",
                    )
                )

    async def get_user_by_username(self, username: str) -> dict | None:
        """Return a user dict by username, or ``None`` if not found.

        Used during login and registration uniqueness checks.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_email(self, email: str) -> dict | None:
        """Return a user dict by email address, or ``None`` if not found.

        Used during registration to enforce email uniqueness.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.email == email))
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> dict | None:
        """Return a user dict by primary-key UUID, or ``None`` if not found."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_activation_token(self, token: str) -> dict | None:
        """Return a user in ``approved`` status matching the one-time token.

        Returns ``None`` if the token is unknown or the account has already
        been activated (status transitions away from ``approved`` on use).
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(
                    User.activation_token == token,
                    User.status == "approved",
                    User.activation_token_expires_at > datetime.utcnow(),
                )
            )
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_pending_users(self) -> list[dict]:
        """Return all users with status ``pending``, newest-first.

        Called by the admin approval endpoint to list unreviewed requests.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User)
                .where(User.status == "pending")
                .order_by(User.created_at.desc())
            )
            rows = result.scalars().all()
            return [_user_to_dict(r) for r in rows]

    async def approve_user(
        self,
        user_id: str,
        role: str,
        activation_token: str,
        approved_by: str,
    ) -> None:
        """Transition a user from ``pending`` to ``approved`` and store the
        one-time ``activation_token``.

        The administrator may override the role requested during registration.
        The token is later consumed by ``activate_user``.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(
                        status="approved",
                        role=role,
                        activation_token=activation_token,
                        activation_token_expires_at=datetime.utcnow()
                        + timedelta(days=settings.ACTIVATION_TOKEN_TTL_DAYS),
                        approved_by=approved_by,
                    )
                )

    async def activate_user(self, user_id: str, hashed_password: str) -> None:
        """Set the user's bcrypt password hash, mark status ``active``, and
        consume the one-time activation token.

        After this call the user can log in via ``POST /api/v1/auth/login``.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(
                        status="active",
                        hashed_password=hashed_password,
                        activation_token=None,
                        activated_at=datetime.utcnow(),
                    )
                )

    async def get_users(self, status: str | None = None) -> list[dict]:
        """Return all users, optionally filtered by status, newest-first.

        Args:
            status: Optional status filter (``"pending"``, ``"active"``,
                ``"suspended"``, ``"approved"``).  ``None`` returns all users.
        """
        async with AsyncSessionLocal() as session:
            query = select(User).order_by(User.created_at.desc())
            if status is not None:
                query = query.where(User.status == status)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [_user_to_dict(r) for r in rows]

    async def update_user_status(self, user_id: str, new_status: str) -> bool:
        """Set the ``status`` field on a user row.

        Args:
            user_id: Primary-key UUID of the user to update.
            new_status: Target status string (e.g. ``"suspended"`` or ``"active"``).

        Returns:
            ``True`` if a row was matched and updated, ``False`` if not found.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await session.execute(
                    update(User).where(User.id == user_id).values(status=new_status)
                )
                return result.rowcount > 0  # type: ignore[attr-defined]

    async def seed_admin(
        self,
        username: str,
        email: str,
        full_name: str,
        hashed_password: str,
    ) -> bool:
        """Create the default admin account if no admin user exists yet.

        Idempotent -- safe to call on every startup.  Does nothing if any
        user with ``role="admin"`` already exists in the database.

        Args:
            username: Login username for the admin account.
            email: Email address for the admin account.
            full_name: Display name shown in the UI.
            hashed_password: Bcrypt hash of the initial password.

        Returns:
            ``True`` if the admin was created, ``False`` if one already exists.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.role == "admin").limit(1)
            )
            if result.scalar_one_or_none() is not None:
                return False

        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    User(
                        username=username,
                        email=email,
                        full_name=full_name,
                        hashed_password=hashed_password,
                        role="admin",
                        court_station="Judiciary Headquarters",
                        status="active",
                        activated_at=datetime.utcnow(),
                    )
                )
        return True


# Global singleton -- stateless; no lifecycle management required
user_repository = UserRepository()

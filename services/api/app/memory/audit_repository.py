# services/api/app/memory/audit_repository.py
"""Thin repository for admin audit log persistence."""

from datetime import datetime

from sqlalchemy import select

from services.api.app.memory.models import AdminAuditLog, AsyncSessionLocal


class AuditRepository:
    """Async repository for writing and reading admin audit log entries."""

    async def log_action(
        self,
        admin_id: str,
        action: str,
        target_user_id: str | None = None,
        detail: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Persist a single audit event.

        Args:
            admin_id:       ID of the admin performing the action.
            action:         Short action label: ``"approve"``, ``"suspend"``,
                            ``"reactivate"``, or ``"role_change"``.
            target_user_id: ID of the user affected (``None`` for non-user actions).
            detail:         Arbitrary JSON-serialisable dict with extra context
                            (e.g. ``{"old_role": "clerk", "new_role": "registrar"}``).
            ip_address:     Client IP extracted from the request (max 45 chars for IPv6).
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    AdminAuditLog(
                        admin_id=admin_id,
                        target_user_id=target_user_id,
                        action=action,
                        detail=detail,
                        ip_address=ip_address,
                        created_at=datetime.utcnow(),
                    )
                )

    async def get_recent_logs(self, limit: int = 200) -> list[dict]:
        """Return the most recent audit log entries, newest first.

        Args:
            limit: Maximum number of rows to return (default 200).

        Returns:
            List of dicts with keys: ``id``, ``admin_id``, ``target_user_id``,
            ``action``, ``detail``, ``ip_address``, ``created_at``.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AdminAuditLog)
                .order_by(AdminAuditLog.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "admin_id": r.admin_id,
                    "target_user_id": r.target_user_id,
                    "action": r.action,
                    "detail": r.detail,
                    "ip_address": r.ip_address,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]


# Global singleton
audit_repository = AuditRepository()

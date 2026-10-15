"""
Audit service — the only way audit rows get written.

record() adds the row to the caller's session but does NOT commit:
the calling service commits once, so the business change and its
audit row are saved together or not at all.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


def record(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    changes: dict | None = None,
    description: str | None = None,
) -> None:
    """Queue an audit row. actor is a Clerk user ID, or 'system' for jobs."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            description=description,
        )
    )

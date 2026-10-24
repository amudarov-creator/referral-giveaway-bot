"""Append-only audit log writer with hash chain."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.services.crypto import canonical_json, sha256_hex


async def write_audit(
    session: AsyncSession,
    *,
    actor_id: int | None,
    actor_type: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    giveaway_id: str | None = None,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    last_seq = await session.scalar(select(func.coalesce(func.max(AuditLog.seq), 0)))
    next_seq = (last_seq or 0) + 1

    last_entry = await session.scalar(
        select(AuditLog).where(AuditLog.seq == last_seq) if last_seq else select(AuditLog).limit(0)
    )
    prev_hash = last_entry.entry_hash if last_entry else None

    body = {
        "seq": next_seq,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "giveaway_id": giveaway_id,
        "payload": payload or {},
        "reason": reason,
        "prev_hash": prev_hash,
    }
    entry_hash = sha256_hex(canonical_json(body))

    entry = AuditLog(
        seq=next_seq,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        giveaway_id=giveaway_id,
        payload=payload or {},
        reason=reason,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    session.add(entry)
    await session.flush()
    return entry

"""Fair draw execution with commit-reveal."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.draw import Draw, DrawWinner
from app.models.giveaway import Giveaway, GiveawayPrize, GiveawayStatus
from app.models.ticket import Ticket, TicketStatus
from app.services.audit import write_audit
from app.services.crypto import (
    compute_commitment,
    generate_seed,
    protocol_hash,
    snapshot_hash,
    verify_commitment,
    weighted_draw,
)

logger = get_logger(__name__)

ALGORITHM = "weighted_csprng_v1"


class DrawService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_seed_commitment(self, giveaway_id: str, admin_id: int) -> dict[str, str]:
        """Generate seed and publish commitment before final snapshot."""
        giveaway = await self.session.get(Giveaway, giveaway_id)
        if giveaway is None:
            raise ValueError("giveaway_not_found")
        if giveaway.status not in (GiveawayStatus.ENDED, GiveawayStatus.VERIFICATION):
            raise ValueError(f"invalid_status_{giveaway.status}")
        if giveaway.seed_commitment:
            raise ValueError("commitment_already_exists")

        seed = generate_seed(32)
        commitment = compute_commitment(seed, giveaway_id)

        giveaway.seed_commitment = commitment
        giveaway.seed_commitment_published_at = utcnow()

        draw = Draw(
            giveaway_id=giveaway_id,
            draw_number=1,
            snapshot_hash="pending",
            snapshot_data={},
            seed_commitment=commitment,
            seed_revealed=seed,
            algorithm=ALGORITHM,
        )
        self.session.add(draw)

        await write_audit(
            self.session,
            actor_id=admin_id,
            actor_type="admin",
            action="seed_commitment_published",
            entity_type="giveaway",
            entity_id=giveaway_id,
            giveaway_id=giveaway_id,
            payload={"commitment": commitment},
        )
        await self.session.flush()
        return {"commitment": commitment, "draw_id": str(draw.id)}

    async def finalize_draw(self, giveaway_id: str, admin_id: int) -> Draw:
        """Freeze snapshot, reveal seed, run algorithm, store winners. Idempotent."""
        giveaway = await self.session.get(
            Giveaway,
            giveaway_id,
            options=[selectinload(Giveaway.prizes)],
        )
        if giveaway is None:
            raise ValueError("giveaway_not_found")
        if giveaway.status == GiveawayStatus.FINALIZED:
            existing = await self.session.scalar(
                select(Draw).where(Draw.giveaway_id == giveaway_id).order_by(Draw.id.desc())
            )
            if existing and existing.finalized_at:
                return existing
            raise ValueError("finalized_but_no_draw")

        if giveaway.status not in (GiveawayStatus.VERIFICATION, GiveawayStatus.ENDED):
            raise ValueError(f"invalid_status_{giveaway.status}")

        if not giveaway.seed_commitment:
            raise ValueError("no_seed_commitment")

        draw = await self.session.scalar(
            select(Draw).where(
                and_(Draw.giveaway_id == giveaway_id, Draw.snapshot_hash == "pending")
            )
        )
        if draw is None or not draw.seed_revealed:
            raise ValueError("seed_not_available")

        seed = draw.seed_revealed
        if not verify_commitment(seed, giveaway_id, giveaway.seed_commitment):
            raise ValueError("commitment_mismatch")

        tickets = (
            await self.session.execute(
                select(Ticket).where(
                    and_(
                        Ticket.giveaway_id == giveaway_id,
                        Ticket.status == TicketStatus.ACTIVE,
                    )
                )
            )
        ).scalars().all()

        by_user: dict[int, dict[str, Any]] = {}
        for t in tickets:
            if t.user_id not in by_user:
                by_user[t.user_id] = {"user_id": t.user_id, "tickets": 0, "ticket_ids": []}
            by_user[t.user_id]["tickets"] += t.weight
            by_user[t.user_id]["ticket_ids"].append(t.id)

        participants = sorted(by_user.values(), key=lambda x: x["user_id"])
        one_prize = bool(giveaway.settings.get("one_prize_per_user", True))

        prizes = sorted(
            [p for p in giveaway.prizes if not p.is_leader_prize],
            key=lambda p: p.place,
        )
        num_winners = sum(p.quantity for p in prizes)

        snapshot = {
            "giveaway_id": giveaway_id,
            "rules_version": giveaway.rules_version,
            "rules_hash": giveaway.rules_hash,
            "participants": participants,
            "prizes": [
                {"place": p.place, "title": p.title, "quantity": p.quantity}
                for p in prizes
            ],
            "algorithm": ALGORITHM,
            "one_prize_per_user": one_prize,
            "num_winners": num_winners,
        }
        snap_hash = snapshot_hash(snapshot)

        winners_raw = weighted_draw(
            participants,
            num_winners,
            seed,
            snap_hash,
            one_prize_per_user=one_prize,
        )

        winner_rows: list[dict[str, Any]] = []
        prize_queue: list[tuple[int, str]] = []
        for p in prizes:
            for _ in range(p.quantity):
                prize_queue.append((p.place, p.title))

        for i, w in enumerate(winners_raw):
            place, title = prize_queue[i] if i < len(prize_queue) else (i + 1, "Prize")
            winner_rows.append(
                {
                    "place": place,
                    "user_id": w["user_id"],
                    "tickets": w["tickets"],
                    "prize_title": title,
                    "is_leader_prize": False,
                }
            )

        leader_prize = next((p for p in giveaway.prizes if p.is_leader_prize), None)
        if leader_prize and participants:
            leader = max(participants, key=lambda x: (x["tickets"], -x["user_id"]))
            if not (one_prize and any(r["user_id"] == leader["user_id"] for r in winner_rows)):
                winner_rows.append(
                    {
                        "place": 0,
                        "user_id": leader["user_id"],
                        "tickets": leader["tickets"],
                        "prize_title": leader_prize.title,
                        "is_leader_prize": True,
                    }
                )

        proto = protocol_hash(seed, snap_hash, winner_rows, ALGORITHM)

        draw.snapshot_hash = snap_hash
        draw.snapshot_data = snapshot
        draw.results = {"winners": winner_rows}
        draw.protocol_hash = proto
        draw.finalized_at = utcnow()

        for wr in winner_rows:
            self.session.add(
                DrawWinner(
                    draw_id=draw.id,
                    user_id=wr["user_id"],
                    place=wr["place"],
                    prize_title=wr["prize_title"],
                    ticket_count=wr["tickets"],
                    is_leader_prize=wr["is_leader_prize"],
                )
            )

        giveaway.status = GiveawayStatus.FINALIZED

        await write_audit(
            self.session,
            actor_id=admin_id,
            actor_type="admin",
            action="draw_finalized",
            entity_type="draw",
            entity_id=str(draw.id),
            giveaway_id=giveaway_id,
            payload={
                "snapshot_hash": snap_hash,
                "protocol_hash": proto,
                "winners_count": len(winner_rows),
            },
        )
        await self.session.flush()
        return draw

    async def verify_protocol(
        self,
        seed: str,
        giveaway_id: str,
        snapshot: dict[str, Any],
        expected_winners: list[dict[str, Any]],
        commitment: str,
    ) -> bool:
        """Independent verification of a published protocol."""
        if not verify_commitment(seed, giveaway_id, commitment):
            return False
        snap_hash = snapshot_hash(snapshot)
        one_prize = snapshot.get("one_prize_per_user", True)
        num = snapshot.get("num_winners", 0)
        computed = weighted_draw(
            snapshot["participants"],
            num,
            seed,
            snap_hash,
            one_prize_per_user=one_prize,
        )
        if len(computed) != len([w for w in expected_winners if not w.get("is_leader_prize")]):
            return False
        for c, e in zip(
            computed,
            [w for w in expected_winners if not w.get("is_leader_prize")],
            strict=True,
        ):
            if c["user_id"] != e["user_id"]:
                return False
        return True

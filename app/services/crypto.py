"""Cryptographic utilities for commit-reveal draws."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Sequence


def canonical_json(data: Any) -> bytes:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def generate_seed(nbytes: int = 32) -> str:
    """CSPRNG seed as hex string."""
    return secrets.token_hex(nbytes)


def compute_commitment(seed: str, giveaway_id: str) -> str:
    """SHA-256(seed || giveaway_id) commitment."""
    return sha256_hex(f"{seed}:{giveaway_id}")


def verify_commitment(seed: str, giveaway_id: str, commitment: str) -> bool:
    return hmac.compare_digest(compute_commitment(seed, giveaway_id), commitment)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(snapshot))


def weighted_draw(
    participants: Sequence[dict[str, Any]],
    num_winners: int,
    seed: str,
    snapshot_hash_value: str,
    one_prize_per_user: bool = True,
) -> list[dict[str, Any]]:
    """Reproducible weighted random selection via HMAC-DRBG."""
    if not participants or num_winners <= 0:
        return []

    material = f"{seed}:{snapshot_hash_value}".encode()
    counter = 0
    pool: list[int] = []

    def next_int(bound: int) -> int:
        nonlocal counter, pool
        if bound <= 0:
            raise ValueError("bound must be positive")
        while True:
            while len(pool) < 8:
                block = hmac.new(
                    material, counter.to_bytes(8, "big"), hashlib.sha256
                ).digest()
                counter += 1
                pool.extend(block)
            raw = int.from_bytes(bytes(pool[:8]), "big")
            pool = pool[8:]
            limit = (2**64 // bound) * bound
            if raw < limit:
                return raw % bound

    indices: list[int] = []
    for i, p in enumerate(participants):
        tickets = max(0, int(p.get("tickets", 0)))
        indices.extend([i] * tickets)

    if not indices:
        return []

    winners: list[dict[str, Any]] = []
    selected_users: set[int] = set()
    remaining = list(indices)

    place = 1
    while remaining and len(winners) < num_winners:
        pick = next_int(len(remaining))
        idx = remaining[pick]
        user_id = participants[idx]["user_id"]

        if one_prize_per_user and user_id in selected_users:
            remaining = [i for i in remaining if participants[i]["user_id"] != user_id]
            continue

        winners.append(
            {
                "place": place,
                "user_id": user_id,
                "tickets": participants[idx]["tickets"],
                "index": idx,
            }
        )
        selected_users.add(user_id)
        place += 1
        remaining = [i for i in remaining if participants[i]["user_id"] != user_id]

    return winners


def protocol_hash(
    seed: str,
    snapshot_hash_value: str,
    winners: list[dict[str, Any]],
    algorithm: str,
) -> str:
    payload = {
        "seed": seed,
        "snapshot_hash": snapshot_hash_value,
        "winners": winners,
        "algorithm": algorithm,
    }
    return sha256_hex(canonical_json(payload))

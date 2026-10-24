"""Unit tests for commit-reveal and weighted draw."""

import pytest
from hypothesis import given, settings, strategies as st

from app.services.crypto import (
    compute_commitment,
    generate_seed,
    protocol_hash,
    snapshot_hash,
    verify_commitment,
    weighted_draw,
)


def test_commitment_roundtrip():
    seed = generate_seed()
    gid = "test-giveaway-id"
    c = compute_commitment(seed, gid)
    assert verify_commitment(seed, gid, c)
    assert not verify_commitment(seed + "x", gid, c)
    assert not verify_commitment(seed, gid + "x", c)


def test_weighted_draw_reproducible():
    participants = [
        {"user_id": 1, "tickets": 3},
        {"user_id": 2, "tickets": 1},
        {"user_id": 3, "tickets": 2},
    ]
    seed = "abc123"
    snap = snapshot_hash({"participants": participants})
    w1 = weighted_draw(participants, 2, seed, snap, one_prize_per_user=True)
    w2 = weighted_draw(participants, 2, seed, snap, one_prize_per_user=True)
    assert w1 == w2
    assert len(w1) == 2
    assert w1[0]["user_id"] != w1[1]["user_id"]


def test_weighted_draw_respects_one_prize():
    participants = [{"user_id": 1, "tickets": 100}, {"user_id": 2, "tickets": 1}]
    seed = "seed"
    snap = "hash"
    winners = weighted_draw(participants, 2, seed, snap, one_prize_per_user=True)
    user_ids = [w["user_id"] for w in winners]
    assert len(user_ids) == len(set(user_ids))


def test_empty_participants():
    assert weighted_draw([], 5, "s", "h") == []


@given(
    tickets=st.lists(st.integers(min_value=1, max_value=20), min_size=1, max_size=15),
    seed=st.text(min_size=8, max_size=32, alphabet="0123456789abcdef"),
)
@settings(max_examples=50)
def test_draw_deterministic_property(tickets, seed):
    participants = [{"user_id": i + 1, "tickets": t} for i, t in enumerate(tickets)]
    snap = snapshot_hash({"p": participants})
    a = weighted_draw(participants, min(3, len(participants)), seed, snap)
    b = weighted_draw(participants, min(3, len(participants)), seed, snap)
    assert a == b


def test_protocol_hash_stable():
    h1 = protocol_hash("seed", "snap", [{"user_id": 1}], "algo")
    h2 = protocol_hash("seed", "snap", [{"user_id": 1}], "algo")
    assert h1 == h2
    assert h1 != protocol_hash("seed2", "snap", [{"user_id": 1}], "algo")

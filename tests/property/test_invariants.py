"""Property-based invariants for referral and ticket logic."""

from hypothesis import given, settings, strategies as st

from app.services.crypto import weighted_draw, snapshot_hash


@given(
    n_users=st.integers(min_value=1, max_value=30),
    ticket_counts=st.lists(st.integers(min_value=0, max_value=10), min_size=1, max_size=30),
)
@settings(max_examples=30)
def test_one_prize_per_user_invariant(n_users, ticket_counts):
    """No user appears twice when one_prize_per_user=True."""
    n = min(n_users, len(ticket_counts))
    participants = [
        {"user_id": i + 1, "tickets": ticket_counts[i]} for i in range(n) if ticket_counts[i] > 0
    ]
    if not participants:
        return
    seed = "fixed-seed-for-property"
    snap = snapshot_hash({"participants": participants})
    winners = weighted_draw(participants, min(5, len(participants)), seed, snap, True)
    user_ids = [w["user_id"] for w in winners]
    assert len(user_ids) == len(set(user_ids))


@given(st.lists(st.integers(min_value=1, max_value=5), min_size=2, max_size=10))
@settings(max_examples=20)
def test_draw_result_bounded(tickets):
    participants = [{"user_id": i, "tickets": t} for i, t in enumerate(tickets, 1)]
    snap = "x"
    winners = weighted_draw(participants, 100, "s", snap, True)
    assert len(winners) <= len(participants)

from datetime import UTC, datetime, timedelta

from src.domain.demande.entities import Status
from src.domain.demande.priority import (
    PriorityLevel,
    compute_score,
    is_late,
    late_since,
    level_for,
)

NOW = datetime.now(UTC)


def test_score_levels():
    hot = compute_score(urgency=5, affected_citizens=50, created_at=NOW, category="Sécurité", now=NOW)
    assert level_for(hot.total) is PriorityLevel.CRITIQUE, hot
    default = compute_score(urgency=3, affected_citizens=1, created_at=NOW, category="voirie", now=NOW)
    assert level_for(default.total) is PriorityLevel.MOYENNE, default
    low = compute_score(urgency=1, affected_citizens=1, created_at=NOW, category="espaces_verts", now=NOW)
    assert level_for(low.total) is PriorityLevel.FAIBLE


def test_score_age_and_bounds():
    old = compute_score(urgency=99, affected_citizens=0, created_at=NOW - timedelta(days=40), category="??", now=NOW)
    assert old.urgency == 30 and old.age == 20 and old.affected == 0
    assert 0 <= old.total <= 100
    naive = compute_score(urgency=3, affected_citizens=10, created_at=NOW.replace(tzinfo=None), category="eau", now=NOW)
    assert naive.age == 0


def test_late_rules():
    kw = dict(scheduled_at=None, updated_at=NOW)
    assert is_late(Status.NOUVEAU, created_at=NOW - timedelta(days=4), now=NOW, **kw)
    assert not is_late(Status.NOUVEAU, created_at=NOW - timedelta(days=1), now=NOW, **kw)
    assert not is_late(Status.RESOLU, created_at=NOW - timedelta(days=99), now=NOW, **kw)
    assert is_late(Status.EN_COURS, created_at=NOW, scheduled_at=NOW - timedelta(hours=1), updated_at=NOW, now=NOW)
    assert late_since(Status.EN_COURS, created_at=NOW, scheduled_at=None, updated_at=NOW) is None



"""Priorisation automatique (T+8h) et règles de retard.

Score sur 100 = urgence (30) + citoyens concernés (25) + ancienneté (20) + criticité (25).
Niveaux : >= 70 CRITIQUE, >= 50 HAUTE, >= 30 MOYENNE, sinon FAIBLE.
Fonctions pures, sans base de données : faciles à tester et à ajuster pendant le hackathon.
"""

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import log10
from typing import Protocol

from src.domain.demande.entities import Status

URGENCY_MIN = 1
URGENCY_MAX = 5
DEFAULT_URGENCY = 3

WEIGHT_URGENCY = 30
WEIGHT_AFFECTED = 25
WEIGHT_AGE = 20
WEIGHT_CRITICALITY = 25

AFFECTED_SATURATION = 100  # à partir de 100 citoyens concernés, la composante est au maximum
AGE_SATURATION_DAYS = 10  # à partir de 10 jours d'ancienneté, idem

# Criticité par catégorie (0 à 1), clés normalisées : sans accent, minuscules, « _ ».
_CATEGORY_CRITICALITY = {
    "securite": 1.0,
    "eau": 0.9,
    "eclairage_public": 0.7,
    "voirie": 0.6,
    "dechets": 0.4,
    "espaces_verts": 0.2,
    "autre": 0.1,
}
_DEFAULT_CRITICALITY = 0.3

# Retards : délais au-delà desquels une demande est considérée « en retard ».
NEW_MAX_AGE = timedelta(days=3)  # « nouveau » non traité
WAITING_MAX_AGE = timedelta(days=7)  # « en attente » sans mouvement

OPEN_STATUSES = (Status.NOUVEAU, Status.EN_COURS, Status.EN_ATTENTE)


class PriorityLevel(StrEnum):
    CRITIQUE = "critique"
    HAUTE = "haute"
    MOYENNE = "moyenne"
    FAIBLE = "faible"


_LEVEL_THRESHOLDS = (
    (70, PriorityLevel.CRITIQUE),
    (50, PriorityLevel.HAUTE),
    (30, PriorityLevel.MOYENNE),
)


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    urgency: int
    affected: int
    age: int
    criticality: int

    @property
    def total(self) -> int:
        return self.urgency + self.affected + self.age + self.criticality


def as_utc(value: datetime) -> datetime:
    # SQLite renvoie des datetimes sans fuseau : on les considère comme UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _category_key(category: object) -> str:
    raw = str(getattr(category, "value", category))
    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return ascii_text.strip().lower().replace(" ", "_").replace("-", "_")


def compute_score(
    *,
    urgency: int,
    affected_citizens: int,
    created_at: datetime,
    category: object,
    now: datetime | None = None,
) -> ScoreBreakdown:
    now = as_utc(now) if now else datetime.now(UTC)
    urgency = min(max(urgency, URGENCY_MIN), URGENCY_MAX)
    affected = max(affected_citizens, 1)
    age_days = max((now - as_utc(created_at)).total_seconds() / 86400, 0.0)
    criticality = _CATEGORY_CRITICALITY.get(_category_key(category), _DEFAULT_CRITICALITY)

    return ScoreBreakdown(
        urgency=round(WEIGHT_URGENCY * (urgency - URGENCY_MIN) / (URGENCY_MAX - URGENCY_MIN)),
        affected=round(WEIGHT_AFFECTED * min(log10(affected) / log10(AFFECTED_SATURATION), 1.0)),
        age=round(WEIGHT_AGE * min(age_days / AGE_SATURATION_DAYS, 1.0)),
        criticality=round(WEIGHT_CRITICALITY * criticality),
    )


def level_for(score: int) -> PriorityLevel:
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level

    return PriorityLevel.FAIBLE


def late_since(
    status: Status,
    *,
    created_at: datetime,
    scheduled_at: datetime | None,
    updated_at: datetime,
) -> datetime | None:
    """Date à partir de laquelle la demande est en retard (None : pas de règle de retard)."""
    if status is Status.NOUVEAU:
        return as_utc(created_at) + NEW_MAX_AGE
    if status is Status.EN_COURS:
        return as_utc(scheduled_at) if scheduled_at else None
    if status is Status.EN_ATTENTE:
        return as_utc(updated_at) + WAITING_MAX_AGE

    return None


def is_late(
    status: Status,
    *,
    created_at: datetime,
    scheduled_at: datetime | None,
    updated_at: datetime,
    now: datetime | None = None,
) -> bool:
    deadline = late_since(
        status, created_at=created_at, scheduled_at=scheduled_at, updated_at=updated_at
    )

    return deadline is not None and deadline <= (as_utc(now) if now else datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PriorityItem:
    """Une demande dans la file priorisée."""

    id: str
    title: str
    category: str
    status: str
    priority: str
    priority_score: int
    urgency: int
    affected_citizens: int
    created_at: datetime
    agent_id: str | None
    address: str | None
    is_late: bool


class PriorityRepository(Protocol):
    def refresh_scores(self, *, demande_id: str | None = None, now: datetime | None = None) -> int:
        """Recalcule score et priorité des demandes ouvertes ; renvoie le nombre de changements de niveau."""
        ...

    def update_inputs(
        self,
        demande_id: str,
        *,
        urgency: int | None,
        affected_citizens: int | None,
        actor_id: str,
        actor_name: str,
    ) -> None: ...

    def get_item(self, demande_id: str) -> PriorityItem | None: ...

    def ranked(
        self,
        *,
        citizen_id: str | None,
        agent_id: str | None,
        status: Status | None,
        include_closed: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[PriorityItem], int]: ...

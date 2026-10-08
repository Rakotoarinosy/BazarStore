"""Règles métier du cycle de vie d'une demande : quelles transitions de statut sont permises."""

from src.domain.demande.entities import Status
from src.domain.demande.exceptions import InvalidStatusTransitionError

_ALLOWED_TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.NOUVEAU: frozenset({Status.EN_COURS, Status.REJETE}),
    Status.EN_COURS: frozenset({Status.EN_ATTENTE, Status.RESOLU, Status.REJETE}),
    Status.EN_ATTENTE: frozenset({Status.EN_COURS, Status.REJETE}),
    Status.RESOLU: frozenset(),  # état final
    Status.REJETE: frozenset(),  # état final
}


def ensure_transition(current: Status, target: Status) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidStatusTransitionError(current.value, target.value)

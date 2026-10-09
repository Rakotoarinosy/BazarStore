"""Diffusion en temps réel (SSE) du nombre de commandes ouvertes au backoffice.

Un écouteur SQLAlchemy incrémente un numéro de version à chaque commit qui touche une commande
(création, paiement, changement de statut) : les flux SSE ouverts dans ce processus le voient
immédiatement. Une relecture périodique en base couvre les changements faits par un autre
processus du serveur (plusieurs workers uvicorn / Passenger).
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from itertools import chain

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.persistence.models import OrderModel

# Commandes ni livrées ni annulées (badge du menu « Commandes »).
OPEN_ORDER_STATUSES = ("pending", "confirmed", "processing", "shipped")

TICK_SECONDS = 0.5  # réactivité aux changements faits dans ce processus
DB_RECHECK_SECONDS = 5.0  # changements faits par un autre processus
HEARTBEAT_SECONDS = 15.0  # garde la connexion ouverte à travers les proxys
# Le navigateur se reconnecte ensuite (avec un jeton d'accès frais) ; borne aussi
# l'attente d'uvicorn --reload sur les flux ouverts.
STREAM_MAX_SECONDS = 120.0


class OrderChangeNotifier:
    def __init__(self) -> None:
        self._version = 0
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        return self._version

    def bump(self) -> None:
        with self._lock:
            self._version += 1


order_changes = OrderChangeNotifier()


@event.listens_for(Session, "after_flush")
def _remember_order_changes(session: Session, _context: object) -> None:
    if any(
        isinstance(obj, OrderModel) for obj in chain(session.new, session.dirty, session.deleted)
    ):
        session.info["orders_changed"] = True


@event.listens_for(Session, "after_commit")
def _notify_order_changes(session: Session) -> None:
    if session.info.pop("orders_changed", False):
        order_changes.bump()


@event.listens_for(Session, "after_rollback")
def _forget_order_changes(session: Session) -> None:
    session.info.pop("orders_changed", None)


def count_open_orders_in(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(OrderModel)
            .where(OrderModel.status.in_(OPEN_ORDER_STATUSES))
        )
        or 0
    )


def _count_with_fresh_session(factory: sessionmaker[Session]) -> int:
    # Session courte : aucune connexion n'est gardée pendant toute la durée du flux.
    with factory() as session:
        return count_open_orders_in(session)


def _sse(event_name: str, data: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


async def open_count_events(
    is_disconnected: Callable[[], Awaitable[bool]],
    factory: sessionmaker[Session],
    *,
    max_seconds: float = STREAM_MAX_SECONDS,
) -> AsyncIterator[str]:
    """Envoie le compteur à l'ouverture, puis à chaque changement ; ping régulier sinon."""
    yield "retry: 3000\n\n"  # délai de reconnexion conseillé au client
    started = last_db_check = last_sent = time.monotonic()
    last_count: int | None = None
    last_version = -1

    while time.monotonic() - started < max_seconds:
        if await is_disconnected():
            return
        now = time.monotonic()
        version = order_changes.version
        if (
            last_count is None
            or version != last_version
            or now - last_db_check >= DB_RECHECK_SECONDS
        ):
            last_version, last_db_check = version, now
            count = await asyncio.to_thread(_count_with_fresh_session, factory)
            if count != last_count:
                last_count = count
                last_sent = now
                yield _sse("open-count", {"count": count})
                continue
        if now - last_sent >= HEARTBEAT_SECONDS:
            last_sent = now
            yield ": ping\n\n"
        await asyncio.sleep(TICK_SECONDS)

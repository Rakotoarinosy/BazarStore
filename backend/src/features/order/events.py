"""Diffusion en temps réel (Server-Sent Events) des commandes.

- Backoffice : chaque commande créée ou modifiée + le nombre de commandes ouvertes (badge).
- Client : uniquement ses propres commandes (statut, paiement, facture…).

Un écouteur SQLAlchemy incrémente un numéro de version à chaque commit qui touche une commande :
les flux ouverts dans ce processus réagissent aussitôt. Une relecture périodique en base couvre
les changements faits par un autre processus du serveur (plusieurs workers uvicorn / Passenger).
Les commandes à envoyer sont celles dont `updated_at` a avancé depuis le dernier envoi.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from itertools import chain

from sqlalchemy import Select, event, func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from src.features.order.schemas import OrderOut
from src.features.order.serialization import serialize_order
from src.infrastructure.persistence.models import OrderItemModel, OrderModel

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


# Horodatage de la dernière modification (les anciennes lignes n'ont pas d'updated_at).
_order_stamp = func.coalesce(OrderModel.updated_at, OrderModel.created_at)
# Fenêtre de recouvrement : une commande validée (commit) après une autre mais horodatée
# avant elle n'est pas manquée ; les doublons sont filtrés par `_ChangeCursor.sent`.
LOOKBACK = timedelta(seconds=10)


def _utc(value: datetime) -> datetime:
    # SQLite renvoie des dates naïves (PostgreSQL des dates avec fuseau) : tout en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class _ChangeCursor:
    """Mémorise ce qui a déjà été envoyé sur un flux pour n'envoyer que les nouveautés."""

    def __init__(self, user_id: str | None) -> None:
        self.user_id = user_id
        self.since: datetime | None = None
        self.sent: dict[str, datetime] = {}

    def _scoped(self, query: Select[tuple[OrderModel]]) -> Select[tuple[OrderModel]]:
        return query.where(OrderModel.user_id == self.user_id) if self.user_id else query

    def start(self, session: Session) -> None:
        """Part de l'état actuel, sans renvoyer tout l'historique (déjà chargé par le client).

        `sent` reste vide : les commandes modifiées dans la fenêtre LOOKBACK seront renvoyées au
        premier appel de `changes`. Cela couvre un changement survenu entre le chargement de la
        liste et l'ouverture du flux ; un éventuel doublon est sans effet (mise à jour en place).
        """
        latest = session.scalar(self._scoped(select(func.max(_order_stamp))))
        self.since = _utc(latest) if latest is not None else None

    def changes(self, session: Session) -> list[OrderOut]:
        query = self._scoped(
            select(OrderModel).options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.product)
            )
        )
        if self.since is not None:
            query = query.where(_order_stamp >= self.since - LOOKBACK)
        changed: list[OrderOut] = []
        for order in session.scalars(query.order_by(_order_stamp)):
            stamp = _utc(order.updated_at or order.created_at)
            if self.sent.get(order.id) == stamp:
                continue
            self.sent[order.id] = stamp
            self.since = stamp if self.since is None else max(self.since, stamp)
            changed.append(serialize_order(order))
        if self.since is not None:
            floor = self.since - LOOKBACK
            self.sent = {order_id: stamp for order_id, stamp in self.sent.items() if stamp >= floor}
        return changed


def _sse(event_name: str, data: object) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


async def order_events(
    is_disconnected: Callable[[], Awaitable[bool]],
    factory: sessionmaker[Session],
    *,
    user_id: str | None = None,
    include_open_count: bool = False,
    max_seconds: float = STREAM_MAX_SECONDS,
) -> AsyncIterator[str]:
    """Flux SSE : `order` (commande créée/modifiée) et, pour l'équipe, `open-count`.

    user_id=None : toutes les commandes (backoffice) ; sinon uniquement celles de ce client.
    """
    cursor = _ChangeCursor(user_id)
    last_count: int | None = None

    def poll(first: bool) -> tuple[list[OrderOut], int | None]:
        # Session courte : aucune connexion n'est gardée pendant toute la durée du flux.
        with factory() as session:
            if first:
                cursor.start(session)
            changed = cursor.changes(session)
            return changed, count_open_orders_in(session) if include_open_count else None

    yield "retry: 3000\n\n"  # délai de reconnexion conseillé au client
    started = last_db_check = last_sent = time.monotonic()
    last_version = -1
    first = True

    while time.monotonic() - started < max_seconds:
        if await is_disconnected():
            return
        now = time.monotonic()
        version = order_changes.version
        if first or version != last_version or now - last_db_check >= DB_RECHECK_SECONDS:
            last_version, last_db_check = version, now
            changed, count = await asyncio.to_thread(poll, first)
            first = False
            for order in changed:
                last_sent = now
                yield _sse("order", order.model_dump(mode="json"))
            if count is not None and count != last_count:
                last_count, last_sent = count, now
                yield _sse("open-count", {"count": count})
        if now - last_sent >= HEARTBEAT_SECONDS:
            last_sent = now
            yield ": ping\n\n"
        await asyncio.sleep(TICK_SECONDS)

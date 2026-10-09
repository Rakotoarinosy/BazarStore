"""Suivi des changements de commandes en base, pour le temps réel (Server-Sent Events).

- `order_changes` : numéro de version incrémenté par un écouteur SQLAlchemy à chaque commit qui
  touche une commande (création, paiement, statut). Les flux ouverts dans ce processus le voient
  aussitôt ; une relecture périodique couvre les changements faits par un autre processus.
- `OrderChangeCursor` : retrouve les commandes dont `updated_at` a avancé depuis le dernier envoi.
"""

import threading
from datetime import UTC, datetime, timedelta
from itertools import chain

from sqlalchemy import Select, event, func, select
from sqlalchemy.orm import Session, selectinload

from src.infrastructure.persistence.models import OrderItemModel, OrderModel

# Commandes ni livrées ni annulées (badge du menu « Commandes »).
OPEN_ORDER_STATUSES = ("pending", "confirmed", "processing", "shipped")

# Fenêtre de recouvrement : une commande validée (commit) après une autre mais horodatée
# avant elle n'est pas manquée ; les doublons sont filtrés par `OrderChangeCursor.sent`.
LOOKBACK = timedelta(seconds=10)


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


def _utc(value: datetime) -> datetime:
    # SQLite renvoie des dates naïves (PostgreSQL des dates avec fuseau) : tout en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class OrderChangeCursor:
    """Mémorise ce qui a déjà été envoyé sur un flux pour n'envoyer que les nouveautés.

    user_id=None : toutes les commandes (backoffice) ; sinon uniquement celles de ce client.
    """

    def __init__(self, user_id: str | None) -> None:
        self.user_id = user_id
        self.since: datetime | None = None
        self.sent: dict[str, datetime] = {}

    def _scoped(self, query: Select) -> Select:  # type: ignore[type-arg]
        return query.where(OrderModel.user_id == self.user_id) if self.user_id else query

    def start(self, session: Session) -> None:
        """Part de l'état actuel, sans renvoyer tout l'historique (déjà chargé par le client).

        `sent` reste vide : les commandes modifiées dans la fenêtre LOOKBACK seront renvoyées au
        premier appel de `changes`. Cela couvre un changement survenu entre le chargement de la
        liste et l'ouverture du flux ; un éventuel doublon est sans effet (mise à jour en place).
        """
        latest = session.scalar(self._scoped(select(func.max(_order_stamp))))
        self.since = _utc(latest) if latest is not None else None

    def changes(self, session: Session) -> list[OrderModel]:
        query = self._scoped(
            select(OrderModel).options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.product)
            )
        )
        if self.since is not None:
            query = query.where(self.since - LOOKBACK <= _order_stamp)
        changed: list[OrderModel] = []
        for order in session.scalars(query.order_by(_order_stamp)):
            stamp = _utc(order.updated_at or order.created_at)
            if self.sent.get(order.id) == stamp:
                continue
            self.sent[order.id] = stamp
            self.since = stamp if self.since is None else max(self.since, stamp)
            changed.append(order)
        if self.since is not None:
            floor = self.since - LOOKBACK
            self.sent = {order_id: stamp for order_id, stamp in self.sent.items() if stamp >= floor}
        return changed

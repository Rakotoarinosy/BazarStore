import json
import time

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.features.order.events import open_count_events, order_changes
from src.infrastructure.persistence.models import OrderModel, UserModel

pytestmark = pytest.mark.anyio


def _order(order_id: str, status: str = "pending") -> OrderModel:
    return OrderModel(
        id=order_id,
        reference=f"CMD-{order_id.upper()}",
        customer_name="Client",
        customer_email="client@example.com",
        status=status,
        total_amount=10_000,
    )


async def test_commits_touching_orders_bump_the_version(db_session: Session) -> None:
    start = order_changes.version

    db_session.add(UserModel(id="u-1", email="u@example.com", name="U"))
    db_session.commit()
    assert order_changes.version == start  # commit sans commande : pas de notification

    db_session.add(_order("o-1"))
    db_session.rollback()
    assert order_changes.version == start  # annulé : pas de notification

    db_session.add(_order("o-1"))
    db_session.commit()
    assert order_changes.version == start + 1

    db_session.get(OrderModel, "o-1").status = "confirmed"
    db_session.commit()
    assert order_changes.version == start + 2


async def test_stream_pushes_new_orders_immediately(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    async def connected() -> bool:
        return False

    stream = open_count_events(connected, factory, max_seconds=4)
    assert await anext(stream) == "retry: 3000\n\n"
    assert await anext(stream) == 'event: open-count\ndata: {"count": 0}\n\n'

    with factory() as session:
        session.add_all([_order("o-1"), _order("o-2", status="completed")])
        session.commit()

    started = time.monotonic()
    pushed = await anext(stream)
    # Poussé au tick suivant (≈ 0,5 s), sans attendre la relecture périodique de 5 s.
    assert time.monotonic() - started < 2
    assert pushed.startswith("event: open-count\n")
    assert json.loads(pushed.split("data: ")[1]) == {"count": 1}
    await stream.aclose()


async def test_stream_stops_when_client_disconnects(engine: Engine) -> None:
    factory = sessionmaker(bind=engine)

    async def disconnected() -> bool:
        return True

    events = [event async for event in open_count_events(disconnected, factory)]
    assert events == ["retry: 3000\n\n"]

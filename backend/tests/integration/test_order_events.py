import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.features.order.events import order_events
from src.features.order.router import make_order_poll
from src.infrastructure.persistence.models import OrderModel, UserModel
from src.infrastructure.persistence.order_feed import OrderChangeCursor, order_changes

pytestmark = pytest.mark.anyio


def _order(order_id: str, user_id: str | None = None, status: str = "pending") -> OrderModel:
    return OrderModel(
        id=order_id,
        reference=f"CMD-{order_id.upper()}",
        user_id=user_id,
        customer_name="Client",
        customer_email="client@example.com",
        status=status,
        total_amount=10_000,
    )


def _parse(event: str) -> tuple[str, dict]:
    name = event.split("\n")[0].removeprefix("event: ")
    return name, json.loads(event.split("data: ", 1)[1])


async def _connected() -> bool:
    return False


def _stream(factory: sessionmaker[Session], *, user_id: str | None, include_open_count: bool):  # type: ignore[no-untyped-def]
    poll = make_order_poll(factory, user_id=user_id, include_open_count=include_open_count)
    return order_events(_connected, poll, lambda: order_changes.version, max_seconds=10)


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                UserModel(id="alice", email="alice@example.com", name="Alice"),
                UserModel(id="bob", email="bob@example.com", name="Bob"),
            ]
        )
        session.commit()
    return factory


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


async def test_staff_stream_pushes_new_orders_status_changes_and_count(
    factory: sessionmaker[Session],
) -> None:
    stream = _stream(factory, user_id=None, include_open_count=True)
    assert await anext(stream) == "retry: 3000\n\n"
    assert _parse(await anext(stream)) == ("open-count", {"count": 0})

    with factory() as session:
        session.add(_order("o-1", "alice"))
        session.commit()
    name, order = _parse(await asyncio.wait_for(anext(stream), 2))
    assert (name, order["reference"], order["status"]) == ("order", "CMD-O-1", "pending")
    assert _parse(await anext(stream)) == ("open-count", {"count": 1})

    with factory() as session:
        session.get(OrderModel, "o-1").status = "completed"
        session.commit()
    name, order = _parse(await asyncio.wait_for(anext(stream), 2))
    assert (name, order["status"]) == ("order", "completed")
    assert _parse(await anext(stream)) == ("open-count", {"count": 0})
    await stream.aclose()


async def test_customer_stream_only_sees_own_orders(factory: sessionmaker[Session]) -> None:
    stream = _stream(factory, user_id="alice", include_open_count=False)
    assert await anext(stream) == "retry: 3000\n\n"

    # La commande de Bob est validée en premier : seule celle d'Alice doit arriver.
    with factory() as session:
        session.add(_order("o-bob", "bob"))
        session.commit()
    with factory() as session:
        session.add(_order("o-alice", "alice"))
        session.commit()
    name, order = _parse(await asyncio.wait_for(anext(stream), 2))
    assert (name, order["id"]) == ("order", "o-alice")
    await stream.aclose()


async def test_cursor_catches_orders_committed_out_of_order(factory: sessionmaker[Session]) -> None:
    now = datetime.now(UTC)
    with factory() as session:
        recent = _order("o-recent")
        recent.updated_at = now
        session.add(recent)
        session.commit()

        cursor = OrderChangeCursor(user_id=None)
        cursor.start(session)
        # Ouverture du flux : les changements récents sont renvoyés (filet de sécurité).
        assert [order.id for order in cursor.changes(session)] == ["o-recent"]

        # Horodatée avant la précédente mais validée après (transaction plus lente).
        late = _order("o-late")
        late.updated_at = now - timedelta(seconds=3)
        session.add(late)
        session.commit()

        assert [order.id for order in cursor.changes(session)] == ["o-late"]
        assert cursor.changes(session) == []  # pas de doublon


async def test_stream_stops_when_client_disconnects(factory: sessionmaker[Session]) -> None:
    async def disconnected() -> bool:
        return True

    poll = make_order_poll(factory, user_id=None, include_open_count=False)
    events = [
        event async for event in order_events(disconnected, poll, lambda: order_changes.version)
    ]
    assert events == ["retry: 3000\n\n"]

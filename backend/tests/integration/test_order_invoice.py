from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from src.domain.user import Role, User
from src.features.order.router import (
    OrderCancelledConflictError,
    OrderNotFoundError,
    download_invoice,
)
from src.infrastructure.config.settings import Settings
from src.infrastructure.persistence.models import OrderItemModel, OrderModel, UserModel
from src.shared.amount_in_words import amount_in_words

SETTINGS = Settings(invoice_seller_nif="1234567890", app_timezone="Indian/Antananarivo")


def _user(user_id: str, role: Role = Role.CUSTOMER) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        role=role,
        created_at=datetime.now(UTC),
        password_hash="",
    )


def _order(order_id: str, user_id: str, status: str = "pending") -> OrderModel:
    return OrderModel(
        id=order_id,
        reference=f"CMD-{order_id.upper()}",
        user_id=user_id,
        customer_name="Rakoto Jean",
        customer_email="rakoto@example.com",
        status=status,
        total_amount=1_328_000,
        items=[
            OrderItemModel(
                product_name="Casque audio",
                unit_price=664_000,
                quantity=2,
                line_total=1_328_000,
            )
        ],
    )


@pytest.fixture
def orders(db_session: Session) -> None:
    db_session.add_all(
        [
            UserModel(id="alice", email="alice@example.com", name="Alice"),
            UserModel(id="bob", email="bob@example.com", name="Bob"),
            _order("o1", "alice"),
            _order("o2", "alice"),
            _order("o3", "bob", status="cancelled"),
        ]
    )
    db_session.commit()


def test_invoice_numbers_are_sequential_and_stable(db_session: Session, orders: None) -> None:
    alice = _user("alice")
    first = download_invoice("o1", db_session, alice, SETTINGS)
    second = download_invoice("o2", db_session, alice, SETTINGS)
    again = download_invoice("o1", db_session, alice, SETTINGS)

    year = datetime.now(UTC).year
    assert first.media_type == "application/pdf"
    assert first.body.startswith(b"%PDF")
    assert f'filename="facture-FAC-{year}-00001.pdf"' in first.headers["content-disposition"]
    assert f"FAC-{year}-00002" in second.headers["content-disposition"]
    # Re-télécharger ne consomme pas de nouveau numéro.
    assert f"FAC-{year}-00001" in again.headers["content-disposition"]
    assert db_session.get(OrderModel, "o1").invoice_number == f"FAC-{year}-00001"


def test_customers_only_get_their_own_invoices(db_session: Session, orders: None) -> None:
    with pytest.raises(OrderNotFoundError):
        download_invoice("o1", db_session, _user("bob"), SETTINGS)

    staff = download_invoice("o1", db_session, _user("admin", Role.ADMIN), SETTINGS)
    assert staff.body.startswith(b"%PDF")


def test_cancelled_orders_are_not_invoiced(db_session: Session, orders: None) -> None:
    with pytest.raises(OrderCancelledConflictError):
        download_invoice("o3", db_session, _user("bob"), SETTINGS)


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        (0, "zéro"),
        (21, "vingt-et-un"),
        (80, "quatre-vingts"),
        (200, "deux-cents"),
        (80_000, "quatre-vingt-mille"),
        (1_328_000, "un-million-trois-cent-vingt-huit-mille"),
    ],
)
def test_amount_in_words(amount: int, words: str) -> None:
    assert amount_in_words(amount) == words

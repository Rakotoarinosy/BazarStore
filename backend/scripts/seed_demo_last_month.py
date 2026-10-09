"""Données de démonstration du mois dernier, pour voir le radar « ce mois vs mois dernier ».

Insère 3 clients fictifs et 8 commandes datées du mois précédent (fuseau APP_TIMEZONE),
à partir des produits du catalogue. Tout est marqué pour être retiré proprement :
références « DEMO-… » et e-mails « @demo.bazarstore.mg ». Le stock n'est pas modifié.

    python -m scripts.seed_demo_last_month            # (ré)insère les données de démo
    python -m scripts.seed_demo_last_month --remove   # les supprime
"""

import argparse
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from src.infrastructure.config import get_settings
from src.infrastructure.persistence.database import SessionLocal
from src.infrastructure.persistence.models import (
    OrderItemModel,
    OrderModel,
    ProductModel,
    UserModel,
)

DEMO_PREFIX = "DEMO-"
DEMO_DOMAIN = "@demo.bazarstore.mg"

# Clients fictifs (sans mot de passe : aucune connexion possible), inscrits le mois dernier.
CUSTOMERS = [
    ("hanta", "Rasoa Hanta", 2),
    ("andry", "Andry Rakoto", 5),
    ("mialy", "Mialy Randria", 8),
]

# (jour du mois, client, [(code produit, quantité)], statut final, payée ?)
ORDERS = [
    (3, "hanta", [("BAZ-MODE-001", 2)], "completed", True),
    (6, "andry", [("BAZ-SPORT-001", 1)], "completed", True),
    (9, "mialy", [("BAZ-ACC-001", 1), ("BAZ-ACC-002", 1)], "completed", True),
    (14, "hanta", [("BAZ-MODE-002", 1)], "completed", True),
    (18, "andry", [("BAZ-TECH-002", 1)], "shipped", True),
    (22, "mialy", [("BAZ-SPORT-002", 1)], "completed", True),
    (25, "hanta", [("BAZ-MODE-001", 1), ("BAZ-SPORT-001", 2)], "completed", True),
    (28, "andry", [("BAZ-TECH-001", 1)], "cancelled", False),
]


def last_month(timezone: ZoneInfo) -> date:
    first_of_this_month = datetime.now(timezone).date().replace(day=1)
    return (first_of_this_month - timedelta(days=1)).replace(day=1)


def at(month: date, day: int, hour: int, timezone: ZoneInfo) -> datetime:
    return datetime.combine(month.replace(day=day), time(hour, 30), tzinfo=timezone).astimezone(UTC)


def remove(db) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    order_ids = db.scalars(
        select(OrderModel.id).where(OrderModel.reference.like(f"{DEMO_PREFIX}%"))
    ).all()
    db.execute(delete(OrderItemModel).where(OrderItemModel.order_id.in_(order_ids)))
    orders = db.execute(delete(OrderModel).where(OrderModel.id.in_(order_ids))).rowcount
    users = db.execute(delete(UserModel).where(UserModel.email.like(f"%{DEMO_DOMAIN}"))).rowcount
    return orders, users


def seed(db, timezone: ZoneInfo) -> list[OrderModel]:  # type: ignore[no-untyped-def]
    month = last_month(timezone)
    products = {product.code: product for product in db.scalars(select(ProductModel))}
    missing = sorted({code for *_, items, _, _ in ORDERS for code, _ in items} - products.keys())
    if missing:
        raise SystemExit(
            f"Produits introuvables : {', '.join(missing)}. Lancez d'abord scripts.seed_demo_catalog."
        )

    customers = {
        key: UserModel(
            email=f"{key}{DEMO_DOMAIN}",
            name=name,
            role="customer",
            created_at=at(month, day, 9, timezone),
        )
        for key, name, day in CUSTOMERS
    }
    db.add_all(customers.values())
    db.flush()

    orders = []
    for index, (day, customer_key, lines, status, paid) in enumerate(ORDERS, start=1):
        customer = customers[customer_key]
        created = at(month, day, 10, timezone)
        items = [
            OrderItemModel(
                product_id=products[code].id,
                product_name=products[code].name,
                unit_price=products[code].price,
                quantity=quantity,
                line_total=products[code].price * quantity,
            )
            for code, quantity in lines
        ]
        orders.append(
            OrderModel(
                reference=f"{DEMO_PREFIX}{month:%Y%m}-{index:02d}",
                user_id=customer.id,
                customer_name=customer.name,
                customer_email=customer.email,
                status=status,
                total_amount=sum(item.line_total for item in items),
                payment_provider="stripe" if paid else None,
                payment_status="completed" if paid else None,
                paid_at=created + timedelta(minutes=12) if paid else None,
                created_at=created,
                # Dernière modification quelques jours après : l'activité récente reste dominée
                # par les vraies commandes de ce mois-ci.
                updated_at=created + timedelta(days=2),
                items=items,
            )
        )
    db.add_all(orders)
    return orders


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--remove", action="store_true", help="supprime les données de démonstration"
    )
    args = parser.parse_args()
    timezone = ZoneInfo(get_settings().app_timezone)

    with SessionLocal() as db:
        removed_orders, removed_users = remove(db)
        if args.remove:
            db.commit()
            print(
                f"Supprimé : {removed_orders} commande(s) et {removed_users} client(s) de démonstration."
            )
            return
        orders = seed(db, timezone)
        db.commit()

    paid = [
        order
        for order in orders
        if order.payment_status == "completed" and order.status != "cancelled"
    ]
    print(f"Mois de démonstration : {last_month(timezone):%m/%Y}")
    print(
        f"  {len(CUSTOMERS)} clients fictifs, {len(orders)} commandes ({len(paid)} payées, 1 annulée)"
    )
    print(
        f"  Chiffre d'affaires encaissé : {sum(order.total_amount for order in paid):,} Ar".replace(
            ",", " "
        )
    )
    print("Retirer ces données : python -m scripts.seed_demo_last_month --remove")


if __name__ == "__main__":
    main()

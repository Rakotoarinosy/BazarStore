"""Synchronisation du catalogue Odoo → BazarStore (cahier des charges IN-01 à IN-08, FI-04/07/08)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.features.product.router import list_active_products
from src.infrastructure.external.odoo_client import OdooUnavailableError
from src.infrastructure.integration.odoo_catalog_sync import (
    KIND_CATALOG,
    KIND_PRODUCT,
    OdooSyncAlreadyRunningConflictError,
    start_run,
    sync_catalog,
)
from src.infrastructure.persistence.models import (
    IntegrationSyncRunModel,
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)
from tests.fakes_odoo import FakeOdooCatalog, odoo_product

_runs = 0


def run_sync(
    db: Session, odoo: FakeOdooCatalog, *, only_ids: list[int] | None = None
) -> IntegrationSyncRunModel:
    global _runs
    _runs += 1
    run = start_run(
        db,
        kind=KIND_PRODUCT if only_ids else KIND_CATALOG,
        trigger="cli",
        correlation_id=f"corr-{_runs}",
    )
    return sync_catalog(db, odoo, run, only_ids=only_ids)


def product_by_odoo_id(db: Session, odoo_id: int) -> ProductModel:
    product = db.scalar(select(ProductModel).where(ProductModel.odoo_product_id == odoo_id))
    assert product is not None
    return product


def product_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(ProductModel)) or 0


def test_new_odoo_product_appears_with_price_stock_and_category(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(42, "BAZ-TECH-001", "Casque audio", price=700_000, free_qty=7)]
    )

    run = run_sync(db_session, odoo)

    product = product_by_odoo_id(db_session, 42)
    assert (run.status, run.created_count) == ("succeeded", 1)
    assert (product.code, product.name, product.price, product.quantity) == (
        "BAZ-TECH-001",
        "Casque audio",
        700_000,
        7,
    )
    assert product.is_active and product.odoo_synced_at is not None
    assert product.category.name == "High-tech"
    assert product.category.odoo_category_id == 5
    assert [p.code for p in list_active_products(db_session)] == ["BAZ-TECH-001"]


def test_replaying_the_sync_never_duplicates(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(1, "SKU-1", "Produit 1"), odoo_product(2, "SKU-2", "Produit 2")]
    )

    run_sync(db_session, odoo)
    replay = run_sync(db_session, odoo)

    assert product_count(db_session) == 2
    assert (replay.created_count, replay.updated_count, replay.unchanged_count) == (0, 0, 2)
    assert db_session.scalar(select(func.count()).select_from(ProductCategoryModel)) == 1


def test_existing_product_and_category_are_matched_not_duplicated(db_session: Session) -> None:
    category = ProductCategoryModel(id="cat-1", name="High tech", slug="high-tech")
    local = ProductModel(
        id="p-1",
        code="BAZ-TECH-001",
        name="Ancien nom",
        description="Texte marketing BazarStore",
        price=1,
        quantity=0,
        image_key="products/casque.jpg",
        category=category,
    )
    db_session.add_all([category, local])
    db_session.commit()

    run = run_sync(db_session, FakeOdooCatalog([odoo_product(42, "BAZ-TECH-001", "Casque audio")]))

    product = product_by_odoo_id(db_session, 42)
    assert run.updated_count == 1
    assert product.id == "p-1"  # même ligne, rapprochée par la référence
    assert product.name == "Casque audio"
    assert product.description == "Texte marketing BazarStore"  # description Odoo vide
    assert product.image_key == "products/casque.jpg"  # image gérée par BazarStore
    assert product.category_id == "cat-1"  # catégorie rapprochée par son slug
    assert product_count(db_session) == 1


def test_price_change_does_not_alter_existing_orders(db_session: Session) -> None:
    odoo = FakeOdooCatalog([odoo_product(42, "SKU-42", "Casque", price=700_000)])
    run_sync(db_session, odoo)
    product = product_by_odoo_id(db_session, 42)
    order = OrderModel(
        reference="CMD-PRIX",
        customer_name="Rakoto",
        customer_email="rakoto@example.com",
        total_amount=700_000,
        items=[
            OrderItemModel(
                product=product,
                product_name=product.name,
                unit_price=700_000,
                quantity=1,
                line_total=700_000,
            )
        ],
    )
    db_session.add(order)
    db_session.commit()

    odoo.records[0]["lst_price"] = 650_000.0
    run_sync(db_session, odoo)

    db_session.refresh(order)
    assert product_by_odoo_id(db_session, 42).price == 650_000
    assert order.items[0].unit_price == 700_000
    assert order.total_amount == 700_000


def test_archived_or_unsaleable_product_is_hidden(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(1, "SKU-1", "Produit 1"), odoo_product(2, "SKU-2", "Produit 2")]
    )
    run_sync(db_session, odoo)

    odoo.records[0]["active"] = False
    odoo.records[1]["sale_ok"] = False
    run = run_sync(db_session, odoo)

    assert run.updated_count == 2
    assert list_active_products(db_session) == []
    assert product_count(db_session) == 2  # conservés pour l'historique des commandes


def test_product_deleted_in_odoo_is_deactivated_after_a_full_pass(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(1, "SKU-1", "Produit 1"), odoo_product(2, "SKU-2", "Produit 2")]
    )
    run_sync(db_session, odoo)

    del odoo.records[1]
    run = run_sync(db_session, odoo)

    assert run.deactivated_count == 1
    assert not product_by_odoo_id(db_session, 2).is_active


def test_odoo_outage_mid_sync_keeps_the_catalog_and_logs_the_failure(db_session: Session) -> None:
    records = [odoo_product(i, f"SKU-{i}", f"Produit {i}") for i in range(1, 5)]
    run_sync(db_session, FakeOdooCatalog(records))

    records[0]["lst_price"] = 1.0
    failing = FakeOdooCatalog(records, page_size=2, fail_after_pages=1)
    with pytest.raises(OdooUnavailableError):
        run_sync(db_session, failing)

    run = db_session.scalars(
        select(IntegrationSyncRunModel).order_by(IntegrationSyncRunModel.started_at.desc())
    ).first()
    assert run is not None
    assert run.status == "failed"
    assert run.error_message and "injoignable" in run.error_message
    assert run.finished_at is not None and run.duration_ms is not None
    # Première page appliquée, et aucun produit désactivé faute d'avoir tout lu.
    assert product_by_odoo_id(db_session, 1).price == 1
    assert len(list_active_products(db_session)) == 4


def test_invalid_records_are_rejected_without_blocking_the_others(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [
            odoo_product(1, "SKU-1", "Produit 1"),
            odoo_product(2, "SKU-2", "Produit 2", default_code=False),
        ]
    )

    run = run_sync(db_session, odoo)

    assert run.status == "partial"
    assert (run.created_count, run.rejected_count) == (1, 1)
    assert run.rejections[0]["odoo_id"] == 2
    assert "default_code" in str(run.rejections[0]["reason"])


def test_same_sku_on_two_odoo_products_is_linked_only_once(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(1, "SKU-1", "Original"), odoo_product(2, "SKU-1", "Doublon")]
    )

    run = run_sync(db_session, odoo)

    assert product_count(db_session) == 1
    assert product_by_odoo_id(db_session, 1).name == "Original"
    assert run.rejections == [
        {"odoo_id": 2, "reason": "référence SKU-1 déjà utilisée par un autre produit"}
    ]


def test_published_stock_deducts_open_bazarstore_orders(db_session: Session) -> None:
    odoo = FakeOdooCatalog([odoo_product(42, "SKU-42", "Casque", free_qty=10)])
    run_sync(db_session, odoo)
    product = product_by_odoo_id(db_session, 42)

    def order(reference: str, status: str, quantity: int, deducted: bool) -> OrderModel:
        return OrderModel(
            reference=reference,
            customer_name="Rakoto",
            customer_email="rakoto@example.com",
            status=status,
            stock_deducted=deducted,
            total_amount=0,
            items=[
                OrderItemModel(
                    product=product,
                    product_name="Casque",
                    unit_price=0,
                    quantity=quantity,
                    line_total=0,
                )
            ],
        )

    db_session.add_all(
        [
            order("CMD-A", "confirmed", 3, True),  # réservée : déduite
            order("CMD-B", "pending", 2, False),  # pas encore confirmée : ignorée
            order("CMD-C", "cancelled", 4, False),  # annulée : ignorée
        ]
    )
    db_session.commit()

    run_sync(db_session, odoo)

    assert product_by_odoo_id(db_session, 42).quantity == 7


def test_single_product_resync(db_session: Session) -> None:
    odoo = FakeOdooCatalog(
        [odoo_product(1, "SKU-1", "Produit 1"), odoo_product(2, "SKU-2", "Produit 2")]
    )
    run_sync(db_session, odoo)
    odoo.records[0]["lst_price"] = 5_000.0
    odoo.records[1]["lst_price"] = 9_000.0

    run = run_sync(db_session, odoo, only_ids=[1])

    assert odoo.calls[-1]["only_ids"] == [1]
    assert (run.kind, run.updated_count) == (KIND_PRODUCT, 1)
    assert product_by_odoo_id(db_session, 1).price == 5_000
    assert product_by_odoo_id(db_session, 2).price == 100_000  # non concerné


def test_single_resync_of_an_unknown_product_is_reported(db_session: Session) -> None:
    run = run_sync(db_session, FakeOdooCatalog([]), only_ids=[999])

    assert run.status == "partial"
    assert run.rejections == [{"odoo_id": 999, "reason": "produit introuvable dans Odoo"}]


def test_archived_product_never_published_is_not_created(db_session: Session) -> None:
    run = run_sync(
        db_session,
        FakeOdooCatalog([odoo_product(3, "SKU-3", "Archivé", active=False)]),
        only_ids=[3],
    )

    assert product_count(db_session) == 0
    assert run.unchanged_count == 1


def test_only_one_sync_runs_at_a_time(db_session: Session) -> None:
    start_run(db_session, kind=KIND_CATALOG, trigger="api", correlation_id="first")

    with pytest.raises(OdooSyncAlreadyRunningConflictError):
        start_run(db_session, kind=KIND_CATALOG, trigger="api", correlation_id="second")


def test_a_stale_running_sync_no_longer_blocks(db_session: Session) -> None:
    stale = IntegrationSyncRunModel(
        correlation_id="crashed",
        kind=KIND_CATALOG,
        trigger="cli",
        status="running",
        started_at=datetime.now(UTC) - timedelta(hours=1),
        rejections=[],
    )
    db_session.add(stale)
    db_session.commit()

    start_run(db_session, kind=KIND_CATALOG, trigger="api", correlation_id="fresh")

    db_session.refresh(stale)
    assert stale.status == "failed"

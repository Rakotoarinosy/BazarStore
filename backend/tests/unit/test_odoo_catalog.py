"""Validation des produits reçus d'Odoo (FI-04) : rien n'est appliqué sans contrôle."""

import pytest

from src.domain.integration import (
    InvalidOdooRecordError,
    parse_odoo_product,
    published_quantity,
)


def odoo_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": 42,
        "default_code": "BAZ-TECH-001",
        "display_name": "[BAZ-TECH-001] Casque audio",
        "description_sale": "Casque circum-aural.",
        "lst_price": 700000.0,
        "free_qty": 7.0,
        "active": True,
        "sale_ok": True,
        "type": "consu",
        "categ_id": [5, "All / Saleable / High-tech"],
    }
    record.update(overrides)
    return record


def test_valid_record_is_mapped() -> None:
    product = parse_odoo_product(odoo_record())

    assert product.odoo_id == 42
    assert product.sku == "BAZ-TECH-001"
    assert product.name == "Casque audio"  # préfixe « [REF] » retiré
    assert product.price == 700_000
    assert product.free_qty == 7
    assert product.sellable is True
    assert (product.category.odoo_id, product.category.name) == (5, "High-tech")


def test_price_is_rounded_to_whole_ariary_and_stock_floored() -> None:
    product = parse_odoo_product(odoo_record(lst_price=1999.6, free_qty=2.9))

    assert product.price == 2000
    assert product.free_qty == 2


def test_negative_stock_is_published_as_zero() -> None:
    assert parse_odoo_product(odoo_record(free_qty=-3.0)).free_qty == 0


def test_empty_description_is_accepted() -> None:
    assert parse_odoo_product(odoo_record(description_sale=False)).description == ""


@pytest.mark.parametrize(
    ("overrides", "sellable"),
    [
        ({"active": False}, False),
        ({"sale_ok": False}, False),
        ({"type": "service"}, False),
        ({"type": "combo"}, False),
        ({}, True),
    ],
)
def test_only_active_saleable_goods_are_sellable(
    overrides: dict[str, object], sellable: bool
) -> None:
    assert parse_odoo_product(odoo_record(**overrides)).sellable is sellable


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"default_code": False}, "default_code"),
        ({"default_code": "X"}, "default_code"),
        ({"id": 0}, "id"),
        ({"id": True}, "id"),
        ({"display_name": ""}, "nom"),
        ({"lst_price": None}, "lst_price"),
        ({"lst_price": -1.0}, "prix négatif"),
        ({"lst_price": float("nan")}, "lst_price"),
        ({"free_qty": "7"}, "free_qty"),
        ({"active": None}, "active"),
        ({"categ_id": False}, "categ_id"),
        ({"categ_id": [5]}, "categ_id"),
    ],
)
def test_invalid_records_are_rejected_with_a_reason(
    overrides: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidOdooRecordError, match=reason):
        parse_odoo_product(odoo_record(**overrides))


@pytest.mark.parametrize(("free", "reserved", "expected"), [(10, 3, 7), (2, 5, 0), (4, 0, 4)])
def test_published_quantity_deducts_local_reservations(
    free: int, reserved: int, expected: int
) -> None:
    assert published_quantity(free, reserved) == expected

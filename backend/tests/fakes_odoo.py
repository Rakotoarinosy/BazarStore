"""Faux catalogue Odoo en mémoire (même contrat que OdooCatalogClient, sans réseau)."""

from collections.abc import Iterator, Mapping, Sequence

from src.domain.integration import OdooCatalogSource
from src.infrastructure.external.odoo_client import OdooUnavailableError


def odoo_product(
    odoo_id: int,
    sku: str,
    name: str,
    *,
    price: float = 100_000,
    free_qty: float = 10,
    active: bool = True,
    category: tuple[int, str] = (5, "All / Saleable / High-tech"),
    **overrides: object,
) -> dict[str, object]:
    record: dict[str, object] = {
        "id": odoo_id,
        "default_code": sku,
        "display_name": f"[{sku}] {name}",
        "description_sale": False,
        "lst_price": price,
        "free_qty": free_qty,
        "active": active,
        "sale_ok": True,
        "type": "consu",
        "categ_id": list(category),
    }
    record.update(overrides)
    return record


class FakeOdooCatalog(OdooCatalogSource):
    """`records` : état courant d'Odoo ; `fail_after_pages` simule une panne en cours de route."""

    def __init__(
        self,
        records: list[dict[str, object]],
        *,
        page_size: int = 100,
        fail_after_pages: int | None = None,
    ) -> None:
        self.records = records
        self.page_size = page_size
        self.fail_after_pages = fail_after_pages
        self.calls: list[dict[str, object]] = []

    def product_pages(
        self, *, linked_ids: Sequence[int], only_ids: Sequence[int] | None = None
    ) -> Iterator[list[Mapping[str, object]]]:
        self.calls.append({"linked_ids": list(linked_ids), "only_ids": only_ids})
        if only_ids is not None:
            rows = [r for r in self.records if r["id"] in only_ids]
        else:
            rows = [
                r
                for r in self.records
                if r["id"] in linked_ids or (r["active"] and r["sale_ok"] and r["type"] == "consu")
            ]
        for index in range(0, len(rows), self.page_size):
            if (
                self.fail_after_pages is not None
                and index // self.page_size >= self.fail_after_pages
            ):
                raise OdooUnavailableError("Odoo est injoignable ou trop lent (ConnectError).")
            yield rows[index : index + self.page_size]

"""Catalogue Odoo → BazarStore : produit Odoo validé, champs maîtres et source de données.

Odoo est la source de vérité du produit (référence, nom, prix TTC, statut, catégorie) et du
stock. Toute donnée reçue est validée ici avant d'être appliquée ; un enregistrement invalide
est rejeté avec un motif clair, sans bloquer le reste de la synchronisation.
"""

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from src.domain.errors import DomainError

# Champs d'un produit BazarStore lié qui ne se modifient que dans Odoo.
# La description et l'image restent gérées dans BazarStore (contenu marketing).
ODOO_MANAGED_PRODUCT_FIELDS = frozenset(
    {"code", "name", "price", "quantity", "is_active", "category_id"}
)

# Odoo affiche « [REF] Nom (variante) » : la référence est déjà portée par `code`.
_CODE_PREFIX = re.compile(r"^\[[^\]]*\]\s*")
MAX_SKU_LENGTH = 64
MAX_NAME_LENGTH = 180


class InvalidOdooRecordError(DomainError):
    """Enregistrement Odoo incomplet ou incohérent : rejeté, motif journalisé."""


@dataclass(frozen=True)
class OdooCategory:
    odoo_id: int
    name: str


@dataclass(frozen=True)
class OdooProduct:
    odoo_id: int
    sku: str
    name: str
    description: str
    price: int
    free_qty: int
    # Visible à l'achat : actif, vendable et de type bien (ni service ni combo).
    sellable: bool
    category: OdooCategory


class OdooCatalogSource(ABC):
    """Lecture paginée des produits Odoo (enregistrements bruts, validés ensuite)."""

    @abstractmethod
    def product_pages(
        self, *, linked_ids: Sequence[int], only_ids: Sequence[int] | None = None
    ) -> Iterator[list[Mapping[str, object]]]:
        """Produits vendables actifs + produits déjà liés (même archivés), ou `only_ids`."""


def _int(raw: Mapping[str, object], field: str) -> int:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidOdooRecordError(f"{field} invalide")
    return value


def _text(raw: Mapping[str, object], field: str) -> str:
    # Odoo renvoie `false` pour un champ texte vide.
    value = raw.get(field)
    if value is False or value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidOdooRecordError(f"{field} invalide")
    return value.strip()


def _number(raw: Mapping[str, object], field: str) -> float:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise InvalidOdooRecordError(f"{field} manquant ou invalide")
    return float(value)


def _bool(raw: Mapping[str, object], field: str) -> bool:
    value = raw.get(field)
    if not isinstance(value, bool):
        raise InvalidOdooRecordError(f"{field} invalide")
    return value


def _category(raw: Mapping[str, object]) -> OdooCategory:
    value = raw.get("categ_id")
    if (
        not isinstance(value, list | tuple)
        or len(value) != 2
        or isinstance(value[0], bool)
        or not isinstance(value[0], int)
        or not isinstance(value[1], str)
    ):
        raise InvalidOdooRecordError("categ_id invalide")
    # « All / Saleable / Audio » → « Audio »
    name = value[1].rsplit(" / ", 1)[-1].strip()
    if len(name) < 2:
        raise InvalidOdooRecordError("nom de catégorie invalide")
    return OdooCategory(odoo_id=value[0], name=name[:120])


def parse_odoo_product(raw: Mapping[str, object]) -> OdooProduct:
    """Valide un `product.product` lu par search_read (voir ODOO_PRODUCT_FIELDS)."""
    odoo_id = _int(raw, "id")
    sku = _text(raw, "default_code")
    if not 2 <= len(sku) <= MAX_SKU_LENGTH:
        raise InvalidOdooRecordError("référence interne (default_code) manquante ou invalide")
    name = _CODE_PREFIX.sub("", _text(raw, "display_name"))
    if not 2 <= len(name) <= MAX_NAME_LENGTH:
        raise InvalidOdooRecordError("nom du produit manquant ou trop long")
    price = _number(raw, "lst_price")
    if price < 0:
        raise InvalidOdooRecordError("prix négatif")

    return OdooProduct(
        odoo_id=odoo_id,
        sku=sku,
        name=name,
        description=_text(raw, "description_sale"),
        # Prix TTC en ariary (devise sans centimes) : taxe Odoo configurée « prix TTC ».
        price=round(price),
        free_qty=max(math.floor(_number(raw, "free_qty")), 0),
        sellable=_bool(raw, "active") and _bool(raw, "sale_ok") and raw.get("type") == "consu",
        category=_category(raw),
    )


def published_quantity(free_qty: int, reserved: int) -> int:
    """Stock affiché : stock libre Odoo moins les commandes BazarStore pas encore dans Odoo."""
    return max(free_qty - reserved, 0)

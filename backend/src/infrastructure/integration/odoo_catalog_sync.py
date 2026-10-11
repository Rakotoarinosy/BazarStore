"""Synchronisation du catalogue Odoo → BazarStore (idempotente : rejouable sans doublon).

Règles :
- Correspondance durable par `products.odoo_product_id` (unique). Un produit Odoo pas encore
  lié est rapproché d'un produit BazarStore existant par sa référence (`code` = default_code),
  sinon il est créé. Rejouer la synchronisation met à jour les mêmes lignes.
- Odoo est maître de la référence, du nom, du prix TTC, du statut et de la catégorie. La
  description Odoo n'écrase la description BazarStore que si elle est renseignée ; les images
  restent gérées dans BazarStore.
- Stock publié = stock libre Odoo - quantités des commandes BazarStore ouvertes déjà décomptées
  (pas encore transmises à Odoo).
- Les prix des commandes passées ne changent jamais : ils sont figés dans `order_items`.
- Un enregistrement invalide est rejeté avec son motif ; les autres sont appliqués.
- Les produits liés absents d'Odoo sont désactivés, mais seulement après un passage complet
  réussi : une panne d'Odoo en cours de route ne vide jamais le catalogue.
"""

import logging
import re
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.domain.errors import DomainError
from src.domain.integration import (
    InvalidOdooRecordError,
    OdooCatalogSource,
    OdooCategory,
    OdooProduct,
    parse_odoo_product,
    published_quantity,
)
from src.infrastructure.persistence.models import (
    IntegrationSyncRunModel,
    OrderItemModel,
    OrderModel,
    ProductCategoryModel,
    ProductModel,
)

logger = logging.getLogger(__name__)

KIND_CATALOG = "odoo_catalog"
KIND_PRODUCT = "odoo_product"
# Commandes dont le stock est déjà décompté dans BazarStore mais pas encore connu d'Odoo.
RESERVING_ORDER_STATUSES = ("confirmed", "processing", "shipped")
# Au-delà, une exécution « running » est considérée comme interrompue (crash, redémarrage).
RUN_LOCK_TIMEOUT = timedelta(minutes=15)
MAX_REJECTIONS_KEPT = 50


class OdooSyncAlreadyRunningConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__("Une synchronisation Odoo est déjà en cours. Réessayez dans un instant.")


@dataclass
class _Outcome:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    rejections: list[dict[str, object]] = field(default_factory=list)

    def reject(self, odoo_id: object, reason: str) -> None:
        self.rejections.append({"odoo_id": odoo_id, "reason": reason})


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:120].strip("-")


def start_run(
    db: Session, *, kind: str, trigger: str, correlation_id: str
) -> IntegrationSyncRunModel:
    """Ouvre une exécution journalisée ; refuse si une autre est en cours (une seule à la fois)."""
    now = datetime.now(UTC)
    stale_before = now - RUN_LOCK_TIMEOUT
    db.execute(
        update(IntegrationSyncRunModel)
        .where(
            IntegrationSyncRunModel.status == "running",
            IntegrationSyncRunModel.started_at < stale_before,
        )
        .values(status="failed", error_message="Exécution interrompue (délai dépassé).")
    )
    if db.scalar(
        select(IntegrationSyncRunModel.id).where(IntegrationSyncRunModel.status == "running")
    ):
        db.commit()
        raise OdooSyncAlreadyRunningConflictError()

    run = IntegrationSyncRunModel(
        correlation_id=correlation_id,
        kind=kind,
        trigger=trigger,
        status="running",
        started_at=now,
        rejections=[],
    )
    db.add(run)
    db.commit()
    return run


class _CatalogWriter:
    def __init__(self, db: Session, outcome: _Outcome) -> None:
        self._db = db
        self._outcome = outcome
        self._now = datetime.now(UTC)
        self.linked: dict[int, ProductModel] = {
            product.odoo_product_id: product
            for product in db.scalars(
                select(ProductModel).where(ProductModel.odoo_product_id.is_not(None))
            )
            if product.odoo_product_id is not None
        }
        self._categories: dict[int, ProductCategoryModel] = {}
        self._reserved: dict[str, int] = {
            product_id: int(quantity)
            for product_id, quantity in db.execute(
                select(OrderItemModel.product_id, func.sum(OrderItemModel.quantity))
                .join(OrderModel)
                .where(
                    OrderModel.stock_deducted.is_(True),
                    OrderModel.status.in_(RESERVING_ORDER_STATUSES),
                    OrderItemModel.product_id.is_not(None),
                )
                .group_by(OrderItemModel.product_id)
            )
            if product_id is not None
        }

    def apply(self, item: OdooProduct) -> None:
        product = self.linked.get(item.odoo_id)
        holder = self._db.scalar(select(ProductModel).where(ProductModel.code == item.sku))
        if holder is not None and holder is not product:
            if holder.odoo_product_id is not None or product is not None:
                # Odoo n'impose pas l'unicité de default_code : on ne lie jamais deux fois.
                self._outcome.reject(
                    item.odoo_id, f"référence {item.sku} déjà utilisée par un autre produit"
                )
                return
            product = holder  # rapprochement initial par référence (SKU)

        if product is None and not item.sellable:
            self._outcome.unchanged += 1  # produit archivé jamais publié : rien à créer
            return

        category = self._category(item.category)
        values: dict[str, object] = {
            "code": item.sku,
            "name": item.name,
            "price": item.price,
            "quantity": published_quantity(
                item.free_qty, self._reserved.get(product.id, 0) if product else 0
            ),
            "is_active": item.sellable,
            "category_id": category.id,
        }
        if item.description:
            values["description"] = item.description

        if product is None:
            product = ProductModel(**values, odoo_product_id=item.odoo_id, odoo_synced_at=self._now)
            self._db.add(product)
            self._db.flush()
            self.linked[item.odoo_id] = product
            self._outcome.created += 1
            return

        changed = product.odoo_product_id != item.odoo_id or any(
            getattr(product, name) != value for name, value in values.items()
        )
        if not changed:
            self._outcome.unchanged += 1
            return
        for name, value in values.items():
            setattr(product, name, value)
        product.odoo_product_id = item.odoo_id
        product.odoo_synced_at = self._now
        self.linked[item.odoo_id] = product
        self._db.flush()
        self._outcome.updated += 1

    def deactivate_missing(self, odoo_ids: Sequence[int]) -> None:
        """Produits liés supprimés (ou devenus introuvables) dans Odoo : retirés de la vente."""
        for odoo_id in odoo_ids:
            product = self.linked.get(odoo_id)
            if product is not None and product.is_active:
                product.is_active = False
                product.odoo_synced_at = self._now
                self._outcome.deactivated += 1

    def _category(self, source: OdooCategory) -> ProductCategoryModel:
        cached = self._categories.get(source.odoo_id)
        if cached is not None:
            return cached
        category = self._db.scalar(
            select(ProductCategoryModel).where(
                ProductCategoryModel.odoo_category_id == source.odoo_id
            )
        )
        slug = _slugify(source.name) or f"odoo-{source.odoo_id}"
        if category is None:
            # Rapprochement d'une catégorie BazarStore existante par son slug.
            category = self._db.scalar(
                select(ProductCategoryModel).where(
                    ProductCategoryModel.slug == slug,
                    ProductCategoryModel.odoo_category_id.is_(None),
                )
            )
        if category is None:
            if self._db.scalar(
                select(ProductCategoryModel.id).where(ProductCategoryModel.slug == slug)
            ):
                slug = f"{slug}-{source.odoo_id}"
            category = ProductCategoryModel(name=source.name, slug=slug)
            self._db.add(category)
        category.odoo_category_id = source.odoo_id
        if category.name != source.name:
            category.name = source.name
        self._db.flush()
        self._categories[source.odoo_id] = category
        return category


def sync_catalog(
    db: Session,
    source: OdooCatalogSource,
    run: IntegrationSyncRunModel,
    *,
    only_ids: Sequence[int] | None = None,
) -> IntegrationSyncRunModel:
    """Applique le catalogue Odoo (ou `only_ids`) et clôt l'exécution `run`.

    Une erreur d'Odoo (indisponibilité, clé refusée…) est journalisée sur l'exécution puis
    relancée ; les pages déjà appliquées restent valides (elles sont idempotentes).
    """
    started = time.monotonic()
    outcome = _Outcome()
    writer = _CatalogWriter(db, outcome)
    seen: set[int] = set()
    try:
        for page in source.product_pages(linked_ids=sorted(writer.linked), only_ids=only_ids):
            for raw in page:
                try:
                    item = parse_odoo_product(raw)
                except InvalidOdooRecordError as exc:
                    outcome.reject(raw.get("id"), exc.message)
                    continue
                seen.add(item.odoo_id)
                writer.apply(item)
            db.commit()  # une page appliquée est acquise, même si la suivante échoue

        expected = set(only_ids) if only_ids is not None else set(writer.linked)
        missing = sorted(expected - seen)
        writer.deactivate_missing(missing)
        if only_ids is not None:
            for odoo_id in missing:
                if odoo_id not in writer.linked:
                    outcome.reject(odoo_id, "produit introuvable dans Odoo")
        db.commit()
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.error_message = exc.message if isinstance(exc, DomainError) else type(exc).__name__
        if not isinstance(exc, DomainError):
            logger.exception("Odoo catalog sync crashed [correlation_id=%s]", run.correlation_id)
        _finish(db, run, outcome, started)
        raise

    run.status = "partial" if outcome.rejections else "succeeded"
    _finish(db, run, outcome, started)
    logger.info(
        "Odoo catalog sync %s: %d created, %d updated, %d unchanged, %d deactivated, "
        "%d rejected [correlation_id=%s]",
        run.status,
        outcome.created,
        outcome.updated,
        outcome.unchanged,
        outcome.deactivated,
        len(outcome.rejections),
        run.correlation_id,
    )
    return run


def _finish(db: Session, run: IntegrationSyncRunModel, outcome: _Outcome, started: float) -> None:
    run.finished_at = datetime.now(UTC)
    run.duration_ms = round((time.monotonic() - started) * 1000)
    run.created_count = outcome.created
    run.updated_count = outcome.updated
    run.unchanged_count = outcome.unchanged
    run.deactivated_count = outcome.deactivated
    run.rejected_count = len(outcome.rejections)
    run.rejections = outcome.rejections[:MAX_REJECTIONS_KEPT]
    db.add(run)
    db.commit()

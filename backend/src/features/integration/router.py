"""Intégration Odoo : resynchronisation du catalogue et journal des échanges (administrateurs).

BazarStore lit Odoo (pull) : aucun point d'entrée public n'est exposé à Odoo, et une panne
d'Odoo n'affecte pas le catalogue déjà publié.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import partial
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.integration import OdooCatalogSource
from src.domain.user import Role
from src.features.integration.schemas import SyncRunOut
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.external.odoo_client import OdooSyncUnavailableError, open_odoo_catalog
from src.infrastructure.integration.odoo_catalog_sync import (
    KIND_CATALOG,
    KIND_PRODUCT,
    start_run,
    sync_catalog,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import IntegrationSyncRunModel
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/integration/odoo", tags=["integration"])

CatalogOpener = Callable[[str], AbstractContextManager[OdooCatalogSource]]


def require_odoo_sync_enabled(settings: Settings = Depends(get_settings)) -> None:
    """Coupe les routes de synchronisation (aucun appel à Odoo) si l'intégration est désactivée."""
    if not settings.odoo_sync_enabled:
        raise OdooSyncUnavailableError()


def get_catalog_opener(settings: Settings = Depends(get_settings)) -> CatalogOpener:
    return partial(open_odoo_catalog, settings)


ADMIN_ONLY = [Depends(require_roles(Role.ADMIN))]
# Rôle vérifié avant l'interrupteur : un anonyme reçoit 401, pas 503.
SYNC_GUARD = [*ADMIN_ONLY, Depends(require_odoo_sync_enabled)]


def _run_sync(
    db: Session, open_catalog: CatalogOpener, *, kind: str, only_ids: list[int] | None = None
) -> SyncRunOut:
    correlation_id = str(uuid4())
    with open_catalog(correlation_id) as source:
        run = start_run(db, kind=kind, trigger="api", correlation_id=correlation_id)
        sync_catalog(db, source, run, only_ids=only_ids)
    return SyncRunOut.model_validate(run)


@router.post("/catalog/sync", response_model=SyncRunOut, dependencies=SYNC_GUARD)
def sync_odoo_catalog(
    db: Session = Depends(get_db), open_catalog: CatalogOpener = Depends(get_catalog_opener)
) -> SyncRunOut:
    """Resynchronisation complète du catalogue (synchronisation initiale comprise)."""
    return _run_sync(db, open_catalog, kind=KIND_CATALOG)


@router.post("/products/{odoo_product_id}/sync", response_model=SyncRunOut, dependencies=SYNC_GUARD)
def sync_odoo_product(
    odoo_product_id: int = Path(gt=0, description="Identifiant product.product dans Odoo"),
    db: Session = Depends(get_db),
    open_catalog: CatalogOpener = Depends(get_catalog_opener),
) -> SyncRunOut:
    """Resynchronisation d'un produit précis (désactivé s'il n'existe plus dans Odoo)."""
    return _run_sync(db, open_catalog, kind=KIND_PRODUCT, only_ids=[odoo_product_id])


@router.get("/runs", response_model=list[SyncRunOut], dependencies=ADMIN_ONLY)
def list_sync_runs(
    limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)
) -> list[SyncRunOut]:
    """Journal des synchronisations, les plus récentes d'abord."""
    runs = db.scalars(
        select(IntegrationSyncRunModel)
        .order_by(IntegrationSyncRunModel.started_at.desc())
        .limit(limit)
    )
    return [SyncRunOut.model_validate(run) for run in runs]

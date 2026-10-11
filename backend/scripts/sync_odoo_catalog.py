"""Synchronise le catalogue Odoo → BazarStore (à planifier, par exemple toutes les 5 minutes).

    uv run python -m scripts.sync_odoo_catalog              # catalogue complet
    uv run python -m scripts.sync_odoo_catalog --product 42 # un produit Odoo précis

Code de sortie : 0 succès, 1 succès partiel (produits rejetés), 2 échec ou intégration coupée.
"""

import argparse
import sys
from uuid import uuid4

from src.domain.errors import DomainError
from src.infrastructure.config import configure_logging, get_settings
from src.infrastructure.external.odoo_client import open_odoo_catalog
from src.infrastructure.integration.odoo_catalog_sync import (
    KIND_CATALOG,
    KIND_PRODUCT,
    start_run,
    sync_catalog,
)
from src.infrastructure.persistence.database import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", type=int, help="identifiant product.product Odoo")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    if not settings.odoo_sync_enabled:
        print("Intégration Odoo désactivée (ODOO_SYNC_ENABLED=false).", file=sys.stderr)
        return 2

    correlation_id = str(uuid4())
    only_ids = [args.product] if args.product else None
    try:
        with open_odoo_catalog(settings, correlation_id) as source, SessionLocal() as db:
            run = start_run(
                db,
                kind=KIND_PRODUCT if only_ids else KIND_CATALOG,
                trigger="cli",
                correlation_id=correlation_id,
            )
            sync_catalog(db, source, run, only_ids=only_ids)
    except DomainError as exc:
        print(f"Échec [{correlation_id}] : {exc.message}", file=sys.stderr)
        return 2

    print(
        f"{run.status} [{correlation_id}] : {run.created_count} créé(s), "
        f"{run.updated_count} mis à jour, {run.unchanged_count} inchangé(s), "
        f"{run.deactivated_count} désactivé(s), {run.rejected_count} rejeté(s)"
    )
    for rejection in run.rejections:
        print(f"  rejet produit Odoo {rejection['odoo_id']} : {rejection['reason']}")
    return 1 if run.rejected_count else 0


if __name__ == "__main__":
    sys.exit(main())

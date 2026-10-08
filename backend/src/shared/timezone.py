"""Fuseau horaire métier (découpage des « jours » du dashboard)."""

import logging
from datetime import UTC, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def resolve_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Sous Windows, installer le paquet `tzdata` pour disposer de la base des fuseaux.
        logger.warning("unknown timezone, falling back to UTC", extra={"timezone": name})
        return UTC

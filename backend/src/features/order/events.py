"""Flux Server-Sent Events des commandes (logique de diffusion, sans accès direct à la base).

- Backoffice : `order` (commande créée ou modifiée) + `open-count` (badge du menu).
- Client : `order` pour ses propres commandes uniquement.

La lecture en base est fournie par router.py (`poll`) ; ce module décide QUAND relire :
dès que la version des commandes change dans ce processus (`version`), et au plus tard toutes
les DB_RECHECK_SECONDS pour les changements faits par un autre processus du serveur.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

TICK_SECONDS = 0.5  # réactivité aux changements faits dans ce processus
DB_RECHECK_SECONDS = 5.0  # changements faits par un autre processus
HEARTBEAT_SECONDS = 15.0  # garde la connexion ouverte à travers les proxys
# Le navigateur se reconnecte ensuite (avec un jeton d'accès frais) ; borne aussi
# l'attente d'uvicorn --reload sur les flux ouverts.
STREAM_MAX_SECONDS = 120.0

# poll(first) -> (commandes modifiées sérialisées, nombre de commandes ouvertes ou None)
OrderPoll = Callable[[bool], tuple[list[dict[str, object]], int | None]]


def _sse(event_name: str, data: object) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


async def order_events(
    is_disconnected: Callable[[], Awaitable[bool]],
    poll: OrderPoll,
    version: Callable[[], int],
    *,
    max_seconds: float = STREAM_MAX_SECONDS,
) -> AsyncIterator[str]:
    """Flux SSE : `order` à chaque commande créée/modifiée, `open-count` quand le nombre change."""
    yield "retry: 3000\n\n"  # délai de reconnexion conseillé au client
    started = last_db_check = last_sent = time.monotonic()
    last_version = -1
    last_count: int | None = None
    first = True

    while time.monotonic() - started < max_seconds:
        if await is_disconnected():
            return
        now = time.monotonic()
        current_version = version()
        if first or current_version != last_version or now - last_db_check >= DB_RECHECK_SECONDS:
            last_version, last_db_check = current_version, now
            # Requête bloquante (SQLAlchemy) : exécutée hors de la boucle asyncio.
            changed, count = await asyncio.to_thread(poll, first)
            first = False
            for order in changed:
                last_sent = now
                yield _sse("order", order)
            if count is not None and count != last_count:
                last_count, last_sent = count, now
                yield _sse("open-count", {"count": count})
        if now - last_sent >= HEARTBEAT_SECONDS:
            last_sent = now
            yield ": ping\n\n"
        await asyncio.sleep(TICK_SECONDS)

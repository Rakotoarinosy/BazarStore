"""Timeline d'une demande (historique complet). Le contrôle d'accès est fait par le router."""

from src.domain.agent import AgentRepository
from src.domain.demande.events import DemandeEvent, DemandeEventRepository, EventType


def list_demande_events(
    demande_id: str, events: DemandeEventRepository, agents: AgentRepository
) -> list[DemandeEvent]:
    items = events.list_for_demande(demande_id)

    # Le nom de l'agent est résolu à la lecture (un seul appel par agent distinct).
    names: dict[str, str | None] = {}
    for event in items:
        agent_id = event.payload.get("agent_id")
        if event.type is EventType.ASSIGNED and agent_id:
            if agent_id not in names:
                agent = agents.get_by_id(agent_id)
                names[agent_id] = agent.name if agent else None
            event.payload = {**event.payload, "agent_name": names[agent_id]}

    return items

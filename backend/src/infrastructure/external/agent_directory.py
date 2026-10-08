"""Annuaire d'agents provisoire.

Les agents sont développés par quelqu'un d'autre : tant que leur table n'existe pas, on accepte
n'importe quel identifiant pour que l'attribution fonctionne. Quand elle sera prête, remplacer
cette classe par une implémentation qui interroge la vraie table (même interface AgentDirectory).
"""

from src.domain.demande import AgentDirectory


class PermissiveAgentDirectory(AgentDirectory):
    def exists(self, agent_id: str) -> bool:
        return True

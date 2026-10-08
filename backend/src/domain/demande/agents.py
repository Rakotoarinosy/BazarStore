"""Port vers les agents (domaine géré par un autre développeur).

Les demandes n'ont besoin que de savoir si un agent peut recevoir une demande (il existe et
est actif). L'implémentation SQL est dans infrastructure/persistence/agent_directory.py.
"""

from abc import ABC, abstractmethod


class AgentDirectory(ABC):
    @abstractmethod
    def exists(self, agent_id: str) -> bool: ...

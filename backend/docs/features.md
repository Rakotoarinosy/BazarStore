# Domaines

À tenir à jour pendant le hackathon : une ligne par domaine, mise à jour à chaque merge.

Statuts : 🟢 terminé · 🟡 en cours · ⚪ à faire · ⛔ abandonné

| Domaine | Statut | Endpoints (`/api/v1`) | Porteur | Notes |
|---|---|---|---|---|
| `health` | 🟢 | `GET /health` | — | Défini dans `main.py`, pas un domaine |
| `user` | 🟢 | `POST /users` · `GET /users` · `GET /users/{id}` · `PUT /users/{id}` · `DELETE /users/{id}` | — | Domaine modèle à copier |
| `agent` | 🟢 | `POST /agents` · `GET /agents` · `GET /agents/{id}` · `PATCH /agents/{id}` · `POST /agents/{id}/deactivate` · `POST /agents/{id}/activate` · `GET /agents/{id}/interventions` | — | Jamais supprimé, seulement désactivé. Interventions = demandes citoyennes attribuées (`citizen_requests.assigned_agent_id` → `agents.id`) ; un agent désactivé ne peut plus être attribué (`AgentInactiveError`, 400). `use_cases/` en package : un fichier par action |
| | | | | |

## Modèle vierge

Copier ce bloc pour chaque nouvelle demande reçue pendant le hackathon.

```markdown
### <domaine> — reçu à <heure>

- Demande : <résumé de la fonctionnalité demandée>
- Priorité : obligatoire | bonus | ignorée (raison)
- Règles métier :
  - …
- Endpoints :
  - `POST /<domaines>` — …
- Exceptions métier : `<Domaine>NotFoundError` (404), …
- Fichiers hors patron (> 7) : aucun | <fichier> — <justification>
```

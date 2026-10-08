# BazarStore — Backend

API REST BazarStore consommée par le frontend Angular (`../frontend`), construite avec FastAPI,
SQLAlchemy 2 et Alembic.

L'API expose actuellement l'authentification et l'administration des comptes. Les anciens
endpoints agents, demandes citoyennes et analytics ne sont plus montés. Leurs anciennes
migrations ont été retirées; Alembic gère désormais le schéma BazarStore des comptes et sessions.

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommandé), sinon pip : le Makefile choisit tout seul
- `make`
- Docker (optionnel)

## Installation et lancement

Depuis `backend/` :

```bash
make install    # dépendances + .env créé depuis .env.example
make migrate    # crée ./app.db (SQLite), users et refresh_tokens
make dev        # http://localhost:8000
```

| URL | Contenu |
|---|---|
| <http://localhost:8000/api/v1/health> | `{"status": "ok"}` |
| <http://localhost:8000/docs> | Scalar |
| <http://localhost:8000/redoc> | ReDoc |

La documentation interactive est masquée quand `ENVIRONMENT=production`.

Avec Docker : `make docker-up` (hot reload, même `./app.db`). Pour PostgreSQL, décommenter le
service `db` dans `docker-compose.yml`.

## Configuration

Toutes les variables sont dans [.env.example](.env.example) :

| Variable | Défaut | Rôle |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` : logs JSON, documentation masquée |
| `DATABASE_URL` | `sqlite:///./app.db` | PostgreSQL : `postgresql+psycopg://user:pass@host:5432/db` |
| `CORS_ORIGINS` | `http://localhost:4200` | Origines autorisées, séparées par des virgules. Angular utilise un proxy local pour `/api/v1`. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SECRET_KEY` | `change-me-in-production` | À remplacer en production |

## Authentification

Les routes d'authentification sont consommées par le frontend via `/api/v1/auth`. Le backend
fournit l'inscription, la connexion, le profil, le renouvellement par cookie HttpOnly et la
déconnexion. La connexion Google et la récupération du mot de passe nécessitent encore leur
configuration/fournisseur. Pour Google, définir le même identifiant client OAuth Web dans
`GOOGLE_CLIENT_ID` côté backend et `googleClientId` dans `frontend/public/runtime-config.json`,
puis autoriser l'origine du frontend dans Google Cloud. Aucun secret Google n'est envoyé au frontend.

Les inscriptions par mot de passe et Google créent toujours un compte `customer`. Le rôle n'est
jamais accepté depuis une inscription publique. Seul un `admin` peut créer ou promouvoir un compte
via `/api/v1/users` : `commercial` gère le backoffice, tandis que `admin` conserve tous les droits.
Les anciens comptes `manager` gardent leurs accès backoffice.

## Exemples d'appels d'authentification

```bash
# Créer un compte client
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","name":"Ada Lovelace","password":"BazarStore2026!"}'

# Se connecter : le refresh token est posé dans un cookie HttpOnly.
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"BazarStore2026!"}'
```

Le frontend utilise le proxy Angular local pour appeler ces routes sur `/api/v1/auth`.

## Administration des comptes

```bash
# Créer
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@example.com", "name": "Ada"}'
# → 201 {"id": "0272…", "email": "ada@example.com", "name": "Ada", "created_at": "…Z"}

# Lister / détail
curl http://localhost:8000/api/v1/users
curl http://localhost:8000/api/v1/users/<id>

# Modifier (partiel)
curl -X PUT http://localhost:8000/api/v1/users/<id> \
  -H "Content-Type: application/json" \
  -d '{"name": "Ada Lovelace"}'

# Supprimer
curl -X DELETE http://localhost:8000/api/v1/users/<id>   # → 204
```

Format des erreurs métier :

```json
{ "error": "UserAlreadyExistsError", "detail": "A user with email 'ada@example.com' already exists" }
```

`*NotFoundError` → 404, `*AlreadyExistsError` → 409, autres erreurs métier → 400,
validation → 422.

## Commandes

```bash
make help                          # liste toutes les commandes
make test                          # tests unitaires, intégration, e2e et architecture
make lint                          # ruff + black --check + mypy strict
make format                        # ruff --fix + black
make revision m="add products"     # nouvelle migration (autogenerate)
make migrate                       # applique les migrations
make requirements                  # régénère requirements.txt (déploiement Passenger)
make clean                         # caches + app.db
```

## Déploiement (Passenger)

`passenger_wsgi.py` expose l'app ASGI en WSGI grâce à `a2wsgi`. Sur le serveur :
`pip install -r requirements.txt`, créer le `.env` (avec `ENVIRONMENT=production` et une vraie
`SECRET_KEY`), puis `alembic upgrade head`. Après toute modification des dépendances, lancer
`make requirements`.

## Documentation

- [docs/architecture.md](docs/architecture.md) : les couches, le flux d'une requête, les règles
  de dépendance et l'ajout d'un domaine en 5 étapes
- [docs/conventions.md](docs/conventions.md) : le nommage, des exemples de code et la checklist
  avant merge
- [docs/features.md](docs/features.md) : le suivi des domaines pendant le hackathon

## Structure

```text
backend/
├── src/
│   ├── domain/           # cœur métier, Python pur
│   ├── features/         # use cases, schémas, routers
│   ├── infrastructure/   # base de données, config, logs
│   ├── shared/           # handlers d'erreurs
│   └── main.py
├── tests/                # unit/ · integration/ · e2e/
├── alembic/              # migrations
├── docs/
├── Dockerfile · docker-compose.yml · Makefile
└── pyproject.toml
```

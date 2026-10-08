# Architecture — Clean Architecture Lite

Objectif : pendant 24 h, on ajoute des fonctionnalités toutes les 1 à 3 heures. Chaque domaine
doit pouvoir être ajouté **sans toucher aux autres**, en copiant le domaine `user`.

## Les 3 couches

```
┌──────────────────────────────────────────────────────────────┐
│ infrastructure/   SQLAlchemy, config, logs, clients externes │
│   implémente les interfaces du domaine                       │
└──────────────┬───────────────────────────────────────────────┘
               │ dépend de
┌──────────────▼───────────────────────────────────────────────┐
│ features/         use cases + schémas Pydantic + router HTTP │
└──────────────┬───────────────────────────────────────────────┘
               │ dépend de
┌──────────────▼───────────────────────────────────────────────┐
│ domain/           entités, exceptions, interfaces (ABC)      │
│   Python pur : aucun framework                               │
└──────────────────────────────────────────────────────────────┘
```

Les dépendances pointent **toujours vers le domaine**. Le domaine ne connaît ni FastAPI, ni
SQLAlchemy, ni Pydantic.

## Flux d'une requête

```
POST /api/v1/users
   │
   ▼
features/user/router.py         valide le JSON (CreateUserIn), résout les Depends()
   │  get_user_repo() → SqlAlchemyUserRepository(db)
   ▼
features/user/use_cases.py      create_user(dto, repo) : règles métier (email unique…)
   │  appelle l'interface
   ▼
domain/user/repository.py       UserRepository (ABC)
   │  implémentée par
   ▼
infrastructure/persistence/user_repository.py   mapping Entity ↔ Model, requêtes SQL
   │
   ▼
SQLite (dev) / PostgreSQL (prod)
   │
   ▼  User (entité) remonte jusqu'au router → sérialisé en UserOut → JSON 201
```

En cas d'erreur métier, le use case lève une exception du domaine (`UserAlreadyExistsError`),
que `shared/errors/handlers.py` convertit en réponse HTTP (ici 409).

## Arborescence

```
src/
├── domain/
│   ├── errors.py                 # DomainError, base de toutes les erreurs métier
│   └── user/
│       ├── entities.py           # @dataclass User
│       ├── exceptions.py         # UserNotFoundError, UserAlreadyExistsError
│       └── repository.py         # UserRepository (ABC)
├── features/
│   └── user/
│       ├── schemas.py            # CreateUserIn, UpdateUserIn, UserOut
│       ├── use_cases.py          # create_user, get_user, list_users, update_user, delete_user
│       └── router.py             # endpoints + get_user_repo() local
├── infrastructure/
│   ├── config/                   # settings.py (pydantic-settings), logging.py
│   ├── persistence/
│   │   ├── database.py           # engine, SessionLocal, Base, get_db
│   │   ├── models.py             # modèles SQLAlchemy de TOUS les domaines
│   │   └── user_repository.py    # SqlAlchemyUserRepository
│   └── external/                 # clients externes (email, paiement…)
├── shared/errors/handlers.py     # exceptions métier → codes HTTP
└── main.py                       # création de l'app, CORS, montage des routers
```

## Règles de dépendance

| Couche | Peut importer | Ne doit JAMAIS importer |
|---|---|---|
| `domain/` | stdlib, `typing`, `abc`, `src.domain` | fastapi, sqlalchemy, pydantic, `features`, `infrastructure`, `shared` |
| `features/*/use_cases.py`, `schemas.py` | `domain`, pydantic, stdlib | sqlalchemy, `infrastructure` |
| `features/*/router.py` | tout ce qui précède + fastapi + `infrastructure` (pour les `Depends()`) | — |
| `infrastructure/` | `domain`, sqlalchemy, libs externes | `features` |
| `shared/` | stdlib, fastapi, `domain.errors` | `features`, `infrastructure` |

**Règle d'or :** le `router.py` d'une feature est le **seul** endroit où `features/` rencontre
`infrastructure/`. Un repository concret n'est instancié que dans un `Depends()` de router.

Ces règles sont **vérifiées automatiquement** par `tests/unit/test_architecture.py` : un import
interdit fait échouer `make test`, pour tous les domaines, y compris les futurs.

## Ajouter un nouveau domaine en 5 étapes

Exemple : `product`.

1. **Domaine** : copier `src/domain/user/` → `src/domain/product/`. Renommer l'entité, les
   exceptions (`ProductNotFoundError`…) et l'interface `ProductRepository`.
2. **Feature** : copier `src/features/user/` → `src/features/product/`. Adapter les schémas, les
   use cases, et le router (`prefix="/products"`, `get_product_repo`).
3. **Repository** : copier `src/infrastructure/persistence/user_repository.py` →
   `product_repository.py` (`SqlAlchemyProductRepository`, mapping `_to_entity` / `_to_model`).
4. **Modèle** : ajouter `ProductModel` dans `src/infrastructure/persistence/models.py`, puis
   `make revision m="create products table"` et `make migrate`.
5. **Montage** : dans `src/main.py`, importer le router et l'ajouter à `FEATURE_ROUTERS`.

Rien d'autre à modifier : les erreurs `*NotFoundError` / `*AlreadyExistsError` sont traduites en
404 / 409 automatiquement, et le test d'architecture couvre le nouveau dossier.

## Ce qu'on garde / ce qu'on simplifie

| On garde (l'essentiel de la Clean Architecture) | Pourquoi |
|---|---|
| Domaine pur (dataclasses, ABC) | Logique métier testable sans DB ni HTTP, indépendante des libs |
| Repository pattern (interface + implémentation) | Changer de base (SQLite → PostgreSQL) ne touche que l'infrastructure |
| Use cases isolés, repository injecté | Tests unitaires avec un repo en mémoire (`tests/fakes.py`) |
| Exceptions métier + handlers globaux | Les endpoints ne contiennent aucun `try/except` ni code HTTP métier |

| On simplifie (contexte hackathon 24 h) | À la place |
|---|---|
| Couches application et présentation séparées | Fusionnées dans `features/<domaine>/` |
| Une classe par use case | Une **fonction** par use case, toutes dans `use_cases.py` |
| DTO séparés des schémas d'API | Les schémas Pydantic `*In` servent de DTO aux use cases |
| Fichiers mapper dédiés | Mapping privé dans le repository (`_to_entity` / `_to_model`) |
| Conteneur d'injection / `dependencies.py` central | `Depends()` local à chaque router (pas de conflits Git entre devs) |
| Un fichier de modèle par domaine | Un seul `models.py`, une section par domaine |

Résultat : **7 fichiers par domaine** (3 domain + 3 features + 1 repository), contre ~16 dans une
Clean Architecture complète.

## Portabilité SQLite / PostgreSQL

- `DATABASE_URL` seule décide de la base : `sqlite:///./app.db` ou
  `postgresql+psycopg://user:pass@host:5432/db` (driver `psycopg` inclus dans les dépendances).
- Uniquement des types portables : `String`, `Integer`, `Boolean`, `DateTime`, `Text`, `JSON`.
  Pas de `JSONB`, `ARRAY` ni `UUID` natif : les identifiants sont des UUID stockés en `String(36)`.
- Les dates sont en UTC « aware » (`DateTime(timezone=True)`). SQLite perd le fuseau : le
  repository le réapplique à la lecture.
- Alembic utilise le mode batch sur SQLite (qui ne supporte pas `ALTER TABLE`).

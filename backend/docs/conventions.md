# Conventions

## Nommage

| Élément | Convention | Exemple |
|---|---|---|
| Fichiers Python | `snake_case.py` | `user_repository.py` |
| Classes | `PascalCase` | `User`, `SqlAlchemyUserRepository` |
| Fonctions, variables | `snake_case` | `get_user_repo`, `user_id` |
| Entités du domaine | nom métier, sans suffixe | `User`, `Product` |
| Interfaces (ABC) | nom sans préfixe `I` | `UserRepository` |
| Implémentations concrètes | préfixe de la techno | `SqlAlchemyUserRepository` |
| Modèles SQLAlchemy | suffixe `Model` | `UserModel` |
| Use cases | `verbe_entité` | `create_user`, `list_users` |
| Schémas Pydantic | suffixe `In` / `Out` | `CreateUserIn`, `UpdateUserIn`, `UserOut` |
| Exceptions métier | suffixe `Error`, héritent de `DomainError` | `UserNotFoundError` |
| Endpoints | `<use_case>_endpoint` | `create_user_endpoint` |
| Tables | pluriel, `snake_case` | `users`, `order_items` |
| Routes | pluriel, `kebab-case` | `/api/v1/users`, `/api/v1/order-items` |

Le suffixe des exceptions fixe le code HTTP (voir `shared/errors/handlers.py`) :
`*NotFoundError` → 404, `*AlreadyExistsError` → 409, tout autre `DomainError` → 400.

## Structure d'un domaine

```
src/domain/<agg>/           entities.py · exceptions.py · repository.py · __init__.py
src/features/<agg>/         schemas.py · use_cases.py · router.py · __init__.py
src/infrastructure/persistence/<agg>_repository.py
+ une section <agg> dans src/infrastructure/persistence/models.py
```

Plus de fichiers ? Seulement avec une raison écrite dans `docs/features.md` (colonne Notes).

## Exemples

### Entité et exception (domain)

```python
# src/domain/product/entities.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Product:
    id: str
    name: str
    price_cents: int          # montants en centimes (Integer portable, pas de float)
    created_at: datetime

    def apply_discount(self, percent: int) -> None:
        """Les règles métier propres à l'entité vivent ici."""
        self.price_cents = self.price_cents * (100 - percent) // 100
```

```python
# src/domain/product/exceptions.py
from src.domain.errors import DomainError


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: str) -> None:
        super().__init__(f"Product '{product_id}' not found")


class InvalidDiscountError(DomainError):   # → 400
    def __init__(self, percent: int) -> None:
        super().__init__(f"Discount must be between 0 and 100, got {percent}")
```

### Use case (features)

```python
# src/features/product/use_cases.py
def discount_product(product_id: str, dto: DiscountIn, repo: ProductRepository) -> Product:
    product = repo.get_by_id(product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    if not 0 <= dto.percent <= 100:
        raise InvalidDiscountError(dto.percent)

    product.apply_discount(dto.percent)

    return repo.update(product)
```

Règles : une fonction, le repository en paramètre, uniquement des exceptions du domaine,
aucun import de SQLAlchemy ni de `src.infrastructure`.

### Repository (infrastructure)

```python
# src/infrastructure/persistence/product_repository.py
class SqlAlchemyProductRepository(ProductRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, product_id: str) -> Product | None:
        model = self.db.get(ProductModel, product_id)
        return self._to_entity(model) if model else None

    def _to_entity(self, model: ProductModel) -> Product: ...
    def _to_model(self, product: Product) -> ProductModel: ...
```

Le repository fait le `commit()` de ses écritures. Si un use case doit enchaîner plusieurs
écritures atomiques, ajouter une méthode dédiée au repository plutôt que d'exposer la session.

### Router (features)

```python
# src/features/product/router.py
router = APIRouter(prefix="/products", tags=["products"])


def get_product_repo(db: Session = Depends(get_db)) -> ProductRepository:
    return SqlAlchemyProductRepository(db)


@router.post("/{product_id}/discount", response_model=ProductOut)
def discount_product_endpoint(
    product_id: str,
    payload: DiscountIn,
    repo: ProductRepository = Depends(get_product_repo),
) -> Product:
    return discount_product(product_id, payload, repo)
```

Un endpoint = un appel de use case. Pas de `if`, pas de `try/except`, pas de requête SQL.

### Tests

- `tests/unit/features/` : use cases avec un faux repository en mémoire (voir `tests/fakes.py`).
- `tests/integration/infrastructure/` : repository SQLAlchemy sur SQLite en mémoire (fixture
  `db_session`).
- `tests/e2e/api/` : endpoints via `httpx.AsyncClient` (fixture `client`, marqueur
  `pytestmark = pytest.mark.anyio`).

## Checklist avant de merger un domaine

- [ ] 7 fichiers max (hors `__init__.py` et tests), ou justification dans `docs/features.md`
- [ ] Aucune logique métier dans le router : chaque endpoint appelle un seul use case
- [ ] Les use cases lèvent des exceptions du domaine (suffixes `NotFoundError` / `AlreadyExistsError`)
- [ ] Modèle ajouté dans `models.py` avec des types portables uniquement
- [ ] Migration générée (`make revision m="..."`) et relue, puis appliquée (`make migrate`)
- [ ] Router ajouté à `FEATURE_ROUTERS` dans `src/main.py`
- [ ] Faux repository ajouté dans `tests/fakes.py` + tests unitaires des use cases
- [ ] Au moins un test e2e du flux principal
- [ ] `make lint` et `make test` verts (le test d'architecture inclus)
- [ ] Ligne du domaine mise à jour dans `docs/features.md`

from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy.orm import Session

from src.domain.shopping_mission import (
    ShoppingMissionAnalysis,
    ShoppingMissionAnalyzer,
    ShoppingMissionCandidate,
    ShoppingMissionSuggestion,
)
from src.features.shopping_mission.router import get_shopping_mission_analyzer
from src.infrastructure.persistence.models import ProductCategoryModel, ProductModel
from src.main import app

pytestmark = pytest.mark.anyio

SHOPPING_MISSIONS = "/api/v1/shopping-missions/recommendations"


class FakeShoppingMissionAnalyzer(ShoppingMissionAnalyzer):
    def __init__(self) -> None:
        self.suggestions: list[ShoppingMissionSuggestion] = []
        self.seen_candidates: list[ShoppingMissionCandidate] = []

    def recommend(
        self,
        mission: str,
        budget: int,
        candidates: list[ShoppingMissionCandidate],
    ) -> ShoppingMissionAnalysis:
        self.seen_candidates = candidates
        return ShoppingMissionAnalysis(
            summary=f"Sélection pour : {mission} (budget {budget} Ar)",
            suggestions=self.suggestions,
        )


@pytest.fixture
def analyzer() -> Iterator[FakeShoppingMissionAnalyzer]:
    fake = FakeShoppingMissionAnalyzer()
    app.dependency_overrides[get_shopping_mission_analyzer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_shopping_mission_analyzer, None)


def _add_product(
    db: Session,
    *,
    product_id: str,
    price: int,
    quantity: int = 5,
    is_active: bool = True,
) -> ProductModel:
    category = ProductCategoryModel(
        id=f"category-{product_id}",
        name="Sport",
        slug=f"category-{product_id}",
        is_active=True,
    )
    product = ProductModel(
        id=product_id,
        code=f"code-{product_id}",
        name=f"Produit {product_id}",
        description="Produit de test",
        price=price,
        quantity=quantity,
        is_active=is_active,
        category_id=category.id,
    )
    db.add_all([category, product])
    db.commit()
    return product


async def test_recommendations_only_include_available_products_within_budget(
    client: httpx.AsyncClient,
    db_session: Session,
    analyzer: FakeShoppingMissionAnalyzer,
) -> None:
    affordable = _add_product(db_session, product_id="affordable", price=60_000)
    _add_product(db_session, product_id="too-expensive", price=40_000)
    _add_product(db_session, product_id="out-of-stock", price=10_000, quantity=0)
    _add_product(db_session, product_id="inactive", price=10_000, is_active=False)
    analyzer.suggestions = [
        ShoppingMissionSuggestion(affordable.id, "Correspond à votre mission."),
        ShoppingMissionSuggestion("too-expensive", "Complète la sélection."),
    ]

    response = await client.post(
        SHOPPING_MISSIONS,
        json={"mission": "Reprendre le sport", "budget": 90_000},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_price"] == 60_000
    assert body["total_price"] <= body["budget"]
    assert [item["product"]["id"] for item in body["recommendations"]] == ["affordable"]
    assert {item.id for item in analyzer.seen_candidates} == {"affordable", "too-expensive"}


async def test_recommendations_reject_unknown_product_ids(
    client: httpx.AsyncClient,
    db_session: Session,
    analyzer: FakeShoppingMissionAnalyzer,
) -> None:
    _add_product(db_session, product_id="available", price=10_000)
    analyzer.suggestions = [ShoppingMissionSuggestion("invented", "Produit imaginaire.")]

    response = await client.post(
        SHOPPING_MISSIONS,
        json={"mission": "Trouver un cadeau", "budget": 50_000},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "ShoppingMissionUnavailableError"


async def test_recommendations_validate_mission_and_budget(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.features.shopping_mission import router as shopping_mission_router

    monkeypatch.setattr(
        shopping_mission_router,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=None),
    )
    response = await client.post(
        SHOPPING_MISSIONS,
        json={"mission": "ok", "budget": 0},
    )

    assert response.status_code == 422


async def test_missing_gemini_key_returns_service_unavailable(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.features.shopping_mission import router as shopping_mission_router

    monkeypatch.setattr(
        shopping_mission_router,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=None),
    )
    response = await client.post(
        SHOPPING_MISSIONS,
        json={"mission": "Reprendre le sport", "budget": 300_000},
    )

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]

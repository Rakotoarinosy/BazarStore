"""Public endpoint for budget-aware shopping mission recommendations."""

from functools import lru_cache

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.domain.shopping_mission import (
    ShoppingMissionAnalyzer,
    ShoppingMissionCandidate,
    ShoppingMissionUnavailableError,
)
from src.features.shopping_mission.schemas import (
    ShoppingMissionIn,
    ShoppingMissionOut,
    ShoppingMissionProductOut,
    ShoppingMissionRecommendationOut,
)
from src.infrastructure.config import get_settings
from src.infrastructure.external.gemini_shopping_mission import GeminiShoppingMissionAnalyzer
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import ProductCategoryModel, ProductModel

router = APIRouter(prefix="/shopping-missions", tags=["shopping missions"])


@lru_cache
def _gemini_analyzer(api_key: str, model: str) -> ShoppingMissionAnalyzer:
    return GeminiShoppingMissionAnalyzer(api_key, model)


def get_shopping_mission_analyzer() -> ShoppingMissionAnalyzer | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    return _gemini_analyzer(settings.gemini_api_key, settings.gemini_model)


@router.post("/recommendations", response_model=ShoppingMissionOut)
def recommend_for_mission(
    payload: ShoppingMissionIn,
    db: Session = Depends(get_db),
    analyzer: ShoppingMissionAnalyzer | None = Depends(get_shopping_mission_analyzer),
) -> ShoppingMissionOut:
    if analyzer is None:
        raise ShoppingMissionUnavailableError(
            "L'IA n'est pas configurée : ajoutez GEMINI_API_KEY dans le fichier .env local."
        )

    products = list(
        db.scalars(
            select(ProductModel)
            .join(ProductCategoryModel)
            .options(joinedload(ProductModel.category))
            .where(
                ProductModel.is_active.is_(True),
                ProductCategoryModel.is_active.is_(True),
                ProductModel.quantity > 0,
            )
            .order_by(ProductModel.name)
        )
    )
    candidates = [
        ShoppingMissionCandidate(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            category_name=product.category.name,
        )
        for product in products
    ]
    analysis = analyzer.recommend(payload.mission, payload.budget, candidates)
    product_by_id = {product.id: product for product in products}
    selected: list[ShoppingMissionRecommendationOut] = []
    selected_ids: set[str] = set()
    total_price = 0

    for suggestion in analysis.suggestions:
        product = product_by_id.get(suggestion.product_id)
        if product is None or product.id in selected_ids:
            raise ShoppingMissionUnavailableError(
                "L'IA a proposé un produit qui ne fait pas partie du catalogue disponible."
            )
        if total_price + product.price > payload.budget:
            continue

        inventory_status = (
            "LOWSTOCK" if product.quantity <= 5 else "INSTOCK"
        )
        image_url = (
            f"/api/v1/products/images/{product.image_key}"
            if product.image_key
            else product.image_url
        )
        selected.append(
            ShoppingMissionRecommendationOut(
                product=ShoppingMissionProductOut(
                    id=product.id,
                    code=product.code,
                    name=product.name,
                    description=product.description,
                    price=product.price,
                    quantity=product.quantity,
                    inventory_status=inventory_status,
                    image_url=image_url,
                    category_id=product.category_id,
                    category_name=product.category.name,
                    is_active=product.is_active,
                ),
                reason=suggestion.reason,
            )
        )
        selected_ids.add(product.id)
        total_price += product.price

    summary = analysis.summary
    if not selected:
        summary = "Aucun produit adapté à cette mission et à ce budget n'a été trouvé."

    return ShoppingMissionOut(
        mission=payload.mission,
        budget=payload.budget,
        total_price=total_price,
        summary=summary,
        recommendations=selected,
    )

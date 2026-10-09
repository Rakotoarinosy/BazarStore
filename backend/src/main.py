"""Point d'entrée FastAPI : configuration, CORS, handlers d'erreurs et montage des routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference
from starlette.responses import HTMLResponse

from src.bootstrap import ensure_bootstrap_admin
from src.features.auth.router import router as auth_router
from src.features.category.router import router as category_router
from src.features.order.router import router as order_router
from src.features.product.router import router as product_router
from src.features.stats.router import router as stats_router
from src.features.storefront.router import router as storefront_router
from src.features.user.router import router as user_router
from src.infrastructure.config import configure_logging, get_settings
from src.shared.errors import register_exception_handlers
from src.shared.security_headers import SecurityHeadersMiddleware

API_PREFIX = "/api/v1"

FEATURE_ROUTERS: list[APIRouter] = [
    auth_router,
    user_router,
    category_router,
    product_router,
    order_router,
    storefront_router,
    stats_router,
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_bootstrap_admin()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    # Documentation interactive masquée en production.
    show_docs = not settings.is_production
    app = FastAPI(
        title="BazarStore API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url="/redoc" if show_docs else None,
        openapi_url="/openapi.json" if show_docs else None,
    )

    # En-têtes de sécurité (HSTS seulement en production, servie en HTTPS).
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # jamais "*" : les cookies (credentials) sont activés
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)

    api = APIRouter(prefix=API_PREFIX)

    @api.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for feature_router in FEATURE_ROUTERS:
        api.include_router(feature_router)

    app.include_router(api)

    if show_docs:

        @app.get("/docs", include_in_schema=False)
        def scalar(request: Request) -> HTMLResponse:
            # Préremplit la connexion Google : Scalar revient sur /docs avec le code, puis
            # l'échange via POST /api/v1/auth/google/token (secret gardé côté serveur).
            authentication = {
                "securitySchemes": {
                    "GoogleOAuth": {
                        "flows": {
                            "authorizationCode": {
                                "x-scalar-client-id": settings.google_client_id or "",
                                "x-scalar-redirect-uri": str(request.url_for("scalar")),
                                "selectedScopes": ["openid", "email", "profile"],
                            }
                        }
                    }
                }
            }
            return get_scalar_api_reference(
                openapi_url="/openapi.json",
                title=app.title,
                authentication=authentication,
                persist_auth=True,
            )

    return app


app = create_app()

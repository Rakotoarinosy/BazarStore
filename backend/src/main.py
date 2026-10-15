"""Point d'entrée FastAPI : configuration, CORS, handlers d'erreurs et montage des routers."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference
from starlette.responses import HTMLResponse

from src.bootstrap import ensure_bootstrap_admin
from src.domain.user import Role
from src.features.auth.router import router as auth_router
from src.features.category.router import router as category_router
from src.features.newsletter.router import router as newsletter_router
from src.features.order.router import router as order_router
from src.features.product.router import router as product_router
from src.features.reaction.router import router as reaction_router
from src.features.shopping_mission.router import router as shopping_mission_router
from src.features.stats.router import router as stats_router
from src.features.storefront.router import router as storefront_router
from src.features.user.router import router as user_router
from src.infrastructure.config import configure_logging, get_settings
from src.infrastructure.persistence.database import SessionLocal
from src.infrastructure.persistence.models import (
    BackofficeAuditModel,
    OrderModel,
    PaymentAttemptModel,
    ProductCategoryModel,
    ProductModel,
    UserModel,
)
from src.infrastructure.security.deps import get_token_service
from src.shared.errors import register_exception_handlers
from src.shared.security_headers import SecurityHeadersMiddleware

API_PREFIX = "/api/v1"

FEATURE_ROUTERS: list[APIRouter] = [
    auth_router,
    user_router,
    category_router,
    product_router,
    reaction_router,
    newsletter_router,
    order_router,
    storefront_router,
    stats_router,
    shopping_mission_router,
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

    @app.middleware("http")
    async def record_backoffice_mutations(request: Request, call_next):
        path = request.url.path
        body: dict[str, object] = {}
        if request.method in {"POST", "PUT", "PATCH"} and "application/json" in request.headers.get("content-type", ""):
            raw_body = await request.body()
            try:
                parsed_body = json.loads(raw_body)
                body = parsed_body if isinstance(parsed_body, dict) else {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = {}

            async def receive_body():
                return {"type": "http.request", "body": raw_body, "more_body": False}

            request._receive = receive_body

        pre_deleted_label = ""
        early_resource_path = path.removeprefix(f"{API_PREFIX}/")
        early_parts = early_resource_path.split("/")
        if request.method == "DELETE" and early_parts[0] in {"products", "categories"} and len(early_parts) > 1:
            with SessionLocal() as db:
                if early_parts[0] == "products":
                    deleted_product = db.get(ProductModel, early_parts[1])
                    if deleted_product:
                        pre_deleted_label = f"{deleted_product.name} ({deleted_product.code})"
                else:
                    deleted_category = db.get(ProductCategoryModel, early_parts[1])
                    if deleted_category:
                        pre_deleted_label = deleted_category.name

        response = await call_next(request)
        resource_path = path.removeprefix(f"{API_PREFIX}/")
        resource = resource_path.split("/", 1)[0]
        if (response.status_code < 400 and path.startswith(f"{API_PREFIX}/")
                and resource in {"users", "categories", "products", "orders", "newsletter", "storefront"}
                and request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and not path.endswith(("/webhook", "/callback"))):
            authorization = request.headers.get("authorization", "")
            token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
            if token:
                try:
                    actor_id = get_token_service().decode(token)
                    with SessionLocal() as db:
                        actor = db.get(UserModel, actor_id)
                        if actor and actor.is_active and actor.role in {Role.ADMIN.value, Role.COMMERCIAL.value, Role.MANAGER.value}:
                            parts = resource_path.split("/")
                            entity_id = parts[1] if len(parts) > 1 and parts[1] not in {"manage", "images", "subscriptions", "settings"} else None
                            target = db.get(UserModel, entity_id) if resource == "users" and entity_id else None
                            product = db.get(ProductModel, entity_id) if resource == "products" and entity_id else None
                            category = db.get(ProductCategoryModel, entity_id) if resource == "categories" and entity_id else None
                            verb = request.method.lower()
                            action = f"{verb} {resource}"
                            details = f"{request.method} {path}"
                            entity_type = resource[:-1] if resource.endswith("s") else resource

                            if resource == "users":
                                entity_type = "compte client"
                                if verb == "post":
                                    name, email = str(body.get("name", "Nouveau compte")), str(body.get("email", ""))
                                    role_labels = {"admin": "administrateur", "commercial": "commercial", "manager": "gestionnaire", "customer": "client", "agent": "agent"}
                                    role_name = role_labels.get(str(body.get("role", "customer")), str(body.get("role", "customer")))
                                    action = "Compte créé"
                                    details = f"Compte créé : {name} ({email}), rôle {role_name}."
                                    entity_id = None
                                elif target:
                                    name, email = target.name, target.email
                                    account_label = "compte client" if target.role == Role.CUSTOMER.value else "compte utilisateur"
                                    if verb == "delete":
                                        action, details = "Compte supprimé", f"Compte supprimé : {name} ({email})."
                                    elif body.get("is_active") is False:
                                        action, details = "Compte désactivé", f"{account_label.capitalize()} désactivé : {name} ({email})."
                                    elif body.get("is_active") is True:
                                        action, details = "Compte réactivé", f"{account_label.capitalize()} réactivé : {name} ({email})."
                                    else:
                                        changed = []
                                        labels = {"name": "nom", "email": "e-mail", "role": "rôle", "agent_id": "agent associé"}
                                        role_labels = {"admin": "administrateur", "commercial": "commercial", "manager": "gestionnaire", "customer": "client", "agent": "agent"}
                                        for key, label in labels.items():
                                            if key in body and body[key] is not None:
                                                value = role_labels.get(str(body[key]), str(body[key])) if key == "role" else body[key]
                                                changed.append(f"{label} : {value}")
                                        if body.get("password"):
                                            changed.append("mot de passe réinitialisé")
                                        action = "Compte modifié"
                                        details = f"Compte client {name} ({email}) modifié" + (f" : {', '.join(changed)}." if changed else ".")
                                else:
                                    details = "Opération de gestion des comptes clients."
                            elif resource in {"products", "categories"}:
                                noun = "Produit" if resource == "products" else "Catégorie"
                                entity_type = "produit" if resource == "products" else "catégorie"
                                item = product if resource == "products" else category
                                item_name = str(body.get("name") or getattr(item, "name", "") or pre_deleted_label)
                                if verb == "post" and "/images" in path:
                                    action, details = "Image produit ajoutée", "Une image de produit a été ajoutée au catalogue."
                                elif body.get("is_active") is False:
                                    action = "Produit masqué" if resource == "products" else "Catégorie désactivée"
                                    details = f"Produit masqué de la boutique : {item_name}." if resource == "products" else f"Catégorie désactivée : {item_name}."
                                elif body.get("is_active") is True:
                                    action = "Produit rendu visible" if resource == "products" else "Catégorie activée"
                                    details = f"Produit rendu visible dans la boutique : {item_name}." if resource == "products" else f"Catégorie activée : {item_name}."
                                elif verb == "post":
                                    action = f"{noun} créé"
                                    details = f"{noun} ajouté au catalogue : {item_name or 'nouvelle entrée'}."
                                elif verb == "delete":
                                    action = f"{noun} supprimé"
                                    details = f"{noun} supprimé du catalogue : {item_name or entity_id or 'entrée supprimée'}."
                                else:
                                    action = f"{noun} modifié"
                                    changes = []
                                    field_labels = {"name": "nom", "code": "code", "price": "prix", "quantity": "stock", "category_id": "catégorie", "description": "description", "slug": "identifiant URL"}
                                    for key, label in field_labels.items():
                                        if key in body and body[key] is not None:
                                            value = f"{body[key]} Ar" if key == "price" else str(body[key])
                                            changes.append(f"{label} → {value}")
                                    details = f"{noun} modifié : {item_name or 'entrée du catalogue'}" + (f" ({', '.join(changes)})." if changes else ".")
                            elif resource == "orders":
                                if "/manage/payments/" in path and path.endswith("/cancel"):
                                    attempt_id = parts[3] if len(parts) > 3 else ""
                                    attempt = db.get(PaymentAttemptModel, attempt_id)
                                    action = "Paiement annulé"
                                    details = f"Tentative de paiement de la commande {attempt.order_reference} ({attempt.provider}) annulée." if attempt else "Tentative de paiement annulée."
                                    entity_type, entity_id = "paiement", attempt_id or None
                                else:
                                    order = db.get(OrderModel, entity_id) if entity_id else None
                                    labels = {"pending": "en attente", "confirmed": "confirmée", "processing": "en préparation", "shipped": "expédiée", "completed": "livrée", "cancelled": "annulée"}
                                    new_status = labels.get(str(body.get("status", "")), "modifié")
                                    action = "Statut de commande modifié" if verb == "patch" else "Action sur une commande"
                                    details = f"Commande {order.reference if order else ''} : statut changé vers {new_status}."
                            elif resource == "newsletter":
                                action, details = "Abonné retiré de la newsletter", "Un abonné a été retiré de la newsletter."
                            elif resource == "storefront":
                                action, details = "Boutique mise à jour", "Les paramètres ou médias de la boutique ont été mis à jour."

                            db.add(BackofficeAuditModel(
                                actor_id=actor.id,
                                actor_name=actor.name,
                                action=action,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                details=details[:500],
                                created_at=datetime.now(UTC),
                            ))
                            db.commit()
                except Exception:
                    # Le journal ne doit jamais faire échouer une opération métier déjà réussie.
                    pass
        return response

    # En-têtes de sécurité (HSTS seulement en production, servie en HTTPS).
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # jamais "*" : les cookies (credentials) sont activés
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Visitor-Id"],
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

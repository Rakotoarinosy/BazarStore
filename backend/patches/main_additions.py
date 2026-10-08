# Imports à ajouter dans src/main.py
from src.features.notification.router import router as notification_router
from src.features.priority.router import router as priority_router
from src.features.search.router import router as search_router

# FEATURE_ROUTERS : ajouter à la fin de la liste
FEATURE_ROUTERS: list[APIRouter] = [
    auth_router,
    user_router,
    demande_router,
    agent_router,
    dashboard_router,
    priority_router,
    notification_router,
    search_router,
]

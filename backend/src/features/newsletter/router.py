"""Inscription publique à la newsletter et liste des abonnés pour le backoffice."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.user import Role
from src.features.newsletter.schemas import (
    NewsletterSubscribeIn,
    NewsletterSubscribeOut,
    NewsletterSubscriber,
    NewsletterSubscribersOut,
)
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import NewsletterSubscriptionModel, utc_now
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/newsletter", tags=["newsletter"])

SUBSCRIBED_MESSAGE = "Merci ! Votre inscription à la newsletter est confirmée."


@router.post(
    "/subscriptions",
    response_model=NewsletterSubscribeOut,
    status_code=status.HTTP_201_CREATED,
)
def subscribe(payload: NewsletterSubscribeIn, db: Session = Depends(get_db)) -> NewsletterSubscribeOut:
    """Inscrit l'adresse ; la réponse est identique si elle l'était déjà,
    pour ne pas révéler quelles adresses figurent dans la liste."""
    subscription = db.scalar(
        select(NewsletterSubscriptionModel).where(NewsletterSubscriptionModel.email == payload.email)
    )
    if subscription is None:
        db.add(NewsletterSubscriptionModel(email=payload.email))
        try:
            db.commit()
        except IntegrityError:
            # Deux envois simultanés de la même adresse : l'inscription existe déjà.
            db.rollback()
    elif not subscription.is_active:
        subscription.is_active = True
        subscription.subscribed_at = utc_now()
        subscription.unsubscribed_at = None
        db.commit()
    return NewsletterSubscribeOut(message=SUBSCRIBED_MESSAGE)


@router.get(
    "/subscriptions",
    response_model=NewsletterSubscribersOut,
    dependencies=[Depends(require_roles(Role.COMMERCIAL))],
)
def list_subscribers(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> NewsletterSubscribersOut:
    """Liste les abonnés actifs, du plus récent au plus ancien."""
    active = NewsletterSubscriptionModel.is_active.is_(True)
    total = db.scalar(select(func.count()).select_from(NewsletterSubscriptionModel).where(active)) or 0
    rows = db.scalars(
        select(NewsletterSubscriptionModel)
        .where(active)
        .order_by(NewsletterSubscriptionModel.subscribed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return NewsletterSubscribersOut(
        total=total,
        subscribers=[NewsletterSubscriber(email=row.email, subscribed_at=row.subscribed_at) for row in rows],
    )

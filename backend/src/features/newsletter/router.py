"""Inscription et désinscription publiques à la newsletter, consultation et export backoffice."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.errors import DomainError
from src.domain.user import Role
from src.features.newsletter.schemas import (
    NewsletterMessageOut,
    NewsletterSubscribeIn,
    NewsletterSubscriber,
    NewsletterSubscribersOut,
    NewsletterUnsubscribeIn,
)
from src.infrastructure.config import Settings, get_settings
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models import NewsletterSubscriptionModel, utc_now
from src.infrastructure.security.deps import require_roles

router = APIRouter(prefix="/newsletter", tags=["newsletter"])

SUBSCRIBED_MESSAGE = "Merci ! Votre inscription à la newsletter est confirmée."
UNSUBSCRIBED_MESSAGE = "Votre adresse a bien été retirée de la newsletter."
# Préfixes qu'un tableur interprète comme une formule (injection CSV).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

staff_only = [Depends(require_roles(Role.COMMERCIAL))]


class NewsletterLinkNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__("Ce lien de désinscription n'est pas valide.")


class NewsletterSubscriptionNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__("Cet abonné n'existe pas.")


def _active_subscriptions(search: str | None) -> Select[tuple[NewsletterSubscriptionModel]]:
    query = select(NewsletterSubscriptionModel).where(
        NewsletterSubscriptionModel.is_active.is_(True)
    )
    if search and search.strip():
        query = query.where(
            NewsletterSubscriptionModel.email.contains(search.strip().lower(), autoescape=True)
        )
    return query


def _deactivate(subscription: NewsletterSubscriptionModel) -> None:
    if subscription.is_active:
        subscription.is_active = False
        subscription.unsubscribed_at = utc_now()


def unsubscribe_url(settings: Settings, token: str) -> str:
    return f"{settings.public_frontend_url.rstrip('/')}/newsletter/unsubscribe?token={token}"


def _csv_cell(value: str) -> str:
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


@router.post(
    "/subscriptions",
    response_model=NewsletterMessageOut,
    status_code=status.HTTP_201_CREATED,
)
def subscribe(
    payload: NewsletterSubscribeIn, db: Session = Depends(get_db)
) -> NewsletterMessageOut:
    """Inscrit l'adresse ; la réponse est identique si elle l'était déjà,
    pour ne pas révéler quelles adresses figurent dans la liste."""
    subscription = db.scalar(
        select(NewsletterSubscriptionModel).where(
            NewsletterSubscriptionModel.email == payload.email
        )
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
    return NewsletterMessageOut(message=SUBSCRIBED_MESSAGE)


@router.post("/unsubscribe", response_model=NewsletterMessageOut)
def unsubscribe(
    payload: NewsletterUnsubscribeIn, db: Session = Depends(get_db)
) -> NewsletterMessageOut:
    """Désinscription via le jeton du lien envoyé dans chaque e-mail.

    En POST plutôt qu'en GET : les antivirus de messagerie qui ouvrent les liens
    ne doivent pas désinscrire l'abonné à sa place."""
    subscription = db.scalar(
        select(NewsletterSubscriptionModel).where(
            NewsletterSubscriptionModel.unsubscribe_token == payload.token
        )
    )
    if subscription is None:
        raise NewsletterLinkNotFoundError()
    _deactivate(subscription)
    db.commit()
    return NewsletterMessageOut(message=UNSUBSCRIBED_MESSAGE)


@router.get("/subscriptions", response_model=NewsletterSubscribersOut, dependencies=staff_only)
def list_subscribers(
    search: str | None = Query(default=None, max_length=320),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> NewsletterSubscribersOut:
    """Liste les abonnés actifs, du plus récent au plus ancien."""
    query = _active_subscriptions(search)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(NewsletterSubscriptionModel.subscribed_at.desc()).limit(limit).offset(offset)
    )
    return NewsletterSubscribersOut(
        total=total,
        subscribers=[
            NewsletterSubscriber(id=row.id, email=row.email, subscribed_at=row.subscribed_at)
            for row in rows
        ],
    )


@router.get("/subscriptions/export", dependencies=staff_only)
def export_subscribers(
    search: str | None = Query(default=None, max_length=320),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Exporte les abonnés actifs en CSV, avec le lien de désinscription propre à chacun
    pour pouvoir l'insérer dans les e-mails envoyés depuis un outil externe."""
    buffer = io.StringIO()
    # Point-virgule : séparateur attendu par Excel en français.
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["email", "date_inscription", "lien_desinscription"])
    for row in db.scalars(
        _active_subscriptions(search).order_by(NewsletterSubscriptionModel.subscribed_at.desc())
    ):
        writer.writerow(
            [
                _csv_cell(row.email),
                row.subscribed_at.strftime("%Y-%m-%d %H:%M"),
                unsubscribe_url(settings, row.unsubscribe_token),
            ]
        )
    filename = f"newsletter-abonnes-{datetime.now(UTC):%Y-%m-%d}.csv"
    # BOM UTF-8 : sans lui, Excel affiche mal les caractères accentués.
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=staff_only,
)
def remove_subscriber(subscription_id: str, db: Session = Depends(get_db)) -> Response:
    """Désinscrit un abonné depuis le backoffice (demande reçue par un autre canal)."""
    subscription = db.get(NewsletterSubscriptionModel, subscription_id)
    if subscription is None:
        raise NewsletterSubscriptionNotFoundError()
    _deactivate(subscription)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

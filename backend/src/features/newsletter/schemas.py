"""Schémas de l'inscription newsletter et de la liste backoffice des abonnés."""

from datetime import datetime

from pydantic import BaseModel

from src.shared.validation import Email


class NewsletterSubscribeIn(BaseModel):
    email: Email


class NewsletterSubscribeOut(BaseModel):
    message: str


class NewsletterSubscriber(BaseModel):
    email: str
    subscribed_at: datetime


class NewsletterSubscribersOut(BaseModel):
    total: int
    subscribers: list[NewsletterSubscriber]

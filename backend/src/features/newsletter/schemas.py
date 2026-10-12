"""Schémas de l'inscription newsletter, de la désinscription et de la liste backoffice."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.shared.validation import Email


class NewsletterSubscribeIn(BaseModel):
    email: Email


class NewsletterUnsubscribeIn(BaseModel):
    token: str = Field(min_length=1, max_length=64)


class NewsletterMessageOut(BaseModel):
    message: str


class NewsletterSubscriber(BaseModel):
    id: str
    email: str
    subscribed_at: datetime


class NewsletterSubscribersOut(BaseModel):
    total: int
    subscribers: list[NewsletterSubscriber]

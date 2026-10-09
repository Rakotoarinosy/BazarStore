"""Modèles SQLAlchemy de tous les domaines.

Règle : uniquement des types portables (String, Integer, Boolean, DateTime, Text, JSON)
pour que le même code tourne sur SQLite (dev) et PostgreSQL (prod).
Après tout ajout ou modification : `make revision m="..."` puis `make migrate`.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.database import Base

# ─── helpers ────────────────────────────────────────────────────────


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


# ─── user ───────────────────────────────────────────────────────────


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255), default="", server_default="")
    role: Mapped[str] = mapped_column(
        String(20), index=True, default="customer", server_default="customer"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Champ historique conservé pour compatibilité de profil, sans dépendance
    # vers la table agents de l'ancien projet.
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    google_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    orders: Mapped[list["OrderModel"]] = relationship(back_populates="user")


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ─── catégories de marchandises ─────────────────────────────────────


class ProductCategoryModel(Base):
    __tablename__ = "product_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    products: Mapped[list["ProductModel"]] = relationship(back_populates="category", passive_deletes=True)


class StorefrontSettingsModel(Base):
    __tablename__ = "storefront_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    hero_main_image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hero_secondary_image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    category: Mapped[ProductCategoryModel] = relationship(back_populates="products")


# ─── commandes ─────────────────────────────────────────────────────


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", server_default="pending", nullable=False, index=True)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    user: Mapped[UserModel | None] = relationship(back_populates="orders")
    items: Mapped[list["OrderItemModel"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItemModel.id"
    )

    __table_args__ = (CheckConstraint("total_amount >= 0", name="ck_orders_total_nonnegative"),)


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    product_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)
    order: Mapped[OrderModel] = relationship(back_populates="items")
    product: Mapped[ProductModel | None] = relationship()

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_order_items_price_nonnegative"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("line_total >= 0", name="ck_order_items_total_nonnegative"),
    )


# ─── agent ──────────────────────────────────────────────────────────


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# ─── demande historique / legacy ─────────────────────────────────────


class DemandeModel(Base):
    __tablename__ = "demandes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    citizen_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_demandes_status_created_at", "status", "created_at"),)


# ─── demandes citoyennes ─────────────────────────────────────────────


class CitizenRequestModel(Base):
    __tablename__ = "citizen_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    citizen_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_citizen_requests_status_created_at", "status", "created_at"),)


# ─── historique des demandes ─────────────────────────────────────────


class DemandeEventModel(Base):
    __tablename__ = "demande_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    demande_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("demandes.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40), index=True)
    # Pas de FK sur l'acteur : l'historique survit à la suppression d'un utilisateur.
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


# ─── notifications ───────────────────────────────────────────────────


class NotificationReadModel(Base):
    """Notifications déjà lues, par utilisateur.

    Les notifications sont dérivées des événements de demandes : seule la clé de
    la notification (`key`) est mémorisée ici, pour savoir si elle est lue.
    """

    __tablename__ = "notification_reads"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

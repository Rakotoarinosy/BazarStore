# ─── 1) Dans DemandeModel, juste avant « # Relation inverse (déjà définie côté AgentModel) » ───

    # Priorisation automatique (T+8h)
    urgency: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    affected_citizens: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    priority_score: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )


# ─── 2) À la fin du fichier ───

# ─── notifications (T+4h) ───


class NotificationReadModel(Base):
    """État « lu » d'une notification pour un utilisateur (les notifications sont dérivées des événements)."""

    __tablename__ = "notification_reads"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # id d'un événement (demande_events) ou « late:<id demande> »
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

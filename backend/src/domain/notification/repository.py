from typing import Protocol

from src.domain.notification.entities import Notification
from src.domain.user import User


class NotificationRepository(Protocol):
    def list_for(
        self, user: User, *, unread_only: bool, limit: int
    ) -> tuple[list[Notification], int]:
        """Notifications du plus récent au plus ancien, et nombre total de non lues."""
        ...

    def mark_read(self, user_id: str, key: str) -> None: ...

    def mark_all_read(self, user: User) -> int: ...

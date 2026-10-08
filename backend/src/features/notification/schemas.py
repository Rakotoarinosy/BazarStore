from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    kind: str  # created / accepted / rejected / assigned / resolved / late
    title: str
    message: str
    demande_id: str
    created_at: datetime
    is_read: bool


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int

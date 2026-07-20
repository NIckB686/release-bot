from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.models import Repo
from datetime import datetime, timezone
from app.database.models.base import Base

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Chat(Base):
    __tablename__ = "chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    lang: Mapped[str] = mapped_column(String(2), default='en')
    github_username: Mapped[str | None] = mapped_column(String)
    release_note_format: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    repos: Mapped[list["Repo"]] = relationship(
        secondary='chat_repo',
        back_populates='chats',
    )

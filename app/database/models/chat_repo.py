from sqlalchemy import ForeignKey, sql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class ChatRepo(Base):
    __tablename__ = "chat_repo"
    chat_id: Mapped[int] = mapped_column(ForeignKey('chat.id'), primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey('repo.id'), primary_key=True)
    process_pre_releases: Mapped[bool] = mapped_column(default=True, server_default=sql.True_())
    starred: Mapped[bool] = mapped_column(default=False, server_default=sql.False_())

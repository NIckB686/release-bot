from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Chat, ChatRepo, Release, Repo


def get_chat_repo(chat: Chat, repo: Repo, session: Session) -> ChatRepo:
    res = session.scalar(
        select(ChatRepo).where(
            ChatRepo.chat_id == chat.id,
            ChatRepo.repo_id == repo.id,
        )
    )
    if not isinstance(res, ChatRepo):
        raise RuntimeError(
            "Couldn't find ChatRepo with 'chat_id' == chat.id and 'repo_id' == repo.id"
        )
    return res


def get_latest_chat_release(session, chat, repo) -> Release | None:
    if repo.releases:
        chat_repo = get_chat_repo(chat, repo, session)

        if chat_repo.process_pre_releases:
            return repo.releases[-1]
        return session.scalar(
            select(Release)
            .where(
                Release.repo_id == repo.id,
                Release.pre_release.is_(False),
            )
            .order_by(Release.id.desc())
        )
    return None

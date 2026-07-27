import asyncio
import contextlib
import logging

import github
import telegram
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from github.GitRelease import GitRelease
from github.Tag import Tag
from sqlalchemy import select

from app.database import SessionLocal
from app.database.models import Chat, Repo
from app.database.models.chat_repo import ChatRepo
from app.github_obj import github_obj
from app.repo_engine import format_release_message, store_latest_release
from app.telegram_bot import add_starred_repos

logger = logging.getLogger(__name__)


async def poll_github(bot: Bot):
    with SessionLocal() as session:
        for repo_obj in session.scalars(select(Repo)):
            # TODO: Filter blocked repos from SQL query
            if repo_obj.blocked:
                continue

            try:
                logger.info("Poll GitHub repo %s", repo_obj.full_name)
                repo = github_obj.get_repo(repo_obj.id)
            except github.UnknownObjectException:
                message = f"GitHub repo {repo_obj.full_name} has been deleted"
                for chat in repo_obj.chats:
                    with contextlib.suppress(telegram.error.Forbidden):
                        asyncio.run(
                            bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                disable_web_page_preview=True,
                            )
                        )

                logger.info(message)
                session.delete(repo_obj)
                session.commit()
                continue
            except github.GithubException as e:
                if e.status in (403, 451):
                    message = f"GitHub repo {repo_obj.full_name} has been blocked"
                    for chat in repo_obj.chats:
                        with contextlib.suppress(telegram.error.Forbidden):
                            await bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                disable_web_page_preview=True,
                            )

                    logger.info(message)
                    repo_obj.blocked = True
                    session.commit()
                else:
                    logger.error(
                        "GithubException for %s in poll_github: %s",
                        repo_obj.full_name,
                        e,
                    )
                continue

            if repo.archived and not repo_obj.archived:
                message = f"GitHub repo <b>{repo_obj.full_name}</b> has been archived"
                for chat in repo_obj.chats:
                    with contextlib.suppress(telegram.error.Forbidden):
                        asyncio.run(
                            bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                parse_mode=ParseMode.HTML,
                                link_preview_options=LinkPreviewOptions(
                                    url=repo_obj.link, prefer_small_media=True
                                ),
                            )
                        )

                logger.info(message)
                repo_obj.archived = repo.archived
                session.commit()
            elif not repo.archived and repo_obj.archived:
                repo_obj.archived = repo.archived
                session.commit()

            release_or_tag, prerelease = store_latest_release(session, repo, repo_obj)
            if isinstance(release_or_tag, GitRelease):
                release = release_or_tag
                logger.info("Process new release %s", release.name)

                for chat in repo_obj.chats:
                    message, parse_mode, entities = format_release_message(
                        chat.release_note_format, repo, release
                    )

                    try:
                        asyncio.run(
                            bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                parse_mode=parse_mode,
                                entities=entities,
                                link_preview_options=LinkPreviewOptions(
                                    url=repo_obj.link, prefer_small_media=True
                                ),
                            )
                        )
                    except telegram.error.Forbidden:
                        logger.info("Bot was blocked by the user")
                        session.delete(chat)
                        session.commit()
            elif isinstance(release_or_tag, Tag):
                tag = release_or_tag
                logger.info("Process new tag %s", tag.name)

                # TODO: Use tag.message as release_body text
                message = (
                    f"<a href='{repo.html_url}'>{repo.full_name}</a>:\n"
                    f"<code>{tag.name}</code>"
                )

                for chat in repo_obj.chats:
                    try:
                        asyncio.run(
                            bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                parse_mode=ParseMode.HTML,
                                link_preview_options=LinkPreviewOptions(
                                    url=repo_obj.link, prefer_small_media=True
                                ),
                            )
                        )
                    except telegram.error.Forbidden:
                        logger.info("Bot was blocked by the user")
                        session.delete(chat)
                        session.commit()
            if isinstance(prerelease, GitRelease):
                release = prerelease
                logger.info("Process new prerelease %s", release.name)

                for chat in repo_obj.chats:
                    chat_repo = session.scalar(
                        select(ChatRepo)
                        .where(ChatRepo.chat_id == chat.id, ChatRepo.repo_id == repo_obj.id),
                    )
                    if isinstance(chat_repo, ChatRepo) and not chat_repo.process_pre_releases:
                        break

                    message, parse_mode, entities = format_release_message(
                        chat.release_note_format, repo, release
                    )

                    try:
                        asyncio.run(
                            bot.send_message(
                                chat_id=chat.id,
                                text=message,
                                parse_mode=parse_mode,
                                entities=entities,
                                link_preview_options=LinkPreviewOptions(
                                    url=repo_obj.link, prefer_small_media=True
                                ),
                            )
                        )
                    except telegram.error.Forbidden:
                        logger.info("Bot was blocked by the user")
                        session.delete(chat)
                        session.commit()


async def poll_github_user(bot: Bot):
    with SessionLocal() as session:
        stmt = select(Chat).where(Chat.github_username.is_not(None))
        for chat in session.scalars(stmt):
            try:
                # pyrefly: ignore [bad-argument-type]
                github_user = github_obj.get_user(chat.github_username)
            except github.GithubException:
                logger.error("Can't found user '%s'", chat.github_username)
                continue

            try:
                asyncio.run(
                    add_starred_repos(
                        chat.id, github_user, bot, session
                    )
                )
            except telegram.error.Forbidden:
                logger.info("Bot was blocked by the user")
                session.delete(chat)
                session.commit()

            for repo_obj in chat.repos:
                try:
                    repo = github_obj.get_repo(repo_obj.id)
                except github.GithubException as e:
                    if e.status == 451:
                        message = f"GitHub repo {repo_obj.full_name} has been blocked"
                        logger.info(message)
                    else:
                        raise
                    continue

                starred = repo in github_user.get_starred()
                chat_repo = session.scalar(
                    select(ChatRepo)
                    .where(ChatRepo.chat_id == chat.id, ChatRepo.repo_id == repo_obj.id),
                )
                if isinstance(chat_repo, ChatRepo) and chat_repo.starred != starred:
                    chat_repo.starred = starred
                    session.commit()


async def clear_db():
    with SessionLocal() as session:
        for repo_obj in session.scalars(select(Repo)):
            #  TODO: Use sqlalchemy_utils.auto_delete_orphans
            if repo_obj.is_orphan():
                logger.info("Delete orphaned GitHub repo %s", repo_obj.full_name)
                session.delete(repo_obj)
        session.commit()

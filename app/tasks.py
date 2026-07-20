import asyncio
import logging

import github
import telegram
from github.GitRelease import GitRelease
from github.Tag import Tag
from sqlalchemy import select
from telegram import LinkPreviewOptions
from telegram.constants import ParseMode

from app.github_obj import github_obj
from app import telegram_bot
from app.database import SessionLocal
from app.database.models import Chat, Repo
from app.database.models.chat_repo import ChatRepo
from app.repo_engine import format_release_message, store_latest_release

logger = logging.getLogger(__name__)


def poll_github():
    with SessionLocal() as session:
        if not asyncio.run(telegram_bot.test_token()):
            logger.critical('Telegram bot token is invalid or server not available')
            return

        for repo_obj in session.scalars(select(Repo)):
            # TODO: Filter blocked repos from SQL query
            if repo_obj.blocked:
                continue

            try:
                logger.info("Poll GitHub repo %s", repo_obj.full_name)
                repo = github_obj.get_repo(repo_obj.id)
            except github.UnknownObjectException as e:
                message = f"GitHub repo {repo_obj.full_name} has been deleted"
                for chat in repo_obj.chats:
                    try:
                        asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                              text=message,
                                                              disable_web_page_preview=True))
                    except telegram.error.Forbidden as e:
                        pass

                logger.info(message)
                session.delete(repo_obj)
                session.commit()
                continue
            except github.GithubException as e:
                if e.status in (403, 451):
                    message = f"GitHub repo {repo_obj.full_name} has been blocked"
                    for chat in repo_obj.chats:
                        try:
                            asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                                  text=message,
                                                                  disable_web_page_preview=True))
                        except telegram.error.Forbidden as e:
                            pass

                    logger.info(message)
                    repo_obj.blocked = True
                    session.commit()
                else:
                    logger.error(f"GithubException for %s in poll_github: %s", repo_obj.full_name, e)
                continue

            if repo.archived and not repo_obj.archived:
                message = f"GitHub repo <b>{repo_obj.full_name}</b> has been archived"
                for chat in repo_obj.chats:
                    try:
                        asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                              text=message,
                                                              parse_mode=ParseMode.HTML,
                                                              link_preview_options=LinkPreviewOptions(
                                                                  url=repo_obj.link,
                                                                  prefer_small_media=True),
                                                              ))
                    except telegram.error.Forbidden as e:
                        pass

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
                    message, parse_mode, entities = format_release_message(chat.release_note_format, repo, release)

                    try:
                        asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                              text=message,
                                                              parse_mode=parse_mode,
                                                              entities=entities,
                                                              link_preview_options=LinkPreviewOptions(
                                                                  url=repo_obj.link,
                                                                  prefer_small_media=True),
                                                              ))
                    except telegram.error.Forbidden as e:
                        logger.info('Bot was blocked by the user')
                        session.delete(chat)
                        session.commit()
            elif isinstance(release_or_tag, Tag):
                tag = release_or_tag
                logger.info("Process new tag %s", tag.name)

                # TODO: Use tag.message as release_body text
                message = (f"<a href='{repo.html_url}'>{repo.full_name}</a>:\n"
                           f"<code>{tag.name}</code>")

                for chat in repo_obj.chats:
                    try:
                        asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                              text=message,
                                                              parse_mode=ParseMode.HTML,
                                                              link_preview_options=LinkPreviewOptions(
                                                                  url=repo_obj.link,
                                                                  prefer_small_media=True),
                                                              ))
                    except telegram.error.Forbidden as e:
                        logger.info('Bot was blocked by the user')
                        session.delete(chat)
                        session.commit()
            if isinstance(prerelease, GitRelease):
                release = prerelease
                logger.info("Process new prerelease %s", release.name)

                for chat in repo_obj.chats:
                    chat_repo = session.scalar(
                        select(ChatRepo)
                        .where(ChatRepo.chat_id == chat.id)
                        .where(ChatRepo.repo_id == repo_obj.id),
                    )
                    if not chat_repo.process_pre_releases:
                        break

                    message, parse_mode, entities = format_release_message(chat.release_note_format, repo, release)

                    try:
                        asyncio.run(telegram_bot.send_message(chat_id=chat.id,
                                                              text=message,
                                                              parse_mode=parse_mode,
                                                              entities=entities,
                                                              link_preview_options=LinkPreviewOptions(
                                                                  url=repo_obj.link,
                                                                  prefer_small_media=True),
                                                              ))
                    except telegram.error.Forbidden as e:
                        logger.info('Bot was blocked by the user')
                        session.delete(chat)
                        session.commit()


def poll_github_user():
    with SessionLocal() as session:
        stmt = select(Chat).where(Chat.github_username.is_not(None))
        for chat in session.scalars(stmt):
            try:
                github_user = github_obj.get_user(chat.github_username)
            except github.GithubException as e:
                logger.error(f"Can't found user '%s'", chat.github_username)
                continue

            try:
                asyncio.run(telegram_bot.add_starred_repos(chat.id, github_user, telegram_bot, session))
            except telegram.error.Forbidden as e:
                logger.info('Bot was blocked by the user')
                session.delete(chat)
                session.commit()

            for repo_obj in chat.repos:
                try:
                    repo = github_obj.get_repo(repo_obj.id)
                except github.GithubException as e:
                    if e.status in (451,):
                        message = f"GitHub repo {repo_obj.full_name} has been blocked"
                        logger.info(message)
                    else:
                        raise
                    continue

                starred = repo in github_user.get_starred()
                chat_repo = session.scalar(
                    select(ChatRepo)
                    .where(ChatRepo.chat_id == chat.id)
                    .where(ChatRepo.repo_id == repo_obj.id),
                )
                if chat_repo.starred != starred:
                    chat_repo.starred = starred
                    session.commit()


def clear_db():
    with SessionLocal() as session:
        for repo_obj in session.scalars(select(Repo)):
            #  TODO: Use sqlalchemy_utils.auto_delete_orphans
            if repo_obj.is_orphan():
                logger.info("Delete orphaned GitHub repo %s", repo_obj.full_name)
                session.delete(repo_obj)
        session.commit()

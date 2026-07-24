import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.database import SessionLocal, engine
from app.github_obj import github_obj
from app.routes import router
from app.tasks import clear_db, poll_github, poll_github_user
from config import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.github_obj = github_obj
    app.state.engine = engine
    app.state.session_local = SessionLocal
    from app.telegram_bot import TelegramBot

    telegram_bot = TelegramBot(settings, github_obj)
    if not await telegram_bot.test_token():
        raise RuntimeError("Telegram bot token is invalid or server not available")
    telegram_bot.start()
    app.state.telegram_bot = telegram_bot
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        poll_github,
        trigger="interval",
        id="poll_github",
        minutes=settings.GITHUB_POLL_INTERVAL,
        replace_existing=True,
        kwargs={"telegram_bot": telegram_bot},
    )
    scheduler.add_job(
        poll_github_user,
        trigger="cron",
        id="poll_github_user",
        hour="*/8",
        replace_existing=True,
        kwargs={"telegram_bot": telegram_bot},
    )

    scheduler.add_job(
        clear_db,
        trigger="cron",
        id="clear_db",
        week="*",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    yield
    scheduler.shutdown()
    engine.dispose()


def create_app():
    return FastAPI(lifespan=lifespan)


if __name__ == "__main__":
    app = create_app()
    app.include_router(router)

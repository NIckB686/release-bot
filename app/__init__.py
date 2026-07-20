import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from app.github_obj import github_obj
from app.tasks import clear_db, poll_github, poll_github_user
from config import settings

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.update(settings.model_dump())
    app.logger.setLevel(settings.LOG_LEVEL)

    return app


app = create_app()

if settings.TELEGRAM_BOT_TOKEN:
    from app.telegram_bot import TelegramBot

    telegram_bot = TelegramBot(settings, github_obj)
    if not asyncio.run(telegram_bot.test_token()):
        raise RuntimeError('Telegram bot token is invalid or server not available')
    telegram_bot.start()
else:
    telegram_bot = None
    logger.critical('Telegram bot token not specified')

scheduler = BackgroundScheduler()
scheduler.add_job(
    poll_github,
    trigger="interval",
    id="poll_github",
    minutes=settings.GITHUB_POLL_INTERVAL,
    replace_existing=True,
)
scheduler.add_job(
    poll_github_user,
    trigger="cron",
    id="poll_github_user",
    hour="*/8",
    replace_existing=True,
)

scheduler.add_job(
    clear_db,
    trigger="cron",
    id="clear_db",
    week="*",
    replace_existing=True,
)
scheduler.start()

from app import database, routes  # noqa: E402
from app.database import models

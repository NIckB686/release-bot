from http import HTTPStatus

from flask import Response, request
from sqlalchemy import func, select

from app import app, telegram_bot
from app._version import __version__
from app.database import SessionLocal
from app.database.models import Repo
from app.database.models.release import Release
from app.database.models.chat import Chat


@app.route('/')
async def index():
    bot_me = await telegram_bot.get_me()
    return (
        f'<a href="https://t.me/{bot_me.username}">{bot_me.first_name}</a> - a telegram bot for GitHub releases v{__version__}.'
        '<br><br>'
        'Source code available at <a href="https://github.com/JanisV/release-bot">JanisV/release-bot</a>')


@app.route('/stats')
async def stats():
    with SessionLocal() as session:
        users = session.scalar(select(func.count()).select_from(Chat))
        repos = session.scalar(select(func.count()).select_from(Repo))
        releases = session.scalar(select(func.count()).select_from(Release))

    statistics = {
        "users": users,
        "repos": repos,
        "releases": releases,
    }
    return statistics


@app.post("/telegram")
async def telegram() -> Response:
    if app.config['SITE_URL']:
        await telegram_bot.webhook(request.json)
        return Response(status=HTTPStatus.OK)
    else:
        return Response(status=HTTPStatus.NOT_IMPLEMENTED)

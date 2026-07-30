from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat


async def get_or_create_chat(session: AsyncSession, chat_id: int) -> Chat:
    chat = await session.get(Chat, chat_id)
    if not chat:
        chat = Chat(
            id=chat_id,
        )
        session.add(chat)
        await session.commit()

    return chat

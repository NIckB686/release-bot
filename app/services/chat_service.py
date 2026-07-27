from sqlalchemy.orm import Session

from app.database.models import Chat


def get_or_create_chat(session: Session, chat_id: int) -> Chat:
    chat = session.get(Chat, chat_id)
    if not chat:
        chat = Chat(
            id=chat_id,
        )
        session.add(chat)
        session.commit()

    return chat

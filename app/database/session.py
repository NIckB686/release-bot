from sqlalchemy.orm import sessionmaker

from .engine import engine

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

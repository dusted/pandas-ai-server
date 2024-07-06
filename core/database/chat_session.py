from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_scoped_session
from sqlalchemy.orm import sessionmaker
from contextvars import ContextVar
import os

chat_db_url = os.getenv("CHAT_DB_URL")

chat_engine = create_async_engine(chat_db_url, pool_recycle=3600, echo=True)

ChatSession = sessionmaker(
    class_=AsyncSession,
    expire_on_commit=False,
    bind=chat_engine
)

chat_session_context = ContextVar("chat_session_context")

chat_session = async_scoped_session(
    session_factory=ChatSession,
    scopefunc=chat_session_context.get,
)
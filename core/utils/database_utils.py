# core/utils/database_utils.py

import pandas as pd
from sqlalchemy.sql import text
from core.database.chat_session import chat_session, chat_session_context

async def load_data_from_db(query: str) -> pd.DataFrame:
    # Set the context variable for chat session
    token = chat_session_context.set("chat_session")
    try:
        async with chat_session() as conn:
            result = await conn.execute(text(query))
            print(result)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
    finally:
        # Reset the context variable
        chat_session_context.reset(token)
    return df
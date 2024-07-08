from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv
from core.config import config
from core.database import create_session  # Ensure this import works

load_dotenv()

app = FastAPI()

@app.get("/")
def read_root():
    return {"POSTGRES_URL": config.POSTGRES_URL, "CHAT_DB_URL": config.CHAT_DB_URL}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

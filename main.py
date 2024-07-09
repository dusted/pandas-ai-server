import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from core.config import config

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app="core.server:app",
        reload=True if config.ENVIRONMENT != "production" else False,
        host=os.environ.get("SERVER_HOST", "0.0.0.0"),
        port=port,
        workers=1,
    )

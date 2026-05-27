import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from routers.api import router as api_router
from bot import dp, bot, on_startup

@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup()
    asyncio.create_task(dp.start_polling(bot))
    yield

app = FastAPI(lifespan=lifespan)

app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")

app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

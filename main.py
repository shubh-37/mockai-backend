from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging
from fastapi.responses import JSONResponse
from database import initialize_database
from services import users_service
from services import interview_service
from services import company_service
from services import aptitude_service
import redis.asyncio as redis_asyncio
import os
from dotenv import load_dotenv

load_dotenv()

logging.getLogger("pymongo").setLevel(logging.WARNING)

app = FastAPI()

origins = [
    "http://localhost:5173",
    "https://mockai.tech",
    "https://www.mockai.tech",
    "https://dev.mockai.tech",
    "https://dev-api.mockai.tech",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_redis():
    redis = redis_asyncio.from_url(os.getenv("REDIS_URI"), decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()


@app.on_event("startup")
async def startup_event():
    await initialize_database()


@app.get("/")
async def health_check():
    return JSONResponse(content={"message": "Success."})


app.include_router(
    users_service.router,
    prefix="/user",
    tags=["User"],
    dependencies=[Depends(get_redis)],
)

app.include_router(interview_service.router, prefix="/interview", tags=["Interview"])

app.include_router(company_service.router, prefix="/company", tags=["Company"])

app.include_router(aptitude_service.router, prefix="/aptitude", tags=["Aptitude"])

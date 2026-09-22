import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

# Import authentication and Customer 360 routes
from app.auth import router as auth_router
from app.customer360 import router as customer360_router

app = FastAPI(title="SSO Demo & Customer 360 Smart Schema Mapper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enable sessions for OAuth state and login data
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "default_secret_key"),
)

app.include_router(auth_router)
app.include_router(customer360_router)

#  endpoint
@app.get("/")
def home():

    return {"message": "SSO Demo Backend is running"}
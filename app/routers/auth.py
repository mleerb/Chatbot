from fastapi import APIRouter, Request, Response

from app.dependencies import BrowserSession
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthResponse)
def me(current: BrowserSession):
    return {"user": current[1].account, "guest": current[1].guest}


@router.post("/guest", response_model=AuthResponse)
def guest(current: BrowserSession, request: Request, response: Response):
    token = service.guest(current, response, request.url.scheme == "https")
    return {"user": None, "guest": True, "guest_token": token}


@router.post("/guest/close")
def close_guest(current: BrowserSession):
    service.close_guest(current)
    return {"ok": True}


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, current: BrowserSession, request: Request, response: Response):
    service.throttle(request.client.host if request.client else "local")
    account = service.register(str(payload.email), payload.name, payload.password)
    service.establish(current, account, response, request.url.scheme == "https")
    return {"user": account}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, current: BrowserSession, request: Request, response: Response):
    service.throttle(request.client.host if request.client else "local")
    account = service.login(str(payload.email), payload.password)
    service.establish(current, account, response, request.url.scheme == "https")
    return {"user": account}


@router.post("/logout", response_model=AuthResponse)
def logout(current: BrowserSession, response: Response):
    service.logout(current, response)
    return {"user": None}

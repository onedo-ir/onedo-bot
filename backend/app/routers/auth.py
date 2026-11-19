from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import PanelUserOut, Token, UserLogin
from app.security import (
    PanelUser,
    create_access_token,
    get_current_user,
    get_panel_user,
    verify_panel_credentials,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: UserLogin):
    if not verify_panel_credentials(payload.email, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ایمیل یا رمز اشتباه است",
        )
    panel = get_panel_user()
    return Token(access_token=create_access_token(panel.email))


@router.get("/me", response_model=PanelUserOut)
def me(user: PanelUser = Depends(get_current_user)):
    return PanelUserOut(
        email=user.email,
        full_name=user.full_name,
        theme_preference=user.theme_preference,
    )

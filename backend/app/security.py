from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import compare_digest

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)
admin_api_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)
settings = get_settings()


@dataclass(frozen=True)
class PanelUser:
    email: str
    full_name: str
    theme_preference: str = "dark"


def get_panel_user() -> PanelUser:
    email = (settings.default_admin_email or "").strip().lower()
    name = email.split("@")[0] if email else "مدیر"
    return PanelUser(email=email, full_name=name or "مدیر", theme_preference="dark")


def verify_panel_credentials(email: str, password: str) -> bool:
    expected_email = (settings.default_admin_email or "").strip().lower()
    expected_password = settings.default_admin_password or ""
    if not expected_email or not expected_password:
        return False
    return compare_digest(email.strip().lower(), expected_email) and compare_digest(
        password, expected_password
    )


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PanelUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ورود لازم است")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر") from exc

    panel = get_panel_user()
    if not panel.email or email.strip().lower() != panel.email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="کاربر یافت نشد")
    return panel


def verify_admin_api_token(
    x_admin_token: str | None = Security(admin_api_header),
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    token = x_admin_token
    if not token and authorization:
        token = authorization.credentials
    if not token or token != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="توکن ADMIN_API_TOKEN نامعتبر است",
        )

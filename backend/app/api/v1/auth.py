from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_session, get_current_user
from app.api.http_utils import client_ip
from app.core.cookies import clear_csrf_cookie, clear_session_cookie, set_csrf_cookie, set_session_cookie
from app.core.csrf import generate_csrf_token
from app.core.rate_limit import enforce_auth_rate_limit
from app.db.session import get_db
from app.models import Session as SessionModel
from app.models import User
from app.schemas.auth import (
    EmailVerifyRequest,
    LoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    SignupRequest,
    UserRead,
)
from app.schemas.organization import InvitationAcceptRequest, MemberRead
from app.services import auth as auth_service
from app.services import organizations as org_service
from app.services.audit import record_event
from app.services.email import EmailService, get_email_service
from app.services.sessions import create_session, revoke_session, session_cookie_max_age_seconds

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(request: Request, response: Response, db: DBSession, user: User) -> None:
    _, raw_session_token = create_session(
        db, user, ip_address=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    max_age = session_cookie_max_age_seconds()
    set_session_cookie(response, raw_session_token, max_age)
    set_csrf_cookie(response, generate_csrf_token(), max_age)


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Annotated[DBSession, Depends(get_db)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> User:
    enforce_auth_rate_limit(request, scope="signup", identifier=payload.email)
    try:
        user = auth_service.signup(
            db,
            email_service,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            ip_address=client_ip(request),
        )
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    _start_session(request, response, db, user)
    return user


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[DBSession, Depends(get_db)],
) -> User:
    enforce_auth_rate_limit(request, scope="login", identifier=payload.email)
    user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        record_event(
            db,
            "login_failed",
            actor_user_id=None,
            ip_address=client_ip(request),
            metadata={"email": payload.email.strip().lower()},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )

    _start_session(request, response, db, user)
    record_event(db, "login_succeeded", actor_user_id=user.id, ip_address=client_ip(request))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(
    request: Request,
    response: Response,
    db: Annotated[DBSession, Depends(get_db)],
    session: Annotated[SessionModel, Depends(get_current_session)],
) -> None:
    actor_user_id = session.user_id
    revoke_session(db, session)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    record_event(db, "logout", actor_user_id=actor_user_id, ip_address=client_ip(request))


@router.get("/me", response_model=UserRead)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


@router.post("/email/verify", response_model=UserRead)
def verify_email(
    payload: EmailVerifyRequest, request: Request, db: Annotated[DBSession, Depends(get_db)]
) -> User:
    user = auth_service.verify_email(db, payload.token, ip_address=client_ip(request))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token."
        )
    return user


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: PasswordForgotRequest,
    request: Request,
    db: Annotated[DBSession, Depends(get_db)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> dict[str, str]:
    enforce_auth_rate_limit(request, scope="password_reset_request", identifier=payload.email)
    auth_service.request_password_reset(db, email_service, payload.email, ip_address=client_ip(request))
    return {"detail": "If that email is registered, a password reset link has been sent."}


@router.post("/password/reset", response_model=UserRead)
def reset_password(
    payload: PasswordResetRequest, request: Request, db: Annotated[DBSession, Depends(get_db)]
) -> User:
    user = auth_service.reset_password(
        db, payload.token, payload.new_password, ip_address=client_ip(request)
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token."
        )
    return user


@router.post("/invitations/accept", response_model=MemberRead)
def accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
    response: Response,
    db: Annotated[DBSession, Depends(get_db)],
) -> MemberRead:
    try:
        user, membership = org_service.accept_invitation(
            db,
            raw_token=payload.token,
            organization_id=payload.organization_id,
            password=payload.password,
            full_name=payload.full_name,
        )
    except org_service.InvalidInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired invitation."
        ) from exc
    except org_service.PasswordRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A password is required to accept this invitation.",
        ) from exc

    db.commit()
    db.refresh(membership)

    _start_session(request, response, db, user)
    record_event(
        db,
        "invitation_accepted",
        actor_user_id=user.id,
        organization_id=payload.organization_id,
        target_type="organization_member",
        target_id=membership.id,
        ip_address=client_ip(request),
    )

    return MemberRead.from_membership(membership)

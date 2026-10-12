"""Administrative routes reuse authenticated sessions and CSRF protection."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.admin import invite_service, stats_service, user_service
from app.auth.dependencies import get_session_factory, require_admin


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin), Depends(no_store)]
)


def database(factory=Depends(get_session_factory)):
    try:
        with factory() as db:
            yield db
    except SQLAlchemyError as exc:
        raise HTTPException(503, "管理数据暂不可用，请稍后重试") from exc


class UserStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool = Field(strict=True)


class NewInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_uses: int = Field(default=50, strict=True, ge=1, le=10000)
    days: int = Field(default=7, strict=True, ge=1, le=3650)


@router.get("/users")
def users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=320),
    disabled: bool | None = None,
    db=Depends(database),
):
    return user_service.list_users(db, limit=limit, offset=offset, q=q.strip(), disabled=disabled)


@router.patch("/users/{user_id}")
def user_status(body: UserStatus, user_id: int = Path(ge=1, le=2147483647), db=Depends(database)):
    return user_service.set_disabled(db, user_id, body.disabled)


@router.get("/invites")
def invites(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(database)
):
    return invite_service.list_invites(db, limit=limit, offset=offset)


@router.post("/invites", status_code=201)
def new_invite(body: NewInvite, db=Depends(database)):
    return invite_service.generate_invite(db, max_uses=body.max_uses, days=body.days)


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: int = Path(ge=1, le=2147483647), db=Depends(database)):
    return invite_service.revoke_invite(db, invite_id)


@router.get("/stats/overview")
def overview(db=Depends(database)):
    return stats_service.overview(db)


@router.get("/stats/llm-usage")
def usage(db=Depends(database)):
    return stats_service.llm_usage(db)

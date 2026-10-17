"""Server-operator commands; no public administration HTTP endpoints."""

import argparse
import getpass
from datetime import timedelta

from sqlalchemy import select, update

from app.auth.models import Invite, LoginSession, User
from app.auth.schemas import EmailRequest
from app.auth.service import create_invite, password_hash, utcnow
from app.database import Base, SessionLocal, engine


def adjust_invite(db, invite_id, *, max_uses=None, revoked=None, days=None):
    row = db.scalar(select(Invite).where(Invite.id == invite_id).with_for_update())
    if row is None:
        raise ValueError("邀请码不存在")
    if max_uses is not None:
        if max_uses < max(1, row.uses):
            raise ValueError("上限不能低于已使用名额")
        row.max_uses = max_uses
    if revoked is not None:
        row.revoked = revoked
    if days is not None:
        if days <= 0:
            raise ValueError("续期天数须为正数")
        row.expires_at = utcnow() + timedelta(days=days)
    db.commit()


def disable_user(db, user_id):
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("账号不存在")
    user.disabled = True
    db.execute(update(LoginSession).where(LoginSession.user_id == user_id).values(revoked=True))
    db.commit()


def bootstrap_admin(db, email, password, *, verified_email: bool):
    if not verified_email:
        raise ValueError("管理员邮箱必须由服务器操作者显式核验")
    email = EmailRequest(email=email).email
    if db.scalar(select(User).where(User.email == email)):
        raise ValueError("账号已存在；不能用 bootstrap 覆盖账号")
    user = User(
        email=email,
        password_hash=password_hash(password),
        verified=True,
        is_admin=True,
        pending_expires_at=utcnow(),
    )
    db.add(user)
    db.commit()
    return user.id


def main():
    parser = argparse.ArgumentParser(description="仅服务器操作者可执行；不会自动发信或认领旧分组")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-auth-schema")
    bootstrap = commands.add_parser("bootstrap-admin")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--verified-email", action="store_true", required=True)
    create = commands.add_parser("create-invite")
    create.add_argument("--max-uses", type=int, default=50)
    create.add_argument("--days", type=int, default=7)
    adjust = commands.add_parser("adjust-invite")
    adjust.add_argument("id", type=int)
    adjust.add_argument("--max-uses", type=int)
    adjust.add_argument("--revoke", action="store_true", default=None)
    adjust.add_argument("--days", type=int)
    disable = commands.add_parser("disable-user")
    disable.add_argument("id", type=int)
    args = parser.parse_args()
    if args.command == "init-auth-schema":
        # Explicitly creates missing tables; existing private tables are migrated separately.
        Base.metadata.create_all(engine)
        return
    with SessionLocal() as db:
        if args.command == "bootstrap-admin":
            user_id = bootstrap_admin(
                db, args.email, getpass.getpass("Password: "), verified_email=args.verified_email
            )
            print(f"管理员 ID: {user_id}")
        elif args.command == "create-invite":
            invite_id, code = create_invite(db, max_uses=args.max_uses, days=args.days)
            print(f"邀请码 ID: {invite_id}\n{code}")
        elif args.command == "adjust-invite":
            adjust_invite(db, args.id, max_uses=args.max_uses, revoked=args.revoke, days=args.days)
        elif args.command == "disable-user":
            disable_user(db, args.id)


if __name__ == "__main__":
    main()

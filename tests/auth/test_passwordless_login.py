"""测试邮箱验证码登录和可选邀请码注册功能"""

from app.auth.models import User
from app.auth.service import create_invite, issue_token, password_hash, utcnow
from tests.auth.conftest import post


def test_register_without_invite_code(env):
    """测试无邀请码注册"""
    client, factory, mail = env

    response = post(
        client,
        "/auth/register",
        {
            "email": "nocode@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 202
    assert "请求已受理" in response.json()["detail"]

    # 验证用户已创建，registration_method 为 'email'
    with factory() as db:
        user = db.query(User).filter(User.email == "nocode@example.com").first()
        assert user is not None
        assert user.registration_method == "email"
        assert user.invite_id is None


def test_register_with_invite_code(env):
    """测试有邀请码注册"""
    client, factory, mail = env

    # 创建邀请码
    with factory() as db:
        invite_id, raw_code = create_invite(db, max_uses=10, days=7)

    response = post(
        client,
        "/auth/register",
        {
            "email": "withcode@example.com",
            "password": "password123",
            "invite_code": raw_code,
        },
    )
    assert response.status_code == 202

    # 验证用户已创建，registration_method 为 'invite'
    with factory() as db:
        user = db.query(User).filter(User.email == "withcode@example.com").first()
        assert user is not None
        assert user.registration_method == "invite"
        assert user.invite_id == invite_id


def test_request_login_link(env):
    """测试请求登录链接"""
    client, factory, mail = env

    # 先创建并验证用户
    with factory() as db:
        user = User(
            email="magiclink@example.com",
            password_hash=password_hash("password123"),
            verified=True,
            pending_expires_at=utcnow(),
            registration_method="email",
        )
        db.add(user)
        db.commit()

    response = post(
        client,
        "/auth/request-login-link",
        {"email": "magiclink@example.com"},
    )
    assert response.status_code == 202
    assert "请求已受理" in response.json()["detail"]


def test_login_with_token(env):
    """测试用令牌登录"""
    client, factory, mail = env

    # 创建已验证用户
    with factory() as db:
        user = User(
            email="tokenlogin@example.com",
            password_hash=password_hash("password123"),
            verified=True,
            pending_expires_at=utcnow(),
            registration_method="email",
        )
        db.add(user)
        db.flush()

        # 生成登录令牌
        token = issue_token(db, user.id, "login")

    # 用令牌登录
    response = post(
        client,
        "/auth/login",
        {"token": token},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "tokenlogin@example.com"


def test_login_with_password_still_works(env):
    """测试密码登录仍然可用"""
    client, factory, mail = env

    # 创建已验证用户
    with factory() as db:
        user = User(
            email="pwdlogin@example.com",
            password_hash=password_hash("password123"),
            verified=True,
            pending_expires_at=utcnow(),
            registration_method="email",
        )
        db.add(user)
        db.commit()

    # 用密码登录
    response = post(
        client,
        "/auth/login",
        {
            "email": "pwdlogin@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "pwdlogin@example.com"


def test_login_with_expired_token_fails(env):
    """测试过期令牌登录失败"""
    client, factory, mail = env

    response = post(
        client,
        "/auth/login",
        {"token": "invalid_or_expired_token"},
    )
    assert response.status_code == 401
    assert "令牌无效" in response.json()["detail"]


def test_register_with_invalid_invite_code_fails(env):
    """测试无效邀请码注册失败"""
    client, factory, mail = env

    response = post(
        client,
        "/auth/register",
        {
            "email": "badcode@example.com",
            "password": "password123",
            "invite_code": "missing_invite_code_" + "x" * 32,
        },
    )
    # 应该返回 202，但后台任务会发现邀请码无效，不会创建用户
    assert response.status_code == 202

    # 验证用户未创建
    with factory() as db:
        user = db.query(User).filter(User.email == "badcode@example.com").first()
        assert user is None

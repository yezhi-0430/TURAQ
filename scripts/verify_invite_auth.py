"""
快速功能验证脚本

运行方式:
    python scripts/verify_invite_auth.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, create_tables
from app.auth.service import create_invite, register, issue_token, verify_email, password_hash, check_password
from app.watchlists.repository import create_watchlist, get_watchlists


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def verify_database():
    """验证数据库表创建"""
    print_section("1. Database Tables")
    try:
        create_tables()
        print("[PASS] Database tables created successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Database table creation failed: {e}")
        return False


def verify_invite_code_system():
    """验证邀请码系统"""
    print_section("2. Invite Code System")
    try:
        with SessionLocal() as db:
            # 生成邀请码
            invite_id1, code1 = create_invite(db)
            invite_id2, code2 = create_invite(db)
            db.commit()

            print(f"[PASS] Generated invite code 1: {code1}")
            print(f"[PASS] Generated invite code 2: {code2}")

            # 验证唯一性
            assert code1 != code2, "Invite codes should be unique"
            assert len(code1) > 0, "Invite code should not be empty"

            print("[PASS] Invite code uniqueness verified")
            return True, code1
    except Exception as e:
        print(f"[FAIL] Invite code system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def verify_registration(invite_code):
    """验证用户注册"""
    print_section("3. User Registration")
    try:
        with SessionLocal() as db:
            # 注册用户
            email = "test@turaq.com"
            password = "test123456"

            user = register(db, email, password, invite_code)
            db.commit()

            print(f"[PASS] User registration successful: {user.email}")
            print(f"       - ID: {user.id}")
            print(f"       - Verified: {user.verified}")
            print(f"       - Admin: {user.is_admin}")

            assert user.email == email
            assert user.verified is False  # 注册后未验证

            return True, user.id
    except Exception as e:
        print(f"[FAIL] User registration failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def verify_email_verification(user_id, invite_code):
    """验证邮箱验证流程"""
    print_section("4. Email Verification")
    try:
        with SessionLocal() as db:
            # 生成验证 token
            token = issue_token(db, user_id, "verify")
            db.commit()

            print(f"[PASS] Generated verification token: {token[:16]}...")

            # 验证邮箱
            verify_email(db, token, invite_code)
            db.commit()

            # 检查用户状态
            from app.auth.models import User
            user = db.get(User, user_id)

            print(f"[PASS] Email verification successful")
            print(f"       - Verified: {user.verified}")

            assert user.verified is True

            return True
    except Exception as e:
        print(f"[FAIL] Email verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_data_isolation():
    """验证数据隔离"""
    print_section("5. Data Isolation")
    try:
        with SessionLocal() as db:
            # 创建两个用户
            _, code1 = create_invite(db)
            _, code2 = create_invite(db)
            db.commit()

            user1 = register(db, "user1@turaq.com", "pass123456", code1)
            token1 = issue_token(db, user1.id, "verify")
            db.commit()
            verify_email(db, token1, code1)
            db.commit()

            user2 = register(db, "user2@turaq.com", "pass123456", code2)
            token2 = issue_token(db, user2.id, "verify")
            db.commit()
            verify_email(db, token2, code2)
            db.commit()

            print(f"[PASS] Created user 1: {user1.email} (ID: {user1.id})")
            print(f"[PASS] Created user 2: {user2.email} (ID: {user2.id})")

            # 用户 1 创建 watchlist
            wl1 = create_watchlist(db, "User1's Watchlist", actor_id=user1.id)
            db.commit()
            print(f"[PASS] User 1 created watchlist: {wl1.name} (ID: {wl1.id})")

            # 用户 2 创建 watchlist
            wl2 = create_watchlist(db, "User2's Watchlist", actor_id=user2.id)
            db.commit()
            print(f"[PASS] User 2 created watchlist: {wl2.name} (ID: {wl2.id})")

            # 验证隔离：用户 1 只能看到自己的
            user1_lists = get_watchlists(db, actor_id=user1.id)
            assert len(user1_lists) == 1
            assert user1_lists[0].id == wl1.id
            print(f"[PASS] User 1 can only see their own watchlist")

            # 验证隔离：用户 2 只能看到自己的
            user2_lists = get_watchlists(db, actor_id=user2.id)
            assert len(user2_lists) == 1
            assert user2_lists[0].id == wl2.id
            print(f"[PASS] User 2 can only see their own watchlist")

            print("[PASS] Data isolation verified")
            return True
    except Exception as e:
        print(f"[FAIL] Data isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_password_security():
    """验证密码安全"""
    print_section("6. Password Security")
    try:
        password = "testpass123"  # 改为符合 6-15 字符要求
        hash1 = password_hash(password)
        hash2 = password_hash(password)

        print(f"[PASS] Generated password hash 1: {hash1[:30]}...")
        print(f"[PASS] Generated password hash 2: {hash2[:30]}...")

        # 验证盐值不同
        assert hash1 != hash2, "Same password hashes should differ (salted)"
        print("[PASS] Password salting verified")

        # 验证正确密码
        assert check_password(hash1, password) is True
        assert check_password(hash2, password) is True
        print("[PASS] Password verification passed")

        # 验证错误密码
        assert check_password(hash1, "wrong_password") is False
        print("[PASS] Wrong password identification passed")

        return True
    except Exception as e:
        print(f"[FAIL] Password security test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*60)
    print("  TURAQ Invite Auth System - Verification")
    print("="*60)

    results = []

    # 1. 数据库
    results.append(("Database tables", verify_database()))

    # 2. 邀请码系统
    invite_ok, invite_code = verify_invite_code_system()
    results.append(("Invite code system", invite_ok))

    if not invite_ok:
        print("\n[FAIL] Invite code system failed, aborting further tests")
        return False

    # 3. 用户注册
    reg_ok, user_id = verify_registration(invite_code)
    results.append(("User registration", reg_ok))

    if not reg_ok:
        print("\n[FAIL] User registration failed, aborting further tests")
        return False

    # 4. 邮箱验证
    results.append(("Email verification", verify_email_verification(user_id, invite_code)))

    # 5. 数据隔离
    results.append(("Data isolation", verify_data_isolation()))

    # 6. 密码安全
    results.append(("Password security", verify_password_security()))

    # 总结
    print_section("Verification Summary")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"{status}  {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All verifications passed! System is ready.")
        return True
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed, please check logs.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

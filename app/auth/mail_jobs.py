"""Account-dependent mail work runs only after the public accepted response is sent."""

import logging

from sqlalchemy import select

from app.auth.models import User
from app.auth.service import aware, issue_token, register, utcnow

logger = logging.getLogger(__name__)


def process_mail_request(action, payload, factory, mailer):
    """Own the session in the background task; never retain a request-bound DB session.

    All accepted requests schedule this same job, including unknown/ineligible addresses.
    Delivery is best effort, not a durable queue or a claim that the recipient received mail.
    """
    try:
        with factory() as db:
            if action == "register":
                user = register(db, payload.email, payload.password, payload.invite_code)
                purpose = "verify"
            else:
                user = db.scalar(select(User).where(User.email == payload.email).with_for_update())
                purpose = "reset" if action == "forgot-password" else "verify"
                if user and (
                    user.disabled
                    or (purpose == "reset" and not user.verified)
                    or (
                        purpose == "verify"
                        and (user.verified or aware(user.pending_expires_at) <= utcnow())
                    )
                ):
                    user = None
            if user is None:
                return
            token = issue_token(db, user.id, purpose)
        mailer.send(payload.email, purpose, token)
    except Exception as exc:
        # No addresses, passwords, tokens, provider responses, SQL values or tracebacks.
        logger.warning("Authentication mail job failed (%s)", type(exc).__name__)

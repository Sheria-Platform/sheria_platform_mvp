# services/api/app/utils/email.py
"""Async email delivery utilities.

Wraps ``aiosmtplib`` with a fire-and-forget helper for sending the
account activation email after an admin approves a registration request.

Designed to be **non-blocking**: if ``SMTP_HOST`` is not configured, or
if the SMTP server is unreachable, a warning is logged and the caller
continues normally.  Email failure never propagates as an HTTP error.

Local development:
    Run MailHog to capture outgoing emails without a real SMTP server::

        docker run -p 1025:1025 -p 8025:8025 mailhog/mailhog

    Then set in ``.env``::

        SMTP_HOST=localhost
        SMTP_PORT=1025
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from services.api.app.config import settings

logger = logging.getLogger(__name__)


async def send_activation_email(
    to_address: str,
    full_name: str,
    activation_link: str,
) -> None:
    """Send the account activation email to a newly approved user.

    The full activation URL is constructed from ``settings.APP_BASE_URL``
    combined with the relative ``activation_link`` path.

    Both plain-text and HTML parts are attached so mail clients can
    choose the appropriate format.

    Args:
        to_address: Recipient email address (user's registered email).
        full_name: User's full name for the salutation.
        activation_link: Relative URL path, e.g. ``/activate?token=<uuid>``.

    Note:
        This function never raises.  All SMTP errors are caught and
        logged as warnings so callers (HTTP route handlers) are
        unaffected by mail delivery failures.
    """
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP_HOST not configured — skipping activation email to %s",
            to_address,
        )
        return

    full_link = f"{settings.APP_BASE_URL}{activation_link}"

    plain_body = (
        f"Dear {full_name},\n\n"
        f"Your Sheria Platform account has been approved by an administrator.\n\n"
        f"Please click the link below to set your password and activate your account:\n\n"
        f"  {full_link}\n\n"
        f"This link is single-use and will expire once your account is activated.\n"
        f"If you did not register, please ignore this email.\n\n"
        f"Regards,\nSheria Platform Administration"
    )

    html_body = f"""\
<html>
<body style="font-family: Georgia, serif; color: #222; max-width: 600px; margin: 0 auto;">
  <div style="background:#1a3a6b; padding:20px 24px;">
    <h1 style="color:#fff; margin:0; font-size:20px;">Sheria Platform</h1>
  </div>
  <div style="padding:28px 24px;">
    <p>Dear {full_name},</p>
    <p>Your Sheria Platform account has been <strong>approved</strong> by an administrator.</p>
    <p>Please click the button below to set your password and activate your account:</p>
    <p style="text-align:center; margin:32px 0;">
      <a href="{full_link}"
         style="background:#1a3a6b; color:#fff; text-decoration:none;
                padding:12px 28px; border-radius:6px; font-size:15px;">
        Activate Account
      </a>
    </p>
    <p style="font-size:13px; color:#666;">
      Or copy this link into your browser:<br>
      <a href="{full_link}" style="color:#1a3a6b;">{full_link}</a>
    </p>
    <p style="font-size:13px; color:#666;">
      This link is <strong>single-use</strong>.
      If you did not register, please ignore this email.
    </p>
  </div>
  <div style="background:#f5f5f5; padding:12px 24px; font-size:12px; color:#888;">
    Sheria Platform — Kenya Judiciary
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Sheria Platform — Activate Your Account"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_address
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            # STARTTLS on 587 (standard); MailHog on 1025 has no TLS
            start_tls=(settings.SMTP_PORT == 587),
            # Allow MailHog's self-signed cert without failing
            validate_certs=False,
        )
        logger.info("Activation email sent to %s", to_address)
    except Exception as exc:
        logger.warning("Failed to send activation email to %s: %s", to_address, exc)

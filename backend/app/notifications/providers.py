"""
Notification provider wrappers.

Provides thin wrappers around SMTP (email) and Twilio REST API (SMS).
Both functions return True on success and False on failure — they log
errors but never raise, so a failing notification never crashes a task.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Send an email via SMTP using Flask config values.

    Config keys used:
        MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS,
        MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER

    Returns
    -------
    bool
        True if the message was accepted by the SMTP server, False otherwise.
    """
    mail_server = current_app.config.get("MAIL_SERVER", "smtp.example.com")
    mail_port = int(current_app.config.get("MAIL_PORT", 587))
    use_tls = current_app.config.get("MAIL_USE_TLS", True)
    username = current_app.config.get("MAIL_USERNAME", "")
    password = current_app.config.get("MAIL_PASSWORD", "")
    sender = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(mail_server, mail_port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(sender, [to], msg.as_string())
        logger.info("send_email: delivered to %s subject=%r", to, subject)
        return True
    except smtplib.SMTPException as exc:
        logger.error("send_email: SMTP error sending to %s: %s", to, exc)
        return False
    except OSError as exc:
        logger.error("send_email: connection error sending to %s: %s", to, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("send_email: unexpected error sending to %s: %s", to, exc)
        return False


def send_sms(to: str, body: str) -> bool:
    """
    Send an SMS via the Twilio REST API.

    Config keys used:
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

    Parameters
    ----------
    to:
        Destination phone number in E.164 format (e.g. ``+254700000000``).
    body:
        Plain-text message body (max 1600 chars for Twilio).

    Returns
    -------
    bool
        True if Twilio accepted the message (HTTP 2xx), False otherwise.
    """
    account_sid = current_app.config.get("TWILIO_ACCOUNT_SID", "")
    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN", "")
    from_number = current_app.config.get("TWILIO_FROM_NUMBER", "")

    if not account_sid or not auth_token or not from_number:
        logger.error("send_sms: Twilio credentials are not configured")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {
        "From": from_number,
        "To": to,
        "Body": body,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            auth=(account_sid, auth_token),
            timeout=30,
        )
        response.raise_for_status()
        logger.info("send_sms: delivered to %s sid=%s", to, response.json().get("sid"))
        return True
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "send_sms: Twilio HTTP error for %s: %s — %s",
            to,
            exc,
            exc.response.text if exc.response is not None else "",
        )
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("send_sms: request error sending to %s: %s", to, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("send_sms: unexpected error sending to %s: %s", to, exc)
        return False

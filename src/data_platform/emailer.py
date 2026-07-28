"""
Email delivery for trade recommendations.

Uses Gmail SMTP (App Password required) or macOS built-in `mail` command
as fallback. Sends the formatted HTML recommendation to a specified address.

Setup for Gmail:
1. Go to https://myaccount.google.com/apppasswords
2. Generate an app password for "Mail"
3. Add to .env: GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

Usage:
    from data_platform.emailer import send_recommendation
    send_recommendation(html_content, subject="XOM — LONG | 4% NAV")
"""

from __future__ import annotations

import os
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from pathlib import Path


# Default config
DEFAULT_TO = "akashpandya1617@gmail.com"
DEFAULT_FROM = "agentic.trader.poc@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_recommendation(
    html_body: str,
    subject: str = "Trade Recommendation",
    to_email: str = DEFAULT_TO,
    plain_text: str = "",
) -> bool:
    """
    Send a trade recommendation via email.

    Tries Gmail SMTP first (requires GMAIL_APP_PASSWORD in env).
    Falls back to macOS `mail` command if SMTP fails.

    Args:
        html_body: HTML content of the email.
        subject: Email subject line.
        to_email: Recipient email address.
        plain_text: Optional plain text version.

    Returns:
        True if sent successfully, False otherwise.
    """
    # Try Gmail SMTP
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    from_email = os.environ.get("GMAIL_FROM", DEFAULT_FROM)

    if app_password:
        return _send_gmail_smtp(html_body, subject, to_email, from_email, app_password, plain_text)

    # Fallback: macOS mail command (sends from local machine)
    return _send_macos_mail(html_body, subject, to_email, plain_text)


def _send_gmail_smtp(
    html_body: str,
    subject: str,
    to_email: str,
    from_email: str,
    app_password: str,
    plain_text: str = "",
) -> bool:
    """Send via Gmail SMTP with app password."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Agentic Trader <{from_email}>"
        msg["To"] = to_email

        # Plain text fallback
        if plain_text:
            msg.attach(MIMEText(plain_text, "plain"))

        # HTML version
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())

        print(f"[EMAIL] Sent to {to_email} via Gmail SMTP")
        return True

    except Exception as e:
        print(f"[EMAIL] Gmail SMTP failed: {e}")
        return False


def _send_macos_mail(
    html_body: str,
    subject: str,
    to_email: str,
    plain_text: str = "",
) -> bool:
    """Fallback: send via macOS mail command."""
    try:
        # Write HTML to temp file
        tmp = Path("/tmp/trade_recommendation.html")
        tmp.write_text(html_body)

        # Use osascript to send via Mail.app
        script = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"{subject}", content:"{plain_text or 'See HTML attachment'}", visible:false}}
            tell newMessage
                make new to recipient with properties {{address:"{to_email}"}}
                make new attachment with properties {{file name:POSIX file "/tmp/trade_recommendation.html"}}
            end tell
            send newMessage
        end tell
        '''

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )

        if result.returncode == 0:
            print(f"[EMAIL] Sent to {to_email} via macOS Mail")
            return True
        else:
            # Last resort: just use the `mail` command with plain text
            if plain_text:
                proc = subprocess.run(
                    ["mail", "-s", subject, to_email],
                    input=plain_text, capture_output=True, text=True, timeout=10,
                )
                if proc.returncode == 0:
                    print(f"[EMAIL] Sent to {to_email} via mail command")
                    return True

            print(f"[EMAIL] macOS mail failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"[EMAIL] Fallback failed: {e}")
        return False


def send_cycle_report(
    html_body: str,
    plain_text: str,
    ticker: str = "",
    direction: str = "",
    to_email: str = DEFAULT_TO,
) -> bool:
    """
    Send end-of-cycle report. Builds a descriptive subject line.
    """
    today = date.today().isoformat()

    if ticker and direction:
        subject = f"[TRADE] {ticker} — {direction.upper()} | {today}"
    else:
        subject = f"[NO TRADE] Cycle Complete | {today}"

    return send_recommendation(html_body, subject, to_email, plain_text)

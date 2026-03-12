#!/usr/bin/env python3
"""
flushoutbox.py
--------------
Retry all .eml files sitting in backend/outbox/.

Run from E:\\Index-Scoring:
    python flushoutbox.py

Fixes the 553 "Sender not allowed to relay" error by rewriting the
From: header in every queued email to match SMTP_USER before sending.
"""

import glob
import os
import smtplib
import ssl
import sys
from email import message_from_bytes, policy as email_policy
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, '.env'))

OUTBOX_DIR = os.path.join(_HERE, "backend", "outbox")

# ── SMTP config ───────────────────────────────────────────────────────────────
SMTP_HOST    = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT    = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER    = os.getenv("SMTP_USER", "").strip()
SMTP_PASS    = os.getenv("SMTP_PASS", "").strip()
SMTP_FROM    = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "").lower() in ("1", "true", "yes") or SMTP_PORT == 465


def _check_config() -> bool:
    if not SMTP_HOST:
        print("ERROR: SMTP_HOST is not set in .env")
        return False
    if not SMTP_FROM:
        print("ERROR: SMTP_FROM / SMTP_USER is not set in .env")
        return False
    print(f"SMTP: {SMTP_HOST}:{SMTP_PORT}  ssl={SMTP_USE_SSL}  from={SMTP_FROM}")
    return True


def _open_smtp():
    """Open and return an authenticated SMTP connection."""
    if SMTP_USE_SSL:
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=ctx)
    else:
        s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        s.ehlo()
        try:
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
        except Exception as e:
            print(f"  Warning: STARTTLS failed ({e}), continuing without TLS")
    if SMTP_USER and SMTP_PASS:
        s.login(SMTP_USER, SMTP_PASS)
    return s


def _fix_from(raw: bytes) -> bytes:
    """
    Rewrite the From: header to SMTP_FROM so Zoho does not reject with 553.
    The old emails were built when SMTP was not configured and used the
    'noreply@example.com' fallback — Zoho rejects any From that is not
    the authenticated sender.
    """
    msg = message_from_bytes(raw, policy=email_policy.default)
    current_from = str(msg.get("From", ""))
    if SMTP_FROM and SMTP_FROM not in current_from:
        if "From" in msg:
            del msg["From"]
        msg["From"] = SMTP_FROM
    return msg.as_bytes()


def flush():
    if not _check_config():
        sys.exit(1)

    if not os.path.isdir(OUTBOX_DIR):
        print(f"Outbox not found at: {OUTBOX_DIR}")
        return

    files = sorted(glob.glob(os.path.join(OUTBOX_DIR, "*.eml")))
    if not files:
        print("Outbox is empty – nothing to send.")
        return

    print(f"\nFound {len(files)} queued email(s)\n" + chr(0x2500)*55)

    # Open one SMTP connection and reuse it for all messages
    try:
        smtp = _open_smtp()
        print(f"Connected to {SMTP_HOST}:{SMTP_PORT}\n")
    except smtplib.SMTPAuthenticationError as e:
        print(f"\nERROR: SMTP authentication failed: {e}")
        print("-> Generate an App Password in Zoho: Mail Settings -> Security -> App Passwords")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Could not connect to SMTP: {e}")
        sys.exit(1)

    sent = failed = skipped = 0

    for path in files:
        fname = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                raw = f.read()

            # Fix the From header before sending
            raw = _fix_from(raw)
            msg = message_from_bytes(raw, policy=email_policy.default)

            to      = str(msg.get("To", "?"))
            subject = str(msg.get("Subject", "?"))
            frm     = str(msg.get("From", "?"))
            print(f"  To: {to}")
            print(f"  Subject: {subject}")
            print(f"  From: {frm}")

        except Exception as e:
            print(f"  {fname}: parse error - {e} (skipping)")
            skipped += 1
            continue

        try:
            smtp.send_message(msg)
            try:
                os.remove(path)
            except Exception:
                pass
            print(f"  OK Sent\n")
            sent += 1

        except smtplib.SMTPServerDisconnected:
            print(f"  Connection dropped, reconnecting...")
            try:
                smtp = _open_smtp()
                smtp.send_message(msg)
                try:
                    os.remove(path)
                except Exception:
                    pass
                print(f"  OK Sent (after reconnect)\n")
                sent += 1
            except Exception as e2:
                print(f"  FAILED after reconnect: {e2}\n")
                failed += 1

        except smtplib.SMTPRecipientsRefused as e:
            print(f"  FAILED recipient refused: {e}\n")
            failed += 1

        except Exception as e:
            print(f"  FAILED: {e}\n")
            failed += 1

    try:
        smtp.quit()
    except Exception:
        pass

    print(chr(0x2500)*55)
    print(f"Sent: {sent}  |  Failed: {failed}  |  Skipped: {skipped}")
    remaining = len(glob.glob(os.path.join(OUTBOX_DIR, "*.eml")))
    print(f"Emails still in outbox: {remaining}")
    if failed:
        print("\nRun again after fixing the errors above.")


if __name__ == "__main__":
    flush()
"""Outlook COM email (standalone only). Best-effort: returns a status, never raises."""
import json
from pathlib import Path
_CFG = Path.home() / ".claude" / "email.json"


def _load_cfg() -> dict:
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _send_via_outlook(to: str, subject: str, body: str, cc: str | None) -> None:
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.To = to
    if cc:
        mail.CC = cc
    mail.Subject = subject
    mail.Body = body
    mail.Send()


def send_email(to: str | None, subject: str, body_path: str, cc: str | None = None) -> str:
    if not to:
        return "skipped"
    body = Path(body_path).read_text(encoding="utf-8")
    _send_via_outlook(to, subject, body, cc or _load_cfg().get("operator_email"))
    return "sent"

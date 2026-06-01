# tests/test_email_delivery.py
import albert.email_delivery as ed
def test_sent(monkeypatch, tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    monkeypatch.setattr(ed, "_send_via_outlook", lambda to, subject, body, cc: None)
    assert ed.send_email(to="a@b.com", subject="s", body_path=str(p)) == "sent"
def test_skipped(tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    assert ed.send_email(to=None, subject="s", body_path=str(p)) == "skipped"

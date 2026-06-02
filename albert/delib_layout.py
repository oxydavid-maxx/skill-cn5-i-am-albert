# albert/delib_layout.py
"""Pure plain-text card-layout primitives for the deliberation transcript.

No Markdown control characters (#, *) — only box-drawing + plain text — so the
output reads cleanly in BOTH the live terminal stream and deliberation.md.
Deterministic; no I/O.
"""

BOX_W = 60

_SEV = {"high": "高", "medium": "中", "low": "低", "none": "無", "unknown": "未知"}
_STR = {"weak": "弱", "medium": "中", "strong": "強"}
_CLS = {"addressable": "可解決", "residual": "殘留"}


def sev_zh(x) -> str:
    return _SEV.get(str(x), str(x))


def strength_zh(x) -> str:
    return _STR.get(str(x), str(x))


def cls_zh(x) -> str:
    return _CLS.get(str(x), str(x))


def header(title: str) -> str:
    bar = "═" * BOX_W
    return f"{bar}\n  {title}\n{bar}"


def section(label: str) -> str:
    return f"▍{label}"


def kv(label: str, value: str) -> str:
    return f"{label}:{value}"


def bullet(text: str, indent: int = 0) -> str:
    return (" " * indent) + f"· {text}"


def truncate(text, n: int = 100) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n].rstrip() + "…"


def card(index: int, total: int, meta: str, lines: list) -> str:
    top = f"┌─ [{index}/{total}]  {meta}"
    body = "\n".join(f"│  {ln}" for ln in lines)
    bot = "└" + "─" * (BOX_W - 1)
    return f"{top}\n{body}\n{bot}"

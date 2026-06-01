"""File ops, slug generation, prompt loading."""
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def sluggify(text: str, max_len: int = 60) -> str:
    """Convert text to URL-safe slug."""
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:max_len]


def load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ directory.

    Strips trailing whitespace — a trailing '\\n' on system prompts passed
    to claude -p --json-schema silently flips Claude out of schema-mode
    into prose-mode (empirical, reproducible). Always strip.
    """
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").rstrip()


def safe_read_text(path: Path) -> str:
    """Read a file; return empty string if missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

# tests/test_delib_layout.py
from albert import delib_layout as L


def test_header_has_bar_and_title_no_markdown():
    h = L.header("PHASE 2 ─ 生成拷問")
    assert "═" in h
    assert "PHASE 2 ─ 生成拷問" in h
    assert "#" not in h and "*" not in h


def test_section_marker():
    assert L.section("拷問(共 10 條)") == "▍拷問(共 10 條)"


def test_card_structure():
    c = L.card(1, 10, "骨#2 · 嚴重度:高 · 現答:弱", ["拷問:X 在成長嗎?", "為何問:慢性失血"])
    assert "┌─ [1/10]" in c
    assert "骨#2 · 嚴重度:高 · 現答:弱" in c
    assert "│  拷問:X 在成長嗎?" in c
    assert "│  為何問:慢性失血" in c
    assert "└─" in c
    assert "#" not in c.replace("骨#2", "") and "*" not in c  # no markdown control chars


def test_kv_and_bullet():
    assert L.kv("提前結束風險", "高 — 6 條未解") == "提前結束風險:高 — 6 條未解"
    assert L.bullet("重點") == "· 重點"
    assert L.bullet("縮排", indent=3) == "   · 縮排"


def test_truncate_collapses_and_caps():
    assert L.truncate("a\n  b   c", 100) == "a b c"
    out = L.truncate("x" * 200, 90)
    assert len(out) <= 91 and out.endswith("…")


def test_zh_label_maps():
    assert L.sev_zh("high") == "高" and L.sev_zh("low") == "低" and L.sev_zh("medium") == "中"
    assert L.strength_zh("weak") == "弱" and L.strength_zh("strong") == "強"
    assert L.cls_zh("addressable") == "可解決" and L.cls_zh("residual") == "殘留"
    assert L.sev_zh("unknown") == "未知"

"""CLI entry point for the Albert Thought Agent FSM."""
import argparse, os, shutil, sys, time, uuid
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from albert import deliberation
from albert.graph import build_graph
from albert.input_adapter import build_input
from albert.profile import resolve_profile, apply_profile

RUNS_DIR = Path(__file__).parent / "runs"
RETENTION_DAYS = 30


def _apply_standalone_rework_default(mode, env):
    """Standalone runs are interactive — default to one rework pass unless the
    caller set ALBERT_MAX_REWORK explicitly. Cockpit mode keeps the graph default (2)."""
    if mode == "standalone" and "ALBERT_MAX_REWORK" not in env:
        env["ALBERT_MAX_REWORK"] = "1"


def _force_utf8_console(streams):
    """Make CJK deliberation cards render cleanly + live on any machine, no env setup.
    errors='replace' so a console that can't encode a glyph degrades it to '?' rather
    than raising UnicodeEncodeError (which would fail the visibility contract)."""
    for s in streams:
        try:
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


def _deliberation_banner(run_dir, profile="thorough") -> str:
    return ("\n▼▼▼ 辯論過程(即時顯示)▼▼▼\n"
            f"（模式:{profile} · 完整存檔:{Path(run_dir) / 'deliberation.md'}）\n")


def _isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _redirect_refusal(*, is_cockpit, allow_redirect, dry_run, streams):
    """Return a refusal message if a standalone run's live deliberation would be hidden
    (output not on an interactive terminal), else None. Cockpit / --allow-redirect /
    --dry-run are exempt; otherwise ALL streams must be TTYs."""
    if is_cockpit or allow_redirect or dry_run:
        return None
    if all(_isatty(s) for s in streams):
        return None
    return (
        "Albert 拒絕執行:辯論過程必須即時顯示在終端機,但偵測到輸出被導走"
        "(pipe / > 檔案 / 2>&1 | tee / 背景執行)。\n"
        "請直接在終端機跑:  py -3 run_albert.py \"<你的提案>\"\n"
        "(別加 | tee、> 檔案、2>&1 |、或丟背景。完整存檔仍會在 runs/<id>/deliberation.md。)\n"
        "若確實需要非互動執行,加 --allow-redirect。"
    )


def main():
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    _force_utf8_console((sys.stdout, sys.stderr))
    ap = argparse.ArgumentParser(prog="run_albert")
    ap.add_argument("proposal", nargs="?")
    ap.add_argument("--input", dest="input_json")
    ap.add_argument("--json-out", action="store_true")
    ap.add_argument("--resume", dest="resume_id")
    ap.add_argument("--gc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-redirect", action="store_true")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--flash", action="store_true")
    ap.add_argument("--user-email")
    args = ap.parse_args()
    if args.gc:
        _gc(); return 0
    if args.flash:
        profile = "flash"
    elif args.quick:
        profile = "quick"
    else:
        profile = resolve_profile(args.fast, os.environ)
    _extra = [n for n, on in (("--flash", args.flash), ("--quick", args.quick), ("--fast", args.fast)) if on]
    if len(_extra) > 1:
        sys.stderr.write(f"[profile] multiple given {_extra}; using {profile}\n")
    _applied = apply_profile(profile, os.environ)
    if profile in ("fast", "quick", "flash"):
        sys.stderr.write(f"[profile] {profile} — {', '.join(f'{k}={v}' for k, v in _applied.items()) or '(all pre-set)'}\n")
    if not args.proposal and not args.input_json and not args.resume_id:
        ap.error("a proposal, --input, or --resume is required")
    is_cockpit = bool(args.input_json or args.json_out)
    allow_redirect = bool(args.allow_redirect) or os.environ.get("ALBERT_ALLOW_REDIRECT") == "1"
    _refusal = _redirect_refusal(is_cockpit=is_cockpit, allow_redirect=allow_redirect,
                                 dry_run=args.dry_run, streams=(sys.stdout, sys.stderr))
    if _refusal:
        sys.stderr.write(_refusal + "\n")
        return 2
    run_id = args.resume_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        print(f"Would invoke Albert with run_id={run_id}"); return 0
    from albert import progress as _p
    _p.init(run_dir)
    deliberation.init(run_dir)
    sys.stderr.write(_deliberation_banner(run_dir, profile))
    sys.stderr.flush()
    try:
        from albert import heartbeat as _hb
        _hb.start(run_dir, run_id)
    except Exception as e:
        sys.stderr.write(f"[run_albert] WARN heartbeat: {e}\n")
    with SqliteSaver.from_conn_string(str(run_dir / "checkpoint.db")) as cp:
        graph = build_graph(checkpointer=cp)
        config = {"configurable": {"thread_id": run_id, "recursion_limit": 100}}
        if args.resume_id:
            initial = None
        else:
            ai = build_input(raw_text=args.proposal, input_json=args.input_json)
            _apply_standalone_rework_default(ai["mode"], os.environ)
            initial = {"albert_input": ai, "mode": ai["mode"], "run_id": run_id,
                       "run_dir": str(run_dir), "user_email": args.user_email,
                       "profile": profile}
        try:
            final = graph.invoke(initial, config=config)
        except Exception as exc:
            sys.stderr.write(f"[Albert] Run failed: {type(exc).__name__}: {str(exc)[:300]}\n"); return 1
    if not final.get("phase_5_complete"):
        sys.stderr.write(f"Run incomplete. Inspect {run_dir}\n"); return 2
    if args.json_out:
        print(final.get("challenge_json_path", ""))
    else:
        sys.stderr.write(f"[Albert] verdict={final.get('verdict')} next={final.get('recommended_next_action')} "
                         f"premature_end={final.get('premature_end_risk',{}).get('level')} "
                         f"standalone={final.get('verdict_standalone')}({final.get('light')})\n")
        print(final.get("report_path", ""))
    print(f"\n📄 報告:{final.get('report_path', run_dir / 'albert_review.md')}")
    print(f"💬 辯論全文:{run_dir / 'deliberation.md'}")
    return 0


def _gc():
    cutoff = time.time() - RETENTION_DAYS * 86400
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

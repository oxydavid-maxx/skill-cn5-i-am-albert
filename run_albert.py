"""CLI entry point for the Albert Thought Agent FSM."""
import argparse, os, shutil, sys, time, uuid
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from albert import deliberation
from albert.graph import build_graph
from albert.input_adapter import build_input

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


def _deliberation_banner(run_dir) -> str:
    return ("\n▼▼▼ 辯論過程(即時顯示)▼▼▼\n"
            f"（完整存檔:{Path(run_dir) / 'deliberation.md'}）\n")


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
    ap.add_argument("--user-email")
    args = ap.parse_args()
    if args.gc:
        _gc(); return 0
    if not args.proposal and not args.input_json and not args.resume_id:
        ap.error("a proposal, --input, or --resume is required")
    run_id = args.resume_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        print(f"Would invoke Albert with run_id={run_id}"); return 0
    from albert import progress as _p
    _p.init(run_dir)
    deliberation.init(run_dir)
    sys.stderr.write(_deliberation_banner(run_dir))
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
                       "run_dir": str(run_dir), "user_email": args.user_email}
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

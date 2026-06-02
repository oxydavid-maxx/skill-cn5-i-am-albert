#!/usr/bin/env bash
# Sync this skill's committed HEAD into the CN5DD2_common Gerrit repo
# (canonical files under skills/skill-cn5-i-am-albert/ + the cn5dd2-base
# plugin symlink) and push DIRECTLY to master (refs/heads/master).
# Per user 2026-06-02: "直接 push, 不要 submit" — land on master, no review.
#
# Invoked automatically by .git/hooks/pre-push (best-effort: a failure here
# never blocks the GitHub push). Can also be run manually:  bash tools/sync-to-gerrit.sh
#
# Rule (user 2026-06-02): "以後這個 skill 的 gitpush 都要同步 gerrit push."
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CN5="/d/D-claude/cn5dd2/CN5DD2_common"
NAME="skill-cn5-i-am-albert"
LINK="plugins/cn5dd2-base/skills/$NAME"
DEST="skills/$NAME"

[ -d "$CN5/.git" ] || { echo "[sync] CN5DD2_common not at $CN5 — skip"; exit 0; }
cd "$CN5"

git fetch -q origin

# Refuse to entangle unrelated local changes: bail if anything outside the
# skill's own paths is dirty.
if git status --porcelain | grep -vqE "(^.. )?($DEST|$LINK)"; then
  echo "[sync] CN5DD2_common has unrelated local changes — aborting auto-sync." >&2
  exit 1
fi

git checkout -q master
git merge -q --ff-only origin/master || { echo "[sync] master diverged from origin/master — resolve manually." >&2; exit 1; }

# Refresh canonical files from the skill's committed HEAD (tracked files only).
rm -rf "$DEST"; mkdir -p "$DEST"
git -C "$SKILL_DIR" archive HEAD | tar -x -C "$DEST"

# Ensure the plugin symlink (git mode 120000) exists (Windows core.symlinks=false safe).
if [ "$(git ls-files -s "$LINK" 2>/dev/null | awk '{print $1}')" != "120000" ]; then
  blob=$(printf '../../../skills/%s' "$NAME" | git hash-object -w --stdin)
  git update-index --add --cacheinfo 120000,"$blob","$LINK"
fi

git add "$DEST"
if git diff --cached --quiet; then
  echo "[sync] no skill changes — nothing to push to Gerrit."
  exit 0
fi

SHA=$(git -C "$SKILL_DIR" rev-parse --short HEAD)
git -c commit.gpgsign=false commit -q -m "chore(cn5dd2-base): sync $NAME @ $SHA"
# Direct push to master (FF base ensured above) — no Gerrit review, per user pref.
git push --dry-run origin HEAD:refs/heads/master >/dev/null 2>&1 || { echo "[sync] dry-run rejected for refs/heads/master — aborting." >&2; exit 1; }
git push origin HEAD:refs/heads/master
echo "[sync] synced $NAME @ $SHA → Gerrit master (direct)"

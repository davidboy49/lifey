#!/usr/bin/env bash
# Pull-based auto deploy: run by lifey-autodeploy.timer as root. If origin/main has moved and its CI
# run finished green, run deploy.sh. Nothing is deployed from a red or still-running CI.
# No GitHub token and no inbound access needed (the repo is public).
#
# A merge that adds or changes a database migration is held: the API runs `alembic upgrade` on start,
# which is hard to undo on real data. Review it, then run `sudo deploy/auto-deploy.sh --approve`.
set -euo pipefail
cd "$(dirname "$0")/.."
approve=0; [ "${1:-}" = "--approve" ] && approve=1
state=/var/lib/lifey-autodeploy; mkdir -p "$state"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$PWD"

git fetch -q origin main
head="$(git rev-parse HEAD)"
remote="$(git rev-parse origin/main)"
[ "$head" = "$remote" ] && exit 0
# Only fast-forwards: a local checkout that diverged is left alone for a human.
git merge-base --is-ancestor "$head" "$remote" || { echo "HEAD is not behind origin/main, not deploying" >&2; exit 1; }

repo="$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
conclusion="$(curl -fsS "https://api.github.com/repos/$repo/actions/workflows/ci.yml/runs?head_sha=$remote&event=push&per_page=1" \
  | python3 -c 'import json,sys; r=json.load(sys.stdin)["workflow_runs"]; print(r[0]["conclusion"] or "running" if r else "none")')"
case "$conclusion" in
  success) ;;
  none|running) echo "CI for ${remote:0:7} not finished ($conclusion), will retry"; exit 0 ;;
  *) echo "CI for ${remote:0:7} is $conclusion, not deploying" >&2; exit 1 ;;
esac

migrations="$(git diff --name-only "$head" "$remote" -- api/migrations)"
if [ -n "$migrations" ] && [ "$approve" = 0 ]; then
  if [ "$(cat "$state/held" 2>/dev/null)" != "$remote" ]; then
    echo "HELD ${remote:0:7}: it changes database migrations, not deploying until approved:"
    echo "$migrations"
    echo "Review, then run: sudo /opt/lifey/deploy/auto-deploy.sh --approve"
    echo "$remote" > "$state/held"
  fi
  exit 0
fi
rm -f "$state/held"

echo "Deploying ${remote:0:7} (was ${head:0:7})"
exec ./deploy/deploy.sh

#!/usr/bin/env bash
# Pull-based auto deploy: run by lifey-autodeploy.timer as root. If origin/main has moved and its CI
# run finished green, run deploy.sh. Nothing is deployed from a red or still-running CI.
# No GitHub token and no inbound access needed (the repo is public).
set -euo pipefail
cd "$(dirname "$0")/.."
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

echo "Deploying ${remote:0:7} (was ${head:0:7})"
exec ./deploy/deploy.sh

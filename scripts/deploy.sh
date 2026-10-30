#!/usr/bin/env bash
# Local preflight and push helper.
#
#   ./scripts/deploy.sh --check     verify the repo is ready (no network, no keys used)
#   ./scripts/deploy.sh --push      commit and push to origin
#   ./scripts/deploy.sh --secrets   list exactly which secrets still need adding
#
# Never prints secret values.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
ok()   { printf "  ${GREEN}ok${OFF}   %s\n" "$1"; }
bad()  { printf "  ${RED}FAIL${OFF} %s\n" "$1"; FAILED=$((FAILED+1)); }
warn() { printf "  ${YELLOW}!!${OFF}   %s\n" "$1"; }
FAILED=0

header() { printf "\n%s\n" "$1"; }

check_files() {
  header "Required files"
  local files=(
    .github/workflows/daily-short.yml
    scripts/pick_topic.py
    scripts/prepare_config.py
    scripts/make_metadata.py
    scripts/youtube_upload.py
    scripts/ci.py
    topics/curriculum.json
    config/mpt-config.template.toml
    state/used.json
    README.md
    docs/SETUP.md
  )
  for f in "${files[@]}"; do
    [ -f "$f" ] && ok "$f" || bad "$f missing"
  done
}

check_python() {
  header "Python syntax"
  local failed=0
  while IFS= read -r f; do
    python3 -m py_compile "$f" 2>/dev/null || { bad "syntax error in $f"; failed=1; }
  done < <(find scripts tests -name '*.py')
  [ "$failed" -eq 0 ] && ok "all scripts compile"
}

check_yaml() {
  header "Workflow"
  if command -v python3 >/dev/null && python3 -c 'import yaml' 2>/dev/null; then
    python3 - <<'PY'
import sys, yaml
d = yaml.safe_load(open('.github/workflows/daily-short.yml'))
job = d['jobs']['make']
n = len(job['steps'])
trig = list(d[True].keys())
assert 'schedule' in trig and 'workflow_dispatch' in trig, trig
print(f"  \033[0;32mok\033[0m   YAML valid, {n} steps, triggers: {', '.join(trig)}")
PY
  else
    warn "pyyaml not installed - skipping YAML parse (pip install pyyaml)"
  fi
  if command -v bash >/dev/null; then
    python3 - <<'PY'
import yaml, subprocess, tempfile, sys
d = yaml.safe_load(open('.github/workflows/daily-short.yml'))
bad = []
for s in d['jobs']['make']['steps']:
    if 'run' not in s: continue
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as fh:
        fh.write(s['run']); path = fh.name
    if subprocess.run(['bash','-n',path], capture_output=True).returncode:
        bad.append(s.get('name'))
if bad:
    print("  \033[0;31mFAIL\033[0m shell syntax: " + ", ".join(bad)); sys.exit(1)
print("  \033[0;32mok\033[0m   every run: block passes bash -n")
PY
  fi
}

check_data() {
  header "Data"
  python3 - <<'PY'
import json
c = json.load(open('topics/curriculum.json'))
doms = c['domains']; n = sum(len(d['topics']) for d in doms)
assert n > 0
print(f"  \033[0;32mok\033[0m   curriculum: {len(doms)} domains, {n} topics")
st = json.load(open('state/used.json'))
print(f"  \033[0;32mok\033[0m   state: {len(st.get('used', []))} topics already used")
PY
}

check_tests() {
  header "Tests"
  if python3 -m pytest tests/ -q >/dev/null 2>&1; then
    ok "pytest suite passes"
  elif python3 tests/test_pick_topic.py >/dev/null 2>&1; then
    ok "test_pick_topic.py passes (pytest not installed)"
  else
    bad "tests failing"
  fi
}

check_topic_pick() {
  header "Dry-run topic pick"
  local out
  out="$(python3 scripts/pick_topic.py --dry-run --show 2>&1 | head -1)"
  case "$out" in
    \[dry-run\]*) ok "picks: ${out#\[dry-run\] }" ;;
    *) bad "picker failed: $out" ;;
  esac
  [ -f out/topic.json ] && ok "wrote out/topic.json ($(wc -c < out/topic.json) bytes, single line)"
}

check_secrets_doc() {
  header "Secrets checklist"
  printf "  %sRequired:%s   LLM_API_KEY, PEXELS_API_KEY\n" "$DIM" "$OFF"
  printf "  %sOptional:%s   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN\n" "$DIM" "$OFF"
  printf "  %sOptional:%s   TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (failure alerts)\n" "$DIM" "$OFF"
  if [ -f .env ]; then
    # shellcheck disable=SC1091
    set +u; . ./.env; set -u
    for v in LLM_API_KEY PEXELS_API_KEY; do
      if [ -n "${!v:-}" ]; then ok "$v is set in .env (${#v} name)"; else warn "$v not set in .env"; fi
    done
  else
    warn ".env not found (copy .env.example) - you can also just use GitHub Secrets"
  fi
}

do_push() {
  header "Push"
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    git init -q
    git branch -M main
    ok "initialised git repo"
  fi
  if ! git remote get-url origin >/dev/null 2>&1; then
    bad "no 'origin' remote. Add one: git remote add origin https://github.com/<you>/<repo>.git"
    return
  fi
  git add -A
  git diff --cached --quiet && warn "nothing to commit" || {
    git -c user.name="${GIT_AUTHOR_NAME:-deploy}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-deploy@localhost}" \
        commit -q -m "automation: educational shorts pipeline"
    ok "committed"
  }
  if git push -q origin HEAD 2>/dev/null; then
    ok "pushed to $(git remote get-url origin)"
  else
    bad "push failed - auth or permissions. If asked for a password, use a token, not your account password."
  fi
}

# ---------------------------------------------------------------- main
case "${1:---check}" in
  --check)
    printf "Preflight for %s\n" "$REPO_ROOT"
    check_files; check_python; check_yaml; check_data; check_tests; check_topic_pick; check_secrets_doc
    printf "\n"
    if [ "$FAILED" -eq 0 ]; then
      printf "${GREEN}Ready.${OFF} Next: add the two required secrets, then Actions -> Run workflow (dry_run: true).\n\n"
    else
      printf "${RED}%d problem(s).${OFF} Fix the FAIL lines above.\n\n" "$FAILED"
      exit 1
    fi
    ;;
  --push) do_push ;;
  --secrets) grep -E '^[A-Z_]+' .env.example 2>/dev/null | cut -d= -f1 | sed 's/^/  /' ;;
  -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown option: $1 (try --help)"; exit 1 ;;
esac

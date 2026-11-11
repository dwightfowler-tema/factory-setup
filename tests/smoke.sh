#!/usr/bin/env bash
# Exercises the deterministic script against a throwaway repo (no gh, no network).
set -euo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
S="python3 $SKILL/scripts/factory_setup.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

# 1. INSTALL.md exists and SKILL.md tells the session to read it
[ -f "$SKILL/INSTALL.md" ] || fail "INSTALL.md missing"
grep -q 'INSTALL.md' "$SKILL/SKILL.md" || fail "SKILL.md must reference INSTALL.md"
grep -q 'INSTALL.md' "$SKILL/payload/factory/checks.sh" || fail "checks.sh comment should name INSTALL.md"

cd "$T" && git init -q -b main . && git config user.email t@t && git config user.name t
printf 'print("hi")\n' > app.py; git add -A; git commit -qm init

# fake gh that records label creation and lists none, so labels can be tested offline
mkdir "$T/bin"; cat > "$T/bin/gh" <<'GH'
#!/usr/bin/env bash
if [ "$1 $2" = "label list" ]; then echo '[]'; exit 0; fi
if [ "$1 $2" = "label create" ]; then echo "$3" >> "$GH_LOG"; exit 0; fi
exit 1
GH
chmod +x "$T/bin/gh"; export GH_LOG="$T/gh.log" PATH="$T/bin:$PATH"

# 2. --help works anywhere, runs nothing; unknown flags are errors; labels is a dry run until --yes
$S --help | grep -q 'labels' || fail "top-level help lists commands"
$S labels --help | grep -q -- '--yes' || fail "labels --help prints usage"
[ ! -e "$GH_LOG" ] || fail "labels --help created labels"
$S labels | grep -q 'DRY RUN' || fail "labels default is a dry run"
[ ! -e "$GH_LOG" ] || fail "dry run created labels"
$S labels --bogus 2>/dev/null && fail "unknown flag should be an error"
$S labels --yes >/dev/null; [ "$(wc -l < "$GH_LOG")" = 3 ] || fail "labels --yes should create 3"

$S copy >/dev/null
[ -x factory/bin/job ] && [ -x factory/checks.sh ] || fail "exec bits"
[ "$(cat factory/VERSION)" = "$(cat "$SKILL/VERSION")" ] || fail "VERSION stamp"
$S copy 2>/dev/null && fail "second copy should refuse"
$S gitignore >/dev/null; $S gitignore | grep -q nothing || fail "gitignore not idempotent"
git check-ignore factory/jobs/x .worktrees/x >/dev/null || fail "ignore lines"
$S agents-md >/dev/null; $S agents-md | grep -q already || fail "agents-md not idempotent"
grep -q '## Software factory' AGENTS.md || fail "agents section"

# 3. config get/set
$S config get ports.base | grep -q 5100 || fail "config get"
$S config set ports.base 5200 | grep -q '5100 -> 5200' || fail "config set prints old -> new"
[ "$($S config get ports.base)" = 5200 ] || fail "typed value stored as number"
$S config set merge_method squash >/dev/null; [ "$($S config get merge_method)" = '"squash"' ] || fail "string value"
$S config set routing.medium.code opus >/dev/null || fail "nested key"
$S config set nope.key 1 2>/dev/null && fail "unknown key should be rejected"
$S config set typo 1 2>/dev/null && fail "unknown top-level key should be rejected"
$S config set typo 1 --add >/dev/null || fail "--add should create"
cp factory/config.json "$T/before.json"
echo '{bad' > factory/config.json; $S config get ports.base 2>/dev/null && fail "invalid JSON should error"
[ "$(cat factory/config.json)" = '{bad' ] || fail "invalid config must be left untouched"
cp "$T/before.json" factory/config.json
python3 -c "import json;json.load(open('factory/config.json'))" || fail "config still valid JSON"

# 4a. dirty tree: only TRACKED changes warn/refuse; untracked files are just a NOTE
out="$($S preflight 2>/dev/null || true)"
echo "$out" | grep -q 'NOTE  .*untracked' || fail "preflight should NOTE untracked files"
echo "$out" | grep -q 'WARN  working tree has' && fail "untracked files alone must not WARN"
out="$($S verify-checks 2>&1 || true)"
echo "$out" | grep -q 'refusing' && fail "untracked files alone must not make verify-checks refuse"
echo "$out" | grep -q 'untracked file' || fail "verify-checks should note untracked files"
echo "# edit" >> app.py
out="$($S preflight 2>/dev/null || true)"
echo "$out" | grep -q 'WARN  working tree has' || fail "preflight should WARN on tracked changes"
out="$($S verify-checks 2>&1 || true)"
echo "$out" | grep -q 'refusing' || fail "verify-checks should refuse tracked changes"
git checkout -q app.py

# placeholder checks.sh must fail; a real one must pass clean and fail when sabotaged
git add -A; git commit -qm install
$S verify-checks 2>/dev/null && fail "placeholder checks.sh should fail"
out="$($S verify-checks --break app.py 2>&1 || true)"
echo "$out" | grep -q 'SKIP  sabotage' || fail "sabotage must be skipped when clean runs fail"
printf '#!/usr/bin/env bash\nset -euo pipefail\npython3 -m py_compile app.py\n' > factory/checks.sh
git commit -qam checks
out="$($S verify-checks --break app.py 2>&1 || true)"
echo "$out" | grep -q 'should point at the broken file' || fail "sabotage output should be printed"
out="$($S verify-checks --break app.py 2>&1)" || fail "real checks.sh should verify"
log="$(echo "$out" | grep -o 'full log: .*sabotage.log' | head -1 | sed 's/full log: //')"
[ -s "$log" ] || fail "sabotage full log should be saved and printed"
echo "$out" | grep -q 'first error line' || fail "first error line should be shown"
echo "$out" | grep -q 'suspicious' && fail "a sabotage failure naming the file is not suspicious"
printf '#!/usr/bin/env bash\nexit 0\n' > factory/checks.sh; git commit -qam vacuous
$S verify-checks --break app.py >/dev/null 2>&1 && fail "vacuous checks.sh must be caught"

# install chatter is filtered from the summary but kept in the full log; fast unrelated failures are flagged
printf '#!/usr/bin/env bash\nrc=0\npython3 -m py_compile app.py || rc=$?\necho "Resolved 3 packages"\necho " + pkg==1.0"\nexit $rc\n' > factory/checks.sh
git commit -qam noisy
out="$($S verify-checks --break app.py 2>&1)" || fail "noisy checks.sh should verify"
echo "$out" | grep -q 'Resolved 3 packages' && fail "install noise should be filtered from the summary"
log="$(echo "$out" | grep -o 'full log: .*sabotage.log' | head -1 | sed 's/full log: //')"
grep -q 'Resolved 3 packages' "$log" || fail "full log should keep the noise"
printf '#!/usr/bin/env bash\ngrep -q sabotage app.py && { echo boom; exit 3; }\nexit 0\n' > factory/checks.sh
git commit -qam fast
out="$($S verify-checks --break app.py 2>&1 || true)"
echo "$out" | grep -q 'WARN  suspicious' || fail "fast failure not naming the file should be flagged"
printf '#!/usr/bin/env bash\nexit 0\n' > factory/checks.sh; git commit -qam vacuous2

# 5. detect reports gaps; uv projects get the uv template
printf '[project]\nname="x"\n' > pyproject.toml; touch uv.lock
$S detect | grep -q 'python-uv.sh' || fail "detect should point at python-uv.sh"
$S detect | grep -q 'no linter' || fail "detect should report the linter gap"
rm pyproject.toml uv.lock

# upgrade: untouched file updates, tailored file is held, checks.sh/config.json are project-owned
echo "# tailored" >> .claude/agents/approver.md
cp -r "$SKILL" "$T/skill2" && echo "# new" >> "$T/skill2/payload/factory/bin/route"
echo "# upstream" >> "$T/skill2/payload/.claude/agents/approver.md"
echo "# upstream comment" >> "$T/skill2/payload/factory/checks.sh"
echo "# tailored too" >> .claude/agents/reviewer-ui.md
echo 9.9.9 > "$T/skill2/VERSION"
P="python3 $T/skill2/scripts/factory_setup.py"
$P upgrade-plan | grep -q 'safe .*factory/bin/route' || fail "route should be safe"
$P upgrade-plan | grep -q 'adapted .*approver.md' || fail "approver should be adapted"
$P upgrade-plan | grep -q 'project-owned .*factory/checks.sh' || fail "checks.sh should be project-owned"
$P upgrade-plan | grep -q 'comments only' || fail "comment-only payload change should be called out"
$P upgrade-plan | grep -q 'adapted .*reviewer-ui.md' && fail "unchanged-payload tailored file is not homework"
$P upgrade-plan | grep -q 'kept .*reviewer-ui.md' || fail "unchanged-payload tailored file should be listed as kept"
$P upgrade-apply | grep -q 'DRY RUN' || fail "upgrade-apply default is a dry run"
tail -1 factory/bin/route | grep -q '# new' && fail "dry run changed route"
out="$($P upgrade-apply --yes)"
echo "$out" | grep -q 'still to merge by hand: .*approver.md' || fail "apply should hold approver"
echo "$out" | grep -q 'Updated factory/VERSION .* -> 9.9.9' || fail "apply should say what it did to VERSION"
echo "$out" | grep -q 'overwrote 1 untouched file' || fail "apply should report the file it overwrote"
$P upgrade-apply --yes | grep -q 'already 9.9.9 and the manifest; no payload files overwritten' || fail "no-op apply message"
tail -1 factory/bin/route | grep -q '# new' || fail "route not updated"
tail -1 .claude/agents/approver.md | grep -q tailored || fail "approver was overwritten"
grep -q 'exit 0' factory/checks.sh || fail "checks.sh was overwritten"
# --mark-reviewed: held files stop being flagged until the payload changes again
$P upgrade-apply --yes --mark-reviewed >/dev/null
out="$($P upgrade-plan)"
echo "$out" | grep -q 'adapted .*approver.md' && fail "reviewed approver should not be flagged"
echo "$out" | grep -q 'project-owned .*checks.sh' && fail "reviewed checks.sh should not be flagged"
echo "$out" | grep -q 'kept .*approver.md' || fail "reviewed approver should be kept"
echo "# upstream again" >> "$T/skill2/payload/.claude/agents/approver.md"
$P upgrade-plan | grep -q 'adapted .*approver.md' || fail "a new payload change should flag it again"

# agents-md dashboard command binds to localhost and uses -d
grep -q -- '--bind 127.0.0.1 -d factory' "$SKILL/templates/agents-section.md" || fail "dashboard command"
echo "SMOKE OK"

#!/usr/bin/env python3
"""Deterministic half of /factory-setup. The agent does the judgment calls.

Run from the TARGET repo's root. Standard library only, Python 3.10+.
Learn the interface from `factory_setup.py --help` (it lists every command);
`<command> --help` is always safe and never runs the command.

Commands that write outside the repo working tree (`labels`, `upgrade-apply`)
are a dry run unless you pass --yes.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PAYLOAD = SKILL / "payload"
TEMPLATES = SKILL / "templates"
VERSION = (SKILL / "VERSION").read_text().strip()
MIN_CLAUDE = (2, 1, 257)
MIN_PYTHON = (3, 10)

# Never overwritten by an upgrade: the project owns them.
PROJECT_OWNED = {"factory/checks.sh", "factory/config.json"}
# Tailored by the installing agent: an upgrade holds these for a manual merge.
ADAPTED = PROJECT_OWNED | {
    ".claude/agents/intake.md",
    ".claude/agents/approver.md",
    ".claude/agents/reviewer-security.md",
    ".claude/agents/reviewer-ui.md",
    ".claude/agents/reviewer-ux.md",
}
EXEC = {"factory/checks.sh", "factory/bin/job", "factory/bin/gate", "factory/bin/route", "factory/bin/dashboard"}
IGNORE_LINES = ["/factory/jobs/", "/.worktrees/", "/factory/.dashboard.pid", "/factory/.dashboard.log"]
LABELS = [
    ("factory", "5319E7", "Build this with the software factory"),
    ("factory:needs-info", "FBCA04", "The factory asked the author a question"),
    ("factory:needs-human", "D93F0B", "The factory needs a human decision on the PR"),
]
SECTION_MARK = "## Software factory"
BEGIN = "<!-- factory-setup:begin -->"
END = "<!-- factory-setup:end -->"
MANIFEST = Path("factory/.setup-manifest.json")


def sh(*cmd, cwd=None, check=False):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        res = subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: command not found")
    if check and res.returncode != 0:
        sys.exit(f"`{' '.join(cmd)}` failed: {res.stderr.strip() or res.stdout.strip()}")
    return res


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def payload_files():
    return sorted(p.relative_to(PAYLOAD).as_posix() for p in PAYLOAD.rglob("*") if p.is_file())


def repo_root():
    res = sh("git", "rev-parse", "--show-toplevel")
    if res.returncode != 0:
        sys.exit("not inside a git repository")
    return Path(res.stdout.strip())


def dirty_paths(root):
    """(tracked changes, untracked files). Only tracked changes make HEAD differ from what's on disk."""
    out = sh("git", "status", "--porcelain", "--untracked-files=all", cwd=root).stdout
    tracked = [line[3:] for line in out.splitlines() if not line.startswith("??")]
    untracked = [line[3:] for line in out.splitlines() if line.startswith("??")]
    return tracked, untracked


def listing(paths, n=5):
    return ", ".join(paths[:n]) + (f", and {len(paths) - n} more" if len(paths) > n else "")


def code_sha(path):
    """Hash of a script with comment and blank lines removed, to tell comment-only payload changes."""
    lines = [l.rstrip() for l in Path(path).read_text().splitlines()]
    keep = [l for l in lines if l.strip() and (not l.lstrip().startswith("#") or l.startswith("#!"))]
    return hashlib.sha256("\n".join(keep).encode()).hexdigest()


def load_manifest(root):
    path = root / MANIFEST
    return json.loads(path.read_text()) if path.exists() else None


def write_manifest(root, files, installed_from=None):
    old = load_manifest(root) or {}
    data = {
        "version": VERSION,
        "installed_from": installed_from or old.get("installed_from") or VERSION,
        "skill_source": "dwightfowler-tema/factory-setup",
        # pristine = sha of the payload file as shipped; the target's own file may drift (adapted).
        "files": {f: sha(PAYLOAD / f) for f in files},
        # comment-stripped hash of the shipped scripts: lets upgrade-plan call a change "comments only".
        "code": {f: code_sha(PAYLOAD / f) for f in files if f in EXEC},
        # payload hash a human last reviewed for held files (see upgrade-apply --mark-reviewed).
        "reviewed": old.get("reviewed", {}),
    }
    (root / MANIFEST).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    (root / "factory" / "VERSION").write_text(VERSION + "\n")


# ---------------------------------------------------------------- preflight
def cmd_preflight(root, args):
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))

    origin = sh("git", "remote", "get-url", "origin", cwd=root)
    check("origin remote exists", origin.returncode == 0, origin.stdout.strip())
    check("origin is on GitHub", "github.com" in origin.stdout)
    auth = sh("gh", "auth", "status")
    check("gh is authenticated", auth.returncode == 0, "" if auth.returncode == 0 else "run `gh auth login`")
    base = None
    if auth.returncode == 0:
        view = sh("gh", "repo", "view", "--json", "defaultBranchRef,viewerPermission", cwd=root)
        if view.returncode == 0:
            info = json.loads(view.stdout)
            base = info["defaultBranchRef"]["name"]
            check("viewer can push", info.get("viewerPermission") in ("ADMIN", "MAINTAIN", "WRITE"),
                  info.get("viewerPermission", ""))
        else:
            check("gh can read this repo", False, view.stderr.strip())
    if base:
        sh("git", "fetch", "origin", base, cwd=root)
        ref = sh("git", "rev-parse", "--verify", f"origin/{base}", cwd=root)
        check(f"origin/{base} exists", ref.returncode == 0,
              "jobs branch from it; push the default branch first" if ref.returncode else base)
        if ref.returncode == 0:
            ahead = sh("git", "rev-list", "--count", f"origin/{base}..HEAD", cwd=root).stdout.strip()
            if ahead not in ("", "0"):
                print(f"WARN  HEAD is {ahead} commit(s) ahead of origin/{base}. Jobs branch from origin/{base}, so "
                      "everything checks.sh depends on (lockfile, tests, config), not just the factory files, "
                      "must be pushed there before the first run.")
    ver = sh("claude", "--version")
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", ver.stdout)
    have = tuple(int(x) for x in m.groups()) if m else None
    check("claude >= 2.1.257", bool(have and have >= MIN_CLAUDE), ver.stdout.strip() or "not found")
    check("python >= 3.10", sys.version_info[:2] >= MIN_PYTHON, sys.version.split()[0])
    clashes = [f for f in payload_files() if (root / f).exists()]
    manifest = load_manifest(root)
    if clashes and manifest:
        print(f"NOTE  factory already installed (v{manifest['version']}); use upgrade-plan, not copy")
    else:
        check("no existing files in the way", not clashes, ", ".join(clashes))
    tracked, untracked = dirty_paths(root)
    if tracked:
        print(f"WARN  working tree has {len(tracked)} staged/modified tracked change(s): {listing(tracked)}. Start the "
              "install from a committed tree: verify-checks tests the committed state, so pending project work "
              "makes it meaningless.")
    if untracked:
        print(f"NOTE  {len(untracked)} untracked file(s): {listing(untracked)}. These can't affect clean worktrees "
              "of HEAD; just don't commit them with the install.")
    if base:
        print(f"BASE_BRANCH={base}")
    sys.exit(0 if all(results) else 1)


# --------------------------------------------------------------------- copy
def cmd_copy(root, args):
    if load_manifest(root):
        sys.exit("already installed: run upgrade-plan instead")
    clashes = [f for f in payload_files() if (root / f).exists()]
    if clashes:
        sys.exit("refusing to overwrite: " + ", ".join(clashes))
    files = payload_files()
    for f in files:
        dest = root / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD / f, dest)
        if f in EXEC:
            dest.chmod(0o755)
    write_manifest(root, files)
    print(f"copied {len(files)} files, wrote factory/VERSION ({VERSION}) and {MANIFEST}")
    print("next: adapt " + ", ".join(sorted(ADAPTED)))


# ---------------------------------------------------------------- gitignore
def cmd_gitignore(root, args):
    path = root / ".gitignore"
    text = path.read_text() if path.exists() else ""
    have = {line.strip() for line in text.splitlines()}
    add = [line for line in IGNORE_LINES if line not in have]
    if add:
        path.write_text(text + ("" if text.endswith("\n") or not text else "\n") + "\n".join(add) + "\n")
    print("added: " + (", ".join(add) if add else "nothing (already present)"))


# ---------------------------------------------------------------- agents-md
def agents_target(root):
    return next((root / n for n in ("AGENTS.md", "CLAUDE.md") if (root / n).exists()), root / "AGENTS.md")


def find_section(text):
    """Locate the factory section: ('marked'|'legacy'|None, start, end)."""
    if BEGIN in text and END in text:
        return "marked", text.index(BEGIN), text.index(END) + len(END)
    m = re.search(r"^## Software factory\s*$", text, re.M)
    if m:
        nxt = re.search(r"^## ", text[m.end():], re.M)
        return "legacy", m.start(), (m.end() + nxt.start() if nxt else len(text))
    return None, 0, 0


def section_state(root):
    """current | stale | legacy | missing, for upgrade-plan."""
    target = agents_target(root)
    text = target.read_text() if target.exists() else ""
    kind, i, j = find_section(text)
    if kind is None:
        return "missing"
    if kind == "legacy":
        return "legacy"
    tpl = (TEMPLATES / "agents-section.md").read_text().strip()
    return "current" if text[i:j].strip() == tpl else "stale"


def cmd_agents_md(root, args):
    target = agents_target(root)
    text = target.read_text() if target.exists() else ""
    tpl = (TEMPLATES / "agents-section.md").read_text().strip()
    kind, i, j = find_section(text)
    rest = text[j:]
    if kind is None:
        target.write_text(text + ("\n" if text and not text.endswith("\n\n") else "") + tpl + "\n")
        print(f"appended the factory section to {target.name}")
        if not text:
            print("NOTE  file was new: add setup, dev-server and validation notes (see INSTALL.md)")
    elif kind == "marked":
        if text[i:j].strip() == tpl:
            print(f"{target.name} factory section is up to date")
        else:
            target.write_text(text[:i] + tpl + rest)
            print(f"refreshed the factory section in {target.name} (only the part between the markers)")
    elif args.migrate:
        target.write_text(text[:i] + tpl + ("\n\n" + rest.lstrip("\n") if rest.strip() else "\n"))
        print(f"replaced the old unmarked factory section in {target.name} (from '## Software factory' to the "
              "next '## ' heading) with the marked, current one")
    else:
        print(f"WARN  {target.name} has an old factory section without markers (it likely names the old dashboard "
              "command). Re-run with --migrate to replace it (everything from '## Software factory' to the next "
              "'## ' heading), or edit it by hand.")


# ------------------------------------------------------------------- labels
def cmd_labels(root, args):
    existing = None
    res = sh("gh", "label", "list", "--json", "name", "--limit", "200", cwd=root)
    if res.returncode == 0:
        existing = {x["name"] for x in json.loads(res.stdout)}
    elif not args.yes:
        print(f"NOTE  could not list existing labels ({res.stderr.strip()}); showing what would be created")
    if not args.yes:
        print("DRY RUN: nothing changed on GitHub. Labels the factory uses:")
        for name, _, desc in LABELS:
            state = "exists, would be updated" if existing is not None and name in existing else "would be created"
            print(f"  {name}  ({state})  {desc}")
        print("Idempotent. Re-run with --yes to apply. Remove later with `gh label delete <name>`.")
        return
    for name, color, desc in LABELS:
        res = sh("gh", "label", "create", name, "--color", color, "--description", desc, "--force", cwd=root)
        print(("ok    " if res.returncode == 0 else "FAIL  ") + name
              + ("" if res.returncode == 0 else f": {res.stderr.strip()}"))


# ------------------------------------------------------------------- config
def _config_path(root):
    path = root / "factory" / "config.json"
    if not path.exists():
        sys.exit("factory/config.json is missing (run copy first)")
    return path


def _config_load(path):
    text = path.read_text()
    try:
        return json.loads(text), text.endswith("\n")
    except json.JSONDecodeError as e:
        sys.exit(f"factory/config.json is not valid JSON: {e}")


def _walk(data, dotted, create=False):
    """Return (parent dict, last key). Errors on a missing path unless create."""
    keys = dotted.split(".")
    node = data
    for k in keys[:-1]:
        if not isinstance(node, dict) or k not in node:
            if create and isinstance(node, dict):
                node[k] = {}
            else:
                sys.exit(f"no such key: {dotted} ('{k}' not found)")
        node = node[k]
    if not isinstance(node, dict):
        sys.exit(f"cannot address {dotted}: parent is not an object")
    return node, keys[-1]


# --- minimal JSON scanner: find a value's span in the raw text so `config set` edits only those characters
def _ws(t, i):
    while i < len(t) and t[i] in " \t\r\n":
        i += 1
    return i


def _value_end(t, i):
    """Index just past the JSON value that starts at t[i]."""
    c = t[i]
    if c == '"':
        i += 1
        while t[i] != '"':
            i += 2 if t[i] == "\\" else 1
        return i + 1
    if c in "{[":
        close = "}" if c == "{" else "]"
        i = _ws(t, i + 1)
        while t[i] != close:
            if c == "{":
                i = _ws(t, _value_end(t, i))  # key
                i = _ws(t, i + 1)             # colon
            i = _ws(t, _value_end(t, i))
            if t[i] == ",":
                i = _ws(t, i + 1)
        return i + 1
    while i < len(t) and t[i] not in ",}] \t\r\n":
        i += 1
    return i


def _members(t, i):
    """Members of the object starting at t[i]: [(key, key_start, value_start, value_end)]."""
    out = []
    i = _ws(t, i + 1)
    while t[i] != "}":
        ks = i
        ke = _value_end(t, i)
        i = _ws(t, _ws(t, ke) + 1)
        ve = _value_end(t, i)
        out.append((json.loads(t[ks:ke]), ks, i, ve))
        i = _ws(t, ve)
        if t[i] == ",":
            i = _ws(t, i + 1)
    return out


def _inline(value):
    return json.dumps(value, separators=(", ", ": "))


def _edit_text(text, dotted, new, add):
    """Return text with only the target value replaced or added, or None to fall back to a rewrite."""
    keys = dotted.split(".")
    obj = _ws(text, 0)
    if text[obj] != "{":
        return None
    for n, k in enumerate(keys):
        members = _members(text, obj)
        hit = [m for m in members if m[0] == k]
        last = n == len(keys) - 1
        if hit and last:
            _, _, vs, ve = hit[0]
            return text[:vs] + _inline(new) + text[ve:]
        if hit:
            obj = hit[0][2]
            if text[obj] != "{":
                return None
            continue
        if not add:
            return None
        # k is missing here: add it (wrapping the value in the remaining nested keys) to this object
        value = new
        for rest in reversed(keys[n + 1:]):
            value = {rest: value}
        end = _value_end(text, obj)  # just past the closing brace
        entry = f"{json.dumps(k)}: {_inline(value)}"
        if not members:
            return text[:obj + 1] + " " + entry + " " + text[end - 1:]
        last_end = members[-1][3]
        if "\n" in text[obj:end]:
            line_start = text.rfind("\n", 0, members[-1][1]) + 1
            indent = text[line_start:members[-1][1]]
            return text[:last_end] + ",\n" + indent + entry + text[last_end:]
        return text[:last_end] + ", " + entry + text[last_end:]
    return None


def cmd_config(root, args):
    path = _config_path(root)
    data, trailing_nl = _config_load(path)
    if args.action == "get":
        node, key = _walk(data, args.key)
        if key not in node:
            sys.exit(f"no such key: {args.key}")
        print(json.dumps(node[key]))
        return
    try:
        new = json.loads(args.value)
    except json.JSONDecodeError:
        new = args.value
    node, key = _walk(data, args.key, create=False) if not args.add else _walk_or_none(data, args.key)
    if (node is None or key not in node) and not args.add:
        sys.exit(f"no such key: {args.key} (pass --add to create it)")
    old = node.get(key, "<unset>") if node is not None else "<unset>"
    text = path.read_text()
    out = _edit_text(text, args.key, new, args.add)
    note = ""
    if out is None:  # unusual shapes (e.g. a parent that isn't an object): rebuild, which re-indents the file
        node, key = _walk(data, args.key, create=True)
        node[key] = new
        out = json.dumps(data, indent=2) + ("\n" if trailing_nl else "")
        note = "  (NOTE: unusual structure, so the file was re-indented)"
    check = json.loads(out)  # re-validate before touching the real file, and verify the value landed
    probe = check
    for k in args.key.split("."):
        probe = probe[k]
    if probe != new:
        sys.exit("internal error: edited value did not parse back to the requested value; file left untouched")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(out)
    os.replace(tmp, path)
    print(f"{args.key}: {json.dumps(old) if old != '<unset>' else old} -> {json.dumps(new)}{note}")


def _walk_or_none(data, dotted):
    """Like _walk, but returns (None, key) when a parent is missing (so --add can create it)."""
    keys = dotted.split(".")
    node = data
    for k in keys[:-1]:
        if not isinstance(node, dict) or k not in node:
            return None, keys[-1]
        node = node[k]
    return (node if isinstance(node, dict) else None), keys[-1]


# ------------------------------------------------------------------- detect
PY_LINT = ("ruff", "flake8", "pylint")
PY_TYPES = ("mypy", "pyright", "pytype")


def cmd_detect(root, args):
    found = []
    gaps = []
    pkg = root / "package.json"
    if pkg.exists():
        meta = json.loads(pkg.read_text())
        scripts = meta.get("scripts", {})
        deps = {**meta.get("dependencies", {}), **meta.get("devDependencies", {})}
        pm = ("pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists()
              else "bun" if (root / "bun.lockb").exists() else "npm")
        found.append(f"node ({pm}): install via lockfile; scripts: " + (", ".join(scripts) or "none"))
        if not ({"eslint", "@biomejs/biome", "oxlint"} & set(deps) or "lint" in scripts):
            gaps.append("node: no linter (eslint/biome/oxlint) configured")
        if "typescript" not in deps and "typecheck" not in scripts:
            gaps.append("node: no typechecker (tsc) configured")
    pyproject = root / "pyproject.toml"
    if pyproject.exists() or (root / "requirements.txt").exists():
        text = pyproject.read_text() if pyproject.exists() else ""
        for extra in ("requirements.txt", "requirements-dev.txt", "setup.cfg", "tox.ini", "ruff.toml",
                      ".flake8", "mypy.ini", "pyrightconfig.json"):
            if (root / extra).exists():
                text += "\n" + (root / extra).read_text()
        if (root / "uv.lock").exists():
            found.append(f"python (uv): uv.lock present; start from {TEMPLATES}/checks/python-uv.sh")
        else:
            found.append(f"python: pyproject.toml / requirements.txt present; start from {TEMPLATES}/checks/python.sh")
        if not any(t in text for t in PY_LINT):
            gaps.append("python: no linter (ruff/flake8/pylint) configured")
        if not any(t in text for t in PY_TYPES):
            gaps.append("python: no typechecker (mypy/pyright) configured")
    if (root / "go.mod").exists():
        found.append("go: go vet ./... && go test ./...")
        if not list(root.glob(".golangci.*")):
            gaps.append("go: no golangci-lint config (go vet only)")
    for name, label in (("Cargo.toml", "rust: cargo clippy/test/build"),
                        ("pom.xml", "java (maven)"), ("build.gradle", "java (gradle)"), ("*.csproj", "dotnet")):
        if list(root.glob(name)):
            found.append(label)
    mk = root / "Makefile"
    if mk.exists():
        targets = sorted(set(re.findall(r"^([A-Za-z][\w-]*):", mk.read_text(), re.M)))
        found.append("Makefile targets: " + ", ".join(targets))
    for name in ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md"):
        if (root / name).exists():
            found.append(f"read for documented commands: {name}")
    wf = root / ".github" / "workflows"
    if wf.is_dir():
        for f in sorted(wf.glob("*.y*ml")):
            runs = re.findall(r"^\s*-?\s*run:\s*(.+)$", f.read_text(), re.M)
            if runs:
                found.append(f"CI {f.name} runs:")
                found.extend(f"    {r.strip()}" for r in runs)
    else:
        found.append("no .github/workflows (CI is the best source of truth; fall back to docs)")
    print("\n".join(found) or "nothing detected")
    if gaps:
        print("\nGAPS (tell the user the gate is only as strong as the tests/build):")
        print("\n".join(f"  - {g}" for g in gaps))
    scan_not_run(root)


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", ".worktrees", "factory", "__pycache__", "target", "dist",
             "build", ".tox", ".mypy_cache", ".pytest_cache"}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
SKIP_RULES = [
    (re.compile(r"\.py$"), re.compile(r"pytest\.skip|pytest\.mark\.(skip|skipif|xfail)|unittest\.skip|\bxfail\b"), "python"),
    (re.compile(r"\.(js|jsx|ts|tsx|mjs|cjs)$"),
     re.compile(r"\b(it|test|describe)\.(skip|todo)\(|\bxit\(|\bxdescribe\(|\bxtest\("), "js/ts"),
    (re.compile(r"_test\.go$"), re.compile(r"\bt\.Skip(Now|f)?\("), "go"),
    (re.compile(r"\.rs$"), re.compile(r"#\[ignore"), "rust"),
]
DESELECT_FILES = ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "package.json", "jest.config.js",
                  "jest.config.ts", "vitest.config.ts", "vitest.config.js")
DESELECT = re.compile(r"addopts[^\n]*(-m\b|--deselect|--ignore)|testPathIgnorePatterns|--testPathIgnorePatterns")


def scan_not_run(root):
    """Report skipped/xfail/ignored tests and deselecting config. A test that doesn't run is a failure."""
    hits = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.stat().st_size > 1_000_000:
                continue
            for ext, pattern, label in SKIP_RULES:
                if ext.search(name) and (label in ("go", "rust") or TEST_PATH.search(rel)):
                    try:
                        lines = path.read_text(errors="ignore").splitlines()
                    except OSError:
                        continue
                    for n, line in enumerate(lines, 1):
                        if pattern.search(line):
                            hits.setdefault(label, []).append(f"{rel}:{n}: {line.strip()[:90]}")
    deselect = []
    for name in DESELECT_FILES:
        f = root / name
        if f.exists():
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if DESELECT.search(line):
                    deselect.append(f"{name}:{n}: {line.strip()[:90]}")
    if not hits and not deselect:
        print("\nNo skipped/xfail/ignored tests or deselecting config found.")
        return
    print("\nTESTS THAT WOULD NOT RUN (a skipped, xfailed, ignored or deselected test is a FAILURE, never a pass: "
          "fix it, or ask the owner; do not quietly exclude it):")
    for label, items in hits.items():
        print(f"  {label}: {len(items)} found")
        for it in items[:5]:
            print(f"    {it}")
    if deselect:
        print(f"  deselecting config: {len(deselect)} found")
        for it in deselect[:5]:
            print(f"    {it}")


# ------------------------------------------------------------ verify-checks
def run_checks_in(worktree, checks):
    start = time.monotonic()
    res = subprocess.run(["bash", str(checks)], cwd=worktree, capture_output=True, text=True)
    return res.returncode, int(time.monotonic() - start), (res.stdout + res.stderr)


NOISE = re.compile(
    r"^\s*([+-]\s+\S+==\S+|(Resolved|Installed|Uninstalled|Prepared|Downloading|Downloaded|Audited|Built)\b"
    r"|Collecting\b|Requirement already|Using cached|Successfully installed|Obtaining\b|Preparing metadata"
    r"|Installing collected|npm (warn|notice)\b|added \d+ packages)")
ERRLINE = re.compile(r"error|FAIL|Traceback", re.I)


NOT_RUN = re.compile(r"\b(\d+)\s+(skipped|xfailed|xpassed|deselected|ignored|pending|todo)\b", re.I)


def not_run(log):
    """Counts of tests the output says did not run: skipped, xfailed, xpassed, deselected, ignored, ..."""
    found = {}
    for n, kind in NOT_RUN.findall(log):
        if int(n):
            found[kind.lower()] = found.get(kind.lower(), 0) + int(n)
    go = len(re.findall(r"^\s*--- SKIP", log, re.M))
    if go:
        found["skipped"] = found.get("skipped", 0) + go
    return found


def summarize(log, n):
    """Last n lines of the output with package-install chatter removed, and the first error-looking line."""
    lines = [l for l in log.splitlines() if l.strip() and not NOISE.match(l)]
    first = next((l for l in lines if ERRLINE.search(l)), None)
    return lines[-n:], first


def report(name, log, logdir, n, indent=""):
    path = logdir / f"{name}.log"
    path.write_text(log)
    lines, first = summarize(log, n)
    print(f"{indent}full log: {path}")
    if first:
        print(f"{indent}first error line: {first.strip()}")
    print("\n".join(indent + l for l in lines))


def cmd_verify_checks(root, args):
    checks = root / "factory" / "checks.sh"
    if not checks.exists():
        sys.exit("factory/checks.sh missing")
    tracked, untracked = dirty_paths(root)
    if tracked and not args.allow_dirty:
        sys.exit(f"refusing: {len(tracked)} tracked file(s) are staged or modified: {listing(tracked)}.\n"
                 "verify-checks tests the COMMITTED state (HEAD) in clean worktrees, like the gate does. Commit the "
                 "project's pending work and factory/checks.sh first, or pass --allow-dirty to run anyway.")
    if untracked:
        print(f"NOTE  {len(untracked)} untracked file(s) ignored (they aren't in HEAD): {listing(untracked)}")
    tmp = Path(tempfile.mkdtemp(prefix="factory-verify-"))
    logdir = Path(tempfile.mkdtemp(prefix="factory-verify-logs-"))  # kept so you can read full output
    wts = []

    def add(name):
        wt = tmp / name
        sh("git", "worktree", "add", "--detach", str(wt), "HEAD", cwd=root, check=True)
        wts.append(wt)
        return wt

    ok = True
    try:
        clean = add("clean")
        for i in (1, 2):
            code, secs, log = run_checks_in(clean, checks)
            print(f"{'PASS' if code == 0 else 'FAIL'}  clean run {i}: exit {code} in {secs}s")
            (logdir / f"clean-{i}.log").write_text(log)
            if code:
                report(f"clean-{i}", log, logdir, 25)
                ok = False
            skipped = not_run(log)
            if skipped:
                print(f"FAIL  clean run {i}: tests did not run: "
                      + ", ".join(f"{n} {k}" for k, n in sorted(skipped.items()))
                      + ". A skipped, deselected or not-run test is a failure, not a pass: make checks.sh fail on it.")
                ok = False
            elif code == 0:
                print(f"      no skipped/deselected/not-run tests reported in run {i}'s output")
        if args.break_file:
            if not ok:
                print("SKIP  sabotage run: the clean runs already fail, so a failure now would prove nothing. "
                      "Fix the clean runs first.")
            else:
                bad = add("broken")
                target = bad / args.break_file
                if not target.exists():
                    sys.exit(f"--break file not found in HEAD: {args.break_file}")
                with open(target, "a") as fh:
                    fh.write("\n@@@ factory sabotage @@@\n")
                code, secs, log = run_checks_in(bad, checks)
                fails = code != 0
                print(f"{'PASS' if fails else 'FAIL'}  sabotaged {args.break_file}: checks.sh exit {code} in {secs}s"
                      + ("" if fails else "  <-- the gate would let broken code through"))
                print("      (the failure should point at the broken file, not at the environment)")
                report("sabotage", log, logdir, 12, indent="      ")
                if fails and secs < 2 and Path(args.break_file).name not in log:
                    print(f"WARN  suspicious: fast failure ({secs}s) not mentioning {args.break_file}. It may be an "
                          "environment failure rather than the sabotage; read the full log before trusting this.")
                ok = ok and fails
        else:
            print("NOTE  no --break FILE given: the script was not shown to be able to fail")
    finally:
        for wt in wts:
            sh("git", "worktree", "remove", "--force", str(wt), cwd=root)
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ upgrade
def diff_stat(target, new):
    import difflib
    a = (Path(target)).read_text().splitlines()
    b = (Path(new)).read_text().splitlines()
    return sum(1 for l in difflib.unified_diff(a, b, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---"))


def classify(root, manifest):
    """Compare each payload file against the target and the install-time manifest."""
    rows = []
    files = payload_files()
    reviewed = manifest.get("reviewed", {})
    code = manifest.get("code", {})

    def held_row(f, kind, target, new, pristine):
        base = reviewed.get(f) or pristine
        if base == new:
            since = "last review" if f in reviewed else "install"
            return (f, "kept", f"{'project-owned' if f in PROJECT_OWNED else 'adapted'}; "
                               f"payload unchanged since {since}, nothing to merge")
        note = "payload changed"
        if f in EXEC and code.get(f) == code_sha(PAYLOAD / f):
            note += " (comments only; safe to ignore)"
        note += f"; {diff_stat(target, PAYLOAD / f)} line(s) differ from your copy"
        note += ". Never overwritten; merge by hand" if f in PROJECT_OWNED else ". Merge by hand"
        return (f, kind, note)

    for f in files:
        new = sha(PAYLOAD / f)
        target = root / f
        pristine = manifest["files"].get(f)
        if not target.exists():
            rows.append((f, "missing" if pristine else "new", ""))
        elif f in PROJECT_OWNED:
            rows.append((f, "current", "") if sha(target) == new
                        else held_row(f, "project-owned", target, new, pristine))
        elif pristine is None:
            rows.append((f, "clash", "new in payload but a file already exists"))
        elif sha(target) == new:
            rows.append((f, "current", ""))
        elif sha(target) == pristine:
            rows.append((f, "safe", "untouched since install; payload changed"))
        else:
            rows.append(held_row(f, "adapted" if f in ADAPTED else "modified", target, new, pristine))
    for f in manifest["files"]:
        if f not in set(files):
            rows.append((f, "removed-upstream", "no longer in payload"))
    return rows


APPLY_KINDS = ("safe", "new", "missing")
HELD_KINDS = ("adapted", "modified", "clash", "project-owned")


def cmd_upgrade_plan(root, args):
    manifest = load_manifest(root)
    if not manifest:
        sys.exit("no manifest: this repo wasn't installed by factory-setup (or was before v0.1.0)")
    print(f"installed {manifest['version']} -> available {VERSION}")
    rows = classify(root, manifest)
    kept = [f for f, kind, _ in rows if kind == "kept"]
    todo = [r for r in rows if r[1] in APPLY_KINDS]
    held = [r for r in rows if r[1] in HELD_KINDS]
    other = [r for r in rows if r[1] == "removed-upstream"]
    for f, kind, note in todo + held + other:
        print(f"{kind:17} {f}  {note}")
    if kept:
        print(f"kept              {len(kept)} tailored file(s) with nothing to merge (payload unchanged): "
              + ", ".join(kept))
    state = section_state(root)
    if state in ("stale", "legacy"):
        print(f"agents-md         the factory section in {agents_target(root).name} is "
              + ("stale (older than this skill's template)" if state == "stale"
                 else "an old unmarked section (it likely names the old dashboard command)")
              + "; run `SCRIPT agents-md" + (" --migrate" if state == "legacy" else "") + "` to update it")
    if not (todo or held or other or state in ("stale", "legacy")):
        print("Nothing to do: only the version stamp and manifest will be refreshed.")
    if todo:
        print(f"\n`{'`, `'.join(APPLY_KINDS)}` are applied by `upgrade-apply --yes`.")
    if held:
        print("Held files are never overwritten: `diff -u <target> " + f"{PAYLOAD}/<file>`, merge by hand, then "
              "`upgrade-apply --yes --mark-reviewed` so they aren't flagged again until the payload changes.")


def cmd_upgrade_apply(root, args):
    manifest = load_manifest(root)
    if not manifest:
        sys.exit("no manifest")
    rows = classify(root, manifest)
    todo = [f for f, kind, _ in rows if kind in APPLY_KINDS]
    held = {f for f, kind, _ in rows if kind in HELD_KINDS}
    keep = held | {f for f, kind, _ in rows if kind == "kept"}
    old_version = manifest["version"]
    if not args.yes:
        print("DRY RUN: nothing changed. Would overwrite: " + (", ".join(todo) or "no payload files"))
        print("Would hold for a manual merge: " + (", ".join(sorted(held)) or "nothing"))
        print(f"Would update factory/VERSION {old_version} -> {VERSION} and the manifest, and make sure "
              ".gitignore has the factory lines.")
        print("Review upgrade-plan with the user, then re-run with --yes.")
        return
    for f in todo:
        dest = root / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD / f, dest)
        if f in EXEC:
            dest.chmod(0o755)
    write_manifest(root, [f for f in payload_files() if f not in keep],
                   installed_from=manifest.get("installed_from"))
    new = load_manifest(root)
    for f in keep:  # keep the old pristine/code hashes so a later upgrade still sees real payload changes
        if f in manifest["files"]:
            new["files"][f] = manifest["files"][f]
        if f in manifest.get("code", {}):
            new.setdefault("code", {})[f] = manifest["code"][f]
    reviewed = dict(manifest.get("reviewed", {}))
    if args.mark_reviewed:
        for f in held:
            reviewed[f] = sha(PAYLOAD / f)
    new["reviewed"] = reviewed
    (root / MANIFEST).write_text(json.dumps(new, indent=2, sort_keys=True) + "\n")
    cmd_gitignore(root, args)
    stamp = (f"Updated factory/VERSION {old_version} -> {VERSION}" if old_version != VERSION
             else f"factory/VERSION already {VERSION}")
    print(f"{stamp} and the manifest; "
          + (f"overwrote {len(todo)} untouched file(s): {', '.join(todo)}." if todo else "no payload files overwritten."))
    if held and not args.mark_reviewed:
        print("still to merge by hand: " + ", ".join(sorted(held)))
        print("when merged or declined, run `upgrade-apply --yes --mark-reviewed`.")
    elif held:
        print("marked as reviewed (not flagged again until the payload changes): " + ", ".join(sorted(held)))


# --------------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(prog="factory_setup.py", description=__doc__.strip(),
                                formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = p.add_subparsers(dest="cmd", metavar="command")

    def add(name, help_text):
        return sub.add_parser(name, help=help_text, description=help_text, allow_abbrev=False)

    add("preflight", "check git, origin, gh, claude, python, clashes; WARN on dirty tree or unpushed commits")
    add("copy", "copy payload/ into the repo; write factory/VERSION and the manifest")
    add("gitignore", "append the factory's two ignore lines (idempotent)")
    am = add("agents-md", "add or refresh the factory section in AGENTS.md / CLAUDE.md (between markers)")
    am.add_argument("--migrate", action="store_true",
                    help="replace an old section that has no markers (from '## Software factory' to the next '## ')")
    lab = add("labels", "list the three GitHub labels (dry run); with --yes create them (idempotent)")
    lab.add_argument("--yes", action="store_true", help="actually create/update the labels on GitHub")
    cfg = add("config", "get/set a key in factory/config.json (never hand-edit the file)")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    g = cfg_sub.add_parser("get", help="print a value", allow_abbrev=False)
    g.add_argument("key", help="dotted key, e.g. ports.base")
    s = cfg_sub.add_parser("set", help="set a value, printing old and new", allow_abbrev=False)
    s.add_argument("key", help="dotted key, e.g. routing.medium.code")
    s.add_argument("value", help="parsed as JSON when valid (3, true, [\"a\"]), else a string")
    s.add_argument("--add", action="store_true", help="allow creating a key that doesn't exist")
    add("detect", "list candidate check commands and linter/typechecker gaps")
    ver = add("verify-checks", "run factory/checks.sh in clean worktrees of HEAD (twice); optionally sabotage")
    ver.add_argument("--break", dest="break_file", metavar="FILE",
                     help="also append garbage to FILE in a throwaway worktree and require checks.sh to FAIL")
    ver.add_argument("--allow-dirty", action="store_true", help="run even though tracked files are staged or modified")
    add("upgrade-plan", "compare the repo with this skill's payload (read-only)")
    up = add("upgrade-apply", "overwrite only files untouched since install (dry run unless --yes)")
    up.add_argument("--yes", action="store_true", help="actually overwrite the safe files")
    up.add_argument("--mark-reviewed", action="store_true",
                    help="record that held files' current payload was reviewed (merged or declined), so "
                         "later upgrades flag them only if the payload changes again")
    return p


def main(argv):
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `... | head` shouldn't traceback
    parser = build_parser()
    args = parser.parse_args(argv)  # --help/-h anywhere prints usage and exits before anything runs
    if not args.cmd:
        parser.print_help()
        return
    root = repo_root()
    os.chdir(root)
    globals()["cmd_" + args.cmd.replace("-", "_")](root, args)


if __name__ == "__main__":
    main(sys.argv[1:])

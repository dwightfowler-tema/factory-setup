#!/usr/bin/env python3
"""Deterministic half of /factory-setup. The agent does the judgment calls.

Run from the TARGET repo's root. Standard library only, Python 3.10+.

  factory_setup.py preflight            check git, origin, gh, claude, python, clashes
  factory_setup.py copy                 copy payload/ into the repo, write factory/VERSION + manifest
  factory_setup.py gitignore            append the factory's two ignore lines
  factory_setup.py agents-md            add the factory section to AGENTS.md / CLAUDE.md
  factory_setup.py labels               create the three GitHub labels (idempotent)
  factory_setup.py detect               list candidate check commands found in the repo
  factory_setup.py verify-checks [--break FILE]
                                        run factory/checks.sh in clean throwaway worktrees (twice),
                                        and, with --break, confirm it FAILS when FILE is sabotaged
  factory_setup.py upgrade-plan         compare the repo with this skill's payload (read-only)
  factory_setup.py upgrade-apply        overwrite only files untouched since install; refresh manifest
"""

import hashlib
import json
import os
import re
import shutil
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

# Files the installing agent is expected to tailor, so upgrades must not overwrite them blindly.
ADAPTED = {
    "factory/config.json",
    "factory/checks.sh",
    ".claude/agents/intake.md",
    ".claude/agents/approver.md",
    ".claude/agents/reviewer-security.md",
    ".claude/agents/reviewer-ui.md",
    ".claude/agents/reviewer-ux.md",
}
EXEC = {"factory/checks.sh", "factory/bin/job", "factory/bin/gate", "factory/bin/route"}
IGNORE_LINES = ["/factory/jobs/", "/.worktrees/"]
LABELS = [
    ("factory", "5319E7", "Build this with the software factory"),
    ("factory:needs-info", "FBCA04", "The factory asked the author a question"),
    ("factory:needs-human", "D93F0B", "The factory needs a human decision on the PR"),
]
SECTION_MARK = "## Software factory"
MANIFEST = Path("factory/.setup-manifest.json")


def sh(*cmd, cwd=None, check=False):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
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
    }
    (root / MANIFEST).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    (root / "factory" / "VERSION").write_text(VERSION + "\n")


# ---------------------------------------------------------------- preflight
def cmd_preflight(root):
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
    if base:
        print(f"BASE_BRANCH={base}")
    sys.exit(0 if all(results) else 1)


# --------------------------------------------------------------------- copy
def cmd_copy(root):
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
def cmd_gitignore(root):
    path = root / ".gitignore"
    text = path.read_text() if path.exists() else ""
    have = {line.strip() for line in text.splitlines()}
    add = [line for line in IGNORE_LINES if line not in have]
    if add:
        path.write_text(text + ("" if text.endswith("\n") or not text else "\n") + "\n".join(add) + "\n")
    print("added: " + (", ".join(add) if add else "nothing (already present)"))


# ---------------------------------------------------------------- agents-md
def cmd_agents_md(root):
    target = next((root / n for n in ("AGENTS.md", "CLAUDE.md") if (root / n).exists()), root / "AGENTS.md")
    text = target.read_text() if target.exists() else ""
    if SECTION_MARK in text:
        print(f"{target.name} already has the factory section")
        return
    section = (TEMPLATES / "agents-section.md").read_text()
    target.write_text(text + ("\n" if text and not text.endswith("\n\n") else "") + section)
    print(f"appended the factory section to {target.name}")
    if not text:
        print("NOTE  file was new: add setup, dev-server and validation notes (see SKILL.md)")


# ------------------------------------------------------------------- labels
def cmd_labels(root):
    for name, color, desc in LABELS:
        res = sh("gh", "label", "create", name, "--color", color, "--description", desc, "--force", cwd=root)
        print(("ok    " if res.returncode == 0 else "FAIL  ") + name + ("" if res.returncode == 0 else f": {res.stderr.strip()}"))


# ------------------------------------------------------------------- detect
def cmd_detect(root):
    found = []
    pkg = root / "package.json"
    if pkg.exists():
        scripts = json.loads(pkg.read_text()).get("scripts", {})
        pm = ("pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists()
              else "bun" if (root / "bun.lockb").exists() else "npm")
        found.append(f"node ({pm}): install via lockfile; scripts: " + (", ".join(scripts) or "none"))
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        found.append("python: pyproject.toml / requirements.txt present")
    for name, label in (("go.mod", "go: go vet ./... && go test ./..."), ("Cargo.toml", "rust: cargo clippy/test/build"),
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


# ------------------------------------------------------------ verify-checks
def run_checks_in(worktree, checks):
    start = time.monotonic()
    res = subprocess.run(["bash", str(checks)], cwd=worktree, capture_output=True, text=True)
    return res.returncode, int(time.monotonic() - start), (res.stdout + res.stderr)


def cmd_verify_checks(root, argv):
    broken = argv[argv.index("--break") + 1] if "--break" in argv else None
    checks = root / "factory" / "checks.sh"
    if not checks.exists():
        sys.exit("factory/checks.sh missing")
    # Judge the committed code, like the gate does: HEAD in a fresh worktree with no installed deps.
    tmp = Path(tempfile.mkdtemp(prefix="factory-verify-"))
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
            if code:
                print("\n".join(log.rstrip().splitlines()[-25:]))
                ok = False
        if broken:
            bad = add("broken")
            target = bad / broken
            if not target.exists():
                sys.exit(f"--break file not found in HEAD: {broken}")
            with open(target, "a") as fh:
                fh.write("\n@@@ factory sabotage @@@\n")
            code, secs, _ = run_checks_in(bad, checks)
            fails = code != 0
            print(f"{'PASS' if fails else 'FAIL'}  sabotaged {broken}: checks.sh exit {code} in {secs}s"
                  + ("" if fails else "  <-- the gate would let broken code through"))
            ok = ok and fails
        else:
            print("NOTE  no --break FILE given: the script was not shown to be able to fail")
    finally:
        for wt in wts:
            sh("git", "worktree", "remove", "--force", str(wt), cwd=root)
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ upgrade
def classify(root, manifest):
    """Compare each payload file against the target and the install-time manifest."""
    rows = []
    for f in payload_files():
        new = sha(PAYLOAD / f)
        target = root / f
        pristine = manifest["files"].get(f)
        if not target.exists():
            rows.append((f, "missing" if pristine else "new", ""))
        elif pristine is None:
            rows.append((f, "clash", "new in payload but a file already exists"))
        elif sha(target) == new:
            rows.append((f, "current", ""))
        elif sha(target) == pristine:
            rows.append((f, "safe", "untouched since install; payload changed"))
        else:
            kind = "adapted" if f in ADAPTED else "modified"
            rows.append((f, kind, "locally changed; merge by hand"))
    for f in manifest["files"]:
        if f not in set(payload_files()):
            rows.append((f, "removed-upstream", "no longer in payload"))
    return rows


def cmd_upgrade_plan(root):
    manifest = load_manifest(root)
    if not manifest:
        sys.exit("no manifest: this repo wasn't installed by factory-setup (or was before v0.1.0)")
    print(f"installed {manifest['version']} -> available {VERSION}")
    for f, kind, note in classify(root, manifest):
        if kind != "current":
            print(f"{kind:17} {f}  {note}")
    print("\n`safe`, `new`, `missing` are applied by upgrade-apply. `adapted`/`modified`/`clash`: diff and merge:")
    print(f"  diff -u <target> {PAYLOAD}/<file>")


def cmd_upgrade_apply(root):
    manifest = load_manifest(root)
    if not manifest:
        sys.exit("no manifest")
    applied = []
    for f, kind, _ in classify(root, manifest):
        if kind in ("safe", "new", "missing"):
            dest = root / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PAYLOAD / f, dest)
            if f in EXEC:
                dest.chmod(0o755)
            applied.append(f)
    # Keep the pristine hash for files we did not touch so a later upgrade still sees them as drifted.
    held = {f for f, k, _ in classify(root, manifest) if k in ("adapted", "modified", "clash")}
    files = [f for f in payload_files() if f not in held]
    old_files = manifest["files"]
    write_manifest(root, files, installed_from=manifest.get("installed_from"))
    new = load_manifest(root)
    for f in held:
        if f in old_files:
            new["files"][f] = old_files[f]
    (root / MANIFEST).write_text(json.dumps(new, indent=2, sort_keys=True) + "\n")
    print("applied: " + (", ".join(applied) or "nothing"))
    if held:
        print("still to merge by hand: " + ", ".join(sorted(held)))
        print("factory/VERSION now says " + VERSION + "; finish the merges, they carry the new payload's changes")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    root = repo_root()
    os.chdir(root)
    cmd = argv[0]
    if cmd == "verify-checks":
        cmd_verify_checks(root, argv[1:])
    elif cmd in ("preflight", "copy", "gitignore", "agents-md", "labels", "detect", "upgrade-plan", "upgrade-apply"):
        globals()["cmd_" + cmd.replace("-", "_")](root)
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])

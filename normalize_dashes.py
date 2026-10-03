#!/usr/bin/env python3
"""Normalize Unicode dashes in files or in Git's staged snapshot."""

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


# Hyphen, nonbreaking hyphen, figure/en/em dash, horizontal bar, hyphen
# bullet, minus sign, two/three-em dash, and small/fullwidth variants.
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\u2e3a\u2e3b\ufe58\ufe63\uff0d"
TRANSLATION = str.maketrans({character: "-" for character in DASHES})
HOOK_MARKER = "# Installed by normalize-dashes (dependency-free Python hook)."


def git(*arguments, cwd=None, data=None):
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(os.fsdecode(result.stderr).strip())
    return result.stdout


def normalize(data):
    """Return unchanged bytes for binary/non-UTF-8 files; preserve newlines."""
    if b"\0" in data:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.translate(TRANSLATION).encode("utf-8")


def normalize_staged():
    root = os.fsdecode(git("rev-parse", "--show-toplevel")).rstrip("\n")
    # Raw, NUL-delimited output handles spaces, tabs, and newlines in filenames.
    # Disabling rename detection treats a rename's destination as an addition.
    records = git(
        "diff", "--cached", "--raw", "--no-abbrev", "--no-renames",
        "--diff-filter=ACM", "-z", "--", cwd=root,
    ).split(b"\0")
    changed = 0
    for offset in range(0, len(records) - 1, 2):
        metadata, filename = records[offset:offset + 2]
        _, mode, _, object_id, _ = metadata.split()
        # Only regular files: never follow symlinks or rewrite submodules.
        if mode not in (b"100644", b"100755"):
            continue
        original = git("cat-file", "blob", object_id.decode(), cwd=root)
        replacement = normalize(original)
        if replacement == original:
            continue

        path = Path(root) / os.fsdecode(filename)
        # Normalize the working copy separately, so partially staged files keep
        # their unstaged edits. Never stage the entire working copy with git add.
        if path.exists() and stat.S_ISREG(path.lstat().st_mode):
            working = path.read_bytes()
            updated = normalize(working)
            if working != updated:
                path.write_bytes(updated)

        new_id = git("hash-object", "-w", "--stdin", cwd=root, data=replacement).strip()
        git(
            "update-index", "-z", "--index-info", cwd=root,
            data=mode + b" " + new_id + b"\t" + filename + b"\0",
        )
        changed += 1
        print("Normalized staged file: " + repr(os.fsdecode(filename)))
    return changed


def normalize_files(filenames):
    for filename in filenames:
        path = Path(filename)
        if not stat.S_ISREG(path.lstat().st_mode):
            continue
        original = path.read_bytes()
        replacement = normalize(original)
        if original != replacement:
            path.write_bytes(replacement)
            print("Normalized file: " + repr(filename))


def install_hook(repository):
    repository = Path(repository).resolve()
    git("rev-parse", "--git-dir", cwd=repository)
    hook_path = Path(os.fsdecode(git(
        "rev-parse", "--git-path", "hooks/pre-commit", cwd=repository,
    )).rstrip("\n"))
    if not hook_path.is_absolute():
        hook_path = repository / hook_path
    if hook_path.is_symlink() or (
        hook_path.exists() and HOOK_MARKER.encode() not in hook_path.read_bytes()
    ):
        raise RuntimeError(
            "An existing pre-commit hook was found at " + str(hook_path)
            + ". Add a call to this script with --staged to that hook."
        )
    source = Path(__file__).read_bytes()
    # The hook is self-contained and keeps working if the original script moves.
    source = source.replace(
        b"#!/usr/bin/env python3\n",
        ("#!/usr/bin/env python3\n" + HOOK_MARKER + "\n").encode(), 1,
    )
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    # Replace atomically rather than leaving a half-written executable hook.
    with tempfile.NamedTemporaryFile(dir=hook_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(source)
    try:
        temporary.chmod(0o755)
        temporary.replace(hook_path)
    finally:
        temporary.unlink(missing_ok=True)
    print("Installed pre-commit hook: " + str(hook_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", nargs="?", const=".", metavar="REPO",
                       help="install a self-contained pre-commit hook (default: current repo)")
    group.add_argument("--staged", action="store_true", help="normalize staged Git files")
    parser.add_argument("files", nargs="*", help="normalize these files directly")
    args = parser.parse_args()
    if args.files and (args.install is not None or args.staged):
        parser.error("file paths cannot be combined with --install or --staged")
    try:
        if args.install is not None:
            install_hook(args.install)
        elif args.files:
            normalize_files(args.files)
        else:
            normalize_staged()
    except (OSError, RuntimeError) as error:
        print("normalize-dashes: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

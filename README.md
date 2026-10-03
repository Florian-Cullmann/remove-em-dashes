# Normalize dashes before a commit

A dependency-free Python 3.8+ script that replaces common Unicode dash characters
with the ASCII hyphen (`-`).

## Install in a Git repository

```sh
python3 /path/to/normalize_dashes.py --install /path/to/your/repo
```

Or run `python3 /path/to/normalize_dashes.py --install` from inside the repository.
Every normal `git commit` then automatically normalizes the staged files and
continues the commit. Python 3 must be available on your `PATH` when committing.
The installed hook is self-contained; the original script can be moved afterward.
Run the install command again to update it when the script changes.

Only changed, staged regular files are checked. UTF-8 text is supported; files
containing NUL bytes, other encodings, symlinks, and submodules are skipped. Line
endings and executable permissions are preserved. Replacements apply everywhere
in the text, including code, strings, and comments.

Partially staged files are supported: the staged snapshot and working copy are
normalized independently, keeping unrelated unstaged edits out of the commit.
Unstaged files are otherwise left alone.

An existing pre-commit hook is never overwritten. If you already have one, add
this command to it, and propagate its exit status so failures stop the commit:

```sh
python3 /absolute/path/to/normalize_dashes.py --staged || exit $?
```

## Run manually

```sh
# Normalize the staged snapshot and corresponding working copies.
python3 /path/to/normalize_dashes.py --staged

# Normalize specific files without changing what is staged.
python3 /path/to/normalize_dashes.py README.md src/example.py
```

The replacements include hyphen (`U+2010`), nonbreaking hyphen (`U+2011`), figure
dash (`U+2012`), en dash (`U+2013`), em dash (`U+2014`), horizontal bar (`U+2015`),
hyphen bullet (`U+2043`), minus sign (`U+2212`), two/three-em dashes (`U+2E3A`,
`U+2E3B`), small em dash (`U+FE58`), small hyphen-minus (`U+FE63`), and fullwidth
hyphen-minus (`U+FF0D`). Adjust `DASHES` in the script to customize the set.

To uninstall, delete the `pre-commit` file at the path printed during installation.
Git hooks are local to each clone, so install it once in every repository you
want to use it in. `git commit --no-verify` bypasses the hook.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

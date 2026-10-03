import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "normalize_dashes.py"
spec = importlib.util.spec_from_file_location("normalize_dashes", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NormalizeTests(unittest.TestCase):
    def test_all_supported_dashes_and_line_endings(self):
        source = ("\ufeffHello " + module.DASHES + "\r\nWorld\n").encode()
        expected = ("\ufeffHello " + "-" * len(module.DASHES) + "\r\nWorld\n").encode()
        self.assertEqual(module.normalize(source), expected)
        self.assertEqual(module.normalize(expected), expected)

    def test_binary_and_non_utf8_are_untouched(self):
        for source in (b"\0hello\xe2\x80\x94", b"\xff\xe2\x80\x94"):
            self.assertEqual(module.normalize(source), source)


class GitHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.hooksPath", ".git/hooks")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True,
        ).stdout

    def script(self, *args, check=True):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=self.repo,
            check=check, capture_output=True,
        )

    def test_installed_hook_normalizes_actual_commit(self):
        self.script("--install")
        path = self.repo / "hello.txt"
        path.write_bytes("Hello—world\r\n1−2 – 3\r\n".encode())
        path.chmod(0o755)
        self.git("add", "hello.txt")
        self.git("commit", "-qm", "first commit")
        expected = b"Hello-world\r\n1-2 - 3\r\n"
        self.assertEqual(self.git("show", "HEAD:hello.txt"), expected)
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(self.git("status", "--porcelain"), b"")
        self.assertEqual(self.git("ls-files", "--stage").split()[0], b"100755")

    def test_partially_staged_file_preserves_unstaged_edits(self):
        path = self.repo / "partial.txt"
        path.write_text("first\nsecond\n")
        self.git("add", "partial.txt")
        self.git("commit", "-qm", "base")
        path.write_text("first—staged\nsecond\n")
        self.git("add", "partial.txt")
        path.write_text("first—staged\nsecond—unstaged\n")
        untouched = self.repo / "unstaged.txt"
        untouched.write_text("leave—alone\n")
        self.script("--install")
        self.git("commit", "-qm", "partial")
        self.assertEqual(self.git("show", "HEAD:partial.txt"), b"first-staged\nsecond\n")
        self.assertEqual(path.read_text(), "first-staged\nsecond-unstaged\n")
        self.assertEqual(untouched.read_text(), "leave—alone\n")
        self.assertIn(b" M partial.txt", self.git("status", "--porcelain"))

    def test_unusual_filenames_binary_files_and_symlinks(self):
        name = "odd\tname\n—.txt"
        (self.repo / name).write_text("text—text")
        (self.repo / "binary").write_bytes(b"\0\xe2\x80\x94")
        (self.repo / "latin1").write_bytes(b"\xff\xe2\x80\x94")
        (self.repo / "link").symlink_to(name)
        self.git("add", "--all")
        self.script("--staged")
        self.assertEqual(self.git("show", ":" + name), b"text-text")
        self.assertEqual(self.git("show", ":binary"), b"\0\xe2\x80\x94")
        self.assertEqual(self.git("show", ":latin1"), b"\xff\xe2\x80\x94")
        self.assertEqual(self.git("show", ":link"), name.encode())
        self.assertEqual(os.readlink(self.repo / "link"), name)

    def test_renamed_file_is_normalized(self):
        (self.repo / "before.txt").write_text("hello—world")
        self.git("add", "--all")
        self.git("commit", "-qm", "base")
        self.git("mv", "before.txt", "after.txt")
        self.script("--staged")
        self.assertEqual(self.git("show", ":after.txt"), b"hello-world")

    def test_existing_hook_is_preserved(self):
        path = self.repo / ".git/hooks/pre-commit"
        original = b"#!/bin/sh\nexit 0\n"
        path.write_bytes(original)
        result = self.script("--install", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"existing pre-commit hook", result.stderr)
        self.assertEqual(path.read_bytes(), original)

    def test_custom_hooks_path_and_reinstallation(self):
        self.git("config", "core.hooksPath", ".custom-hooks")
        self.script("--install")
        path = self.repo / ".custom-hooks/pre-commit"
        self.assertTrue(path.is_file())
        self.assertTrue(os.access(path, os.X_OK))
        original = path.read_bytes()
        self.script("--install")
        self.assertEqual(path.read_bytes(), original)

    def test_direct_file_mode_does_not_change_index(self):
        path = self.repo / "direct.txt"
        path.write_text("hello—world")
        self.git("add", "direct.txt")
        self.script("direct.txt")
        self.assertEqual(path.read_text(), "hello-world")
        self.assertEqual(self.git("show", ":direct.txt"), "hello—world".encode())


if __name__ == "__main__":
    unittest.main()

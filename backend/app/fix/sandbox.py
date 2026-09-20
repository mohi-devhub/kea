"""Throwaway clone of the demo repo where a proposal is generated, tested and diffed.

Everything the fix flow does before approval happens under `<sandboxes>/<proposal_id>/`. The real
demo repo is only ever read (`git clone --local`). Paths are jailed to the sandbox checkout.
"""

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.fix.demo_repo import TEST_COMMAND
from app.fix.models import FileChange, TestRun

MAX_CHANGED_LINES = 200
ALLOWED_EDIT_PREFIX = "src/"
_SAFE_REF = re.compile(r"^[A-Za-z0-9._/-]{1,64}$")


class SandboxError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path, *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _clean_env(sandbox_root: Path) -> dict[str, str]:
    """Only what running tests needs. Never any token or key from the parent environment."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(sandbox_root),
        "PYTHONPATH": "src",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C.UTF-8",
    }


@dataclass
class Sandbox:
    root: Path
    repo: Path
    base_commit: str

    @classmethod
    def create(cls, demo_repo: Path, sandboxes: Path, proposal_id: str) -> "Sandbox":
        root = sandboxes / proposal_id
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        repo = root / "repo"
        subprocess.run(
            ["git", "clone", "--local", "-q", str(demo_repo), str(repo)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        _run(["git", "config", "user.name", "kea Bot"], repo)
        _run(["git", "config", "user.email", "bot@localhost"], repo)
        base = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        return cls(root=root, repo=repo, base_commit=base)

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def resolve(self, relative: str) -> Path:
        """Resolve a path in the checkout; reject traversal, absolute paths and symlink escapes."""
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise SandboxError(f"path not allowed: {relative!r}")
        if ".git" in Path(relative).parts:
            raise SandboxError("the .git directory is off limits")
        target = (self.repo / relative).resolve()
        if not target.is_relative_to(self.repo.resolve()):
            raise SandboxError(f"path escapes the sandbox: {relative!r}")
        return target

    def show_commit(self, ref: str) -> str:
        if not _SAFE_REF.match(ref):
            raise SandboxError("invalid ref")
        result = _run(["git", "show", "--stat", "--patch", "--no-color", ref], self.repo)
        return result.stdout[-6000:] if result.returncode == 0 else result.stderr[-400:]

    def run_tests(self, timeout: float = 60) -> TestRun:
        try:
            result = subprocess.run(
                TEST_COMMAND,
                cwd=self.repo,
                env=_clean_env(self.root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return TestRun(passed=False, summary=f"timed out after {timeout:.0f}s")
        output = (result.stdout + result.stderr).strip()
        return TestRun(
            passed=result.returncode == 0,
            summary=_summarize(output, result.returncode),
            output_tail=output[-1500:],
        )

    def diff(self) -> str:
        """The exact change against the base commit, LF-normalized. Stages files in the sandbox."""
        _run(["git", "add", "-A"], self.repo)
        raw = _run(
            ["git", "diff", "--cached", "--no-color", "--binary", self.base_commit], self.repo
        ).stdout
        return raw.replace("\r\n", "\n")

    def files_changed(self) -> list[FileChange]:
        out = _run(["git", "diff", "--cached", "--numstat", self.base_commit], self.repo).stdout
        changes = []
        for line in out.splitlines():
            added, deleted, path = line.split("\t", 2)
            changes.append(
                FileChange(
                    path=path,
                    additions=int(added) if added.isdigit() else 0,
                    deletions=int(deleted) if deleted.isdigit() else 0,
                )
            )
        return changes

    def _name_status(self) -> list[tuple[str, list[str]]]:
        out = _run(["git", "diff", "--cached", "--name-status", self.base_commit], self.repo).stdout
        rows = []
        for line in out.splitlines():
            status, *paths = line.split("\t")
            rows.append((status, paths))
        return rows

    def modified_tests(self) -> list[str]:
        """Existing test files that were modified, renamed or deleted (added tests are fine)."""
        return [
            p
            for status, paths in self._name_status()
            if not status.startswith("A")
            for p in paths
            if _is_test_path(p)
        ]

    def disallowed_edits(self) -> list[str]:
        """Changed paths outside the source tree (existing tests, CI, dotfiles, docs)."""
        return [
            p
            for status, paths in self._name_status()
            for p in paths
            if not (
                p.startswith(ALLOWED_EDIT_PREFIX) or (status.startswith("A") and _is_test_path(p))
            )
        ]


def _is_test_path(path: str) -> bool:
    name = Path(path).name
    return path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py")


def _summarize(output: str, returncode: int) -> str:
    ran = re.search(r"Ran (\d+) tests?", output)
    failed = re.search(r"FAILED \((.*?)\)", output)
    if ran and returncode == 0:
        return f"{ran.group(1)} passed"
    if ran and failed:
        return f"{failed.group(1)} of {ran.group(1)} tests"
    return output.splitlines()[-1][:120] if output else f"exit code {returncode}"


def diff_hash(diff: str) -> str:
    return "sha256:" + hashlib.sha256(diff.encode("utf-8")).hexdigest()


def changed_lines(files: list[FileChange]) -> int:
    return sum(f.additions + f.deletions for f in files)

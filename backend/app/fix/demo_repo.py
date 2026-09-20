"""Generate the tiny demo service the fix flow works on (docs/FIX_FLOW_SPEC.md section 3).

Linear history with tags: deploy-171 (harmless), deploy-181 (healthy), deploy-182 (the bad
"Optimize payment lookup path" commit that leaks connections), deploy-221 (same tree as 182).
Tests use unittest and an in-repo FakePool, so they are deterministic and need no database.
"""

import shutil
import subprocess
from pathlib import Path

TEST_COMMAND = ["python", "-m", "unittest", "discover", "-s", "tests", "-q"]

_POOL = '''"""A fake connection pool that counts outstanding connections."""

from contextlib import contextmanager


class PoolExhausted(RuntimeError):
    pass


class Connection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    def fetch(self, order_id: str) -> dict:
        return {"order_id": order_id, "status": "paid"}


class FakePool:
    def __init__(self, size: int = 4) -> None:
        self.size = size
        self.outstanding = 0

    def acquire(self) -> Connection:
        if self.outstanding >= self.size:
            raise PoolExhausted("connection pool exhausted")
        self.outstanding += 1
        return Connection(self)

    def release(self, conn: Connection) -> None:
        self.outstanding -= 1

    @contextmanager
    def connection(self):
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)
'''

_LOOKUP_HEALTHY = '''"""Payment lookup for the checkout path."""


def lookup_payments(pool, order_ids, cache=None):
    cache = cache or {}
    results = []
    with pool.connection() as conn:
        for order_id in order_ids:
            if order_id in cache:
                results.append(cache[order_id])
                continue
            results.append(conn.fetch(order_id))
    return results
'''

_LOOKUP_BAD = '''"""Payment lookup for the checkout path."""


def lookup_payments(pool, order_ids, cache=None):
    cache = cache or {}
    results = []
    for order_id in order_ids:
        conn = pool.acquire()
        if order_id in cache:
            results.append(cache[order_id])
            continue
        results.append(conn.fetch(order_id))
        pool.release(conn)
    return results
'''

_TESTS = """import unittest

from payments.lookup import lookup_payments
from payments.pool import FakePool


class LookupTests(unittest.TestCase):
    def test_lookup_returns_results(self):
        pool = FakePool()
        rows = lookup_payments(pool, ["a", "b"])
        self.assertEqual([r["order_id"] for r in rows], ["a", "b"])

    def test_lookup_serves_cached_orders(self):
        pool = FakePool()
        rows = lookup_payments(pool, ["a", "b"], cache={"a": {"order_id": "a", "status": "cached"}})
        self.assertEqual(rows[0]["status"], "cached")

    def test_lookup_releases_all_connections(self):
        pool = FakePool(size=4)
        lookup_payments(pool, ["a", "b", "a"], cache={"a": {"order_id": "a", "status": "cached"}})
        self.assertEqual(pool.outstanding, 0)


if __name__ == "__main__":
    unittest.main()
"""

_README = "# payment-service\n\nDemo service used by the kea fix flow. Not part of kea itself.\n"
_LOGGING_V1 = "LOG_FORMAT = '%(message)s'\n"
_LOGGING_V2 = "LOG_FORMAT = '%(levelname)s %(message)s'\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str, tag: str | None = None) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    if tag:
        _git(repo, "tag", tag)


def build_demo_repo(path: Path) -> Path:
    """Recreate the demo repo from scratch (idempotent)."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "kea Bot")
    _git(path, "config", "user.email", "bot@localhost")
    _git(path, "config", "commit.gpgsign", "false")
    _write(
        path,
        {
            "README.md": _README,
            "src/payments/__init__.py": "",
            "src/payments/pool.py": _POOL,
            "src/payments/lookup.py": _LOOKUP_HEALTHY,
            "src/payments/logging_conf.py": _LOGGING_V1,
            "tests/__init__.py": "",
            "tests/test_lookup.py": _TESTS,
        },
    )
    _commit(path, "Initial payment service")
    _write(path, {"src/payments/logging_conf.py": _LOGGING_V2})
    _commit(path, "Bump logging format", "deploy-171")
    _write(path, {"README.md": _README + "\nHealthy baseline.\n"})
    _commit(path, "Document baseline", "deploy-181")
    _write(path, {"src/payments/lookup.py": _LOOKUP_BAD})
    _commit(path, "Optimize payment lookup path", "deploy-182")
    _git(path, "tag", "deploy-221")
    return path


def has_tag(repo: Path, tag: str) -> bool:
    if not (repo / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0

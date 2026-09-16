#!/usr/bin/env python3
"""Lifecycle tests for the package-managed PostgreSQL secret."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "kame-postgres" / "init-secrets.sh"
TEST_TMP_ROOT = Path(os.environ.get("KAME_TEST_TMPDIR", tempfile.gettempdir()))


class SecretLifecycle(unittest.TestCase):
    def init_env(self, root: Path, derived: str) -> dict[str, str]:
        secrets = root / "secrets"
        pgadmin = root / "pgadmin"
        postgres = root / "postgres"
        for path in (secrets, pgadmin, postgres):
            path.mkdir(parents=True, exist_ok=True)

        return os.environ | {
            "APP_POSTGRES_PASSWORD": derived,
            "SECRETS_DIR": str(secrets),
            "PGADMIN_DATA_DIR": str(pgadmin),
            "POSTGRES_DATA_DIR": str(postgres),
            "POSTGRES_UID": str(os.getuid()),
            "POSTGRES_GID": str(os.getgid()),
            "PGADMIN_UID": str(os.getuid()),
            "PGADMIN_GID": str(os.getgid()),
        }

    def run_init(self, root: Path, derived: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", str(SCRIPT)],
            env=self.init_env(root, derived),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_first_start_creates_restrictive_canonical_secret_and_passfile(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            password = "a" * 64
            result = self.run_init(root, password)
            self.assertEqual(result.returncode, 0, result.stderr)
            secret = root / "secrets" / "postgres-password"
            passfile = root / "pgadmin" / "storage" / "admin_umbrel.local" / ".pgpass"
            self.assertEqual(secret.read_text(), password)
            self.assertEqual(
                passfile.read_text(),
                f"kame-postgres_postgres_1:5432:postgres:postgres:{password}\n",
            )
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o400)
            self.assertEqual(stat.S_IMODE(passfile.stat().st_mode), 0o400)

    def test_concurrent_first_start_publishes_exactly_one_canonical_secret(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            candidates = ("a" * 64, "b" * 64)
            processes = [
                subprocess.Popen(
                    ["/bin/sh", str(SCRIPT)],
                    env=self.init_env(root, candidate),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for candidate in candidates
            ]
            results = [process.communicate() for process in processes]
            self.assertEqual([process.returncode for process in processes], [0, 0], results)
            output = "".join(stdout for stdout, _ in results)
            self.assertEqual(output.count("created canonical PostgreSQL secret"), 1, results)
            self.assertEqual(output.count("preserved canonical PostgreSQL secret"), 1, results)

            secret = root / "secrets" / "postgres-password"
            winner = secret.read_text()
            self.assertIn(winner, candidates)
            third = self.run_init(root, "c" * 64)
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertIn("preserved canonical PostgreSQL secret", third.stdout)
            self.assertEqual(secret.read_text(), winner)

    def test_restart_preserves_canonical_secret_and_repairs_passfile(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            original = "a" * 64
            self.assertEqual(self.run_init(root, original).returncode, 0)
            passfile = root / "pgadmin" / "storage" / "admin_umbrel.local" / ".pgpass"
            passfile.chmod(0o600)
            passfile.write_text("stale\n")

            result = self.run_init(root, "b" * 64)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "secrets" / "postgres-password").read_text(), original)
            self.assertEqual(
                passfile.read_text(),
                f"kame-postgres_postgres_1:5432:postgres:postgres:{original}\n",
            )

    def test_existing_cluster_without_canonical_secret_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            pgdata = root / "postgres" / "18" / "docker"
            pgdata.mkdir(parents=True)
            (pgdata / "PG_VERSION").write_text("18\n")

            result = self.run_init(root, "a" * 64)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "secrets" / "postgres-password").exists())

    def test_malformed_existing_secret_is_rejected_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            secret_dir = root / "secrets"
            secret_dir.mkdir(parents=True)
            secret = secret_dir / "postgres-password"
            secret.write_text("short")

            result = self.run_init(root, "a" * 64)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(secret.read_text(), "short")

    def test_symbolic_link_secret_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            secret_dir = root / "secrets"
            secret_dir.mkdir(parents=True)
            target = root / "outside-secret"
            target.write_text("do-not-touch")
            (secret_dir / "postgres-password").symlink_to(target)

            result = self.run_init(root, "a" * 64)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "do-not-touch")

    def test_valid_restored_secret_has_permissions_repaired(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            secret_dir = root / "secrets"
            secret_dir.mkdir(parents=True)
            secret = secret_dir / "postgres-password"
            secret.write_text("a" * 64)
            secret.chmod(0o666)

            result = self.run_init(root, "b" * 64)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(secret.read_text(), "a" * 64)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
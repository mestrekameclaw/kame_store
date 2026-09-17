#!/usr/bin/env python3
"""Contract tests for the PostgreSQL + pgAdmin Umbrel package."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "kame-postgres"


class PostgresPackageContract(unittest.TestCase):
    def test_required_package_files_exist(self) -> None:
        required = {
            "umbrel-app.yml",
            "docker-compose.yml",
            "exports.sh",
            "hooks/pre-start",
            "servers.json",
            "README.md",
            "data/postgres/.gitkeep",
            "data/pgadmin/.gitkeep",
            "data/secrets/.gitkeep",
        }
        missing = sorted(path for path in required if not (APP / path).is_file())
        self.assertEqual(missing, [], f"missing package files: {missing}")

    def test_manifest_exposes_recoverable_initial_credentials(self) -> None:
        manifest = (APP / "umbrel-app.yml").read_text()
        self.assertRegex(manifest, r"(?m)^id:\s*kame-postgres\s*$")
        self.assertRegex(manifest, r"(?m)^defaultUsername:\s*[\"']?admin@umbrel\.local[\"']?\s*$")
        self.assertRegex(manifest, r"(?m)^defaultPassword:\s*[\"']{2}\s*$")
        self.assertRegex(manifest, r"(?m)^deterministicPassword:\s*true\s*$")

    def test_images_are_versioned_and_digest_pinned(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertRegex(
            compose,
            r"(?m)^\s*image:\s*postgres:[^\s@]+@sha256:[0-9a-f]{64}\s*$",
        )
        self.assertRegex(
            compose,
            r"(?m)^\s*image:\s*dpage/pgadmin4:[^\s@]+@sha256:[0-9a-f]{64}\s*$",
        )
        self.assertNotIn(":latest", compose)

    def test_secrets_are_generated_by_umbrel_not_committed(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        exports = (APP / "exports.sh").read_text()
        self.assertIn("APP_POSTGRES_PASSWORD", exports)
        self.assertIn("derive_entropy", exports)
        self.assertIn("POSTGRES_PASSWORD_FILE: /run/secrets/postgres-password", compose)
        self.assertNotIn("POSTGRES_PASSWORD: ${APP_PASSWORD}", compose)
        self.assertIn("PGADMIN_DEFAULT_PASSWORD: ${APP_PASSWORD}", compose)
        self.assertIn("APP_POSTGRES_PASSWORD: ${APP_POSTGRES_PASSWORD}", compose)
        self.assertNotIn("PGPASS_FILE:", compose)
        self.assertFalse(any(APP.rglob(".env")), "real .env files must not be packaged")
        self.assertNotRegex(compose, r"(?m)^\s*(?:POSTGRES_PASSWORD|PGADMIN_DEFAULT_PASSWORD):\s*(?!\$\{APP_PASSWORD\})\S+")

    def test_database_authentication_is_hardened(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertIn('POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256 --data-checksums"', compose)
        self.assertIn("password_encryption=scram-sha-256", compose)
        self.assertIn("PGDATA: /var/lib/postgresql/18/docker", compose)
        self.assertNotIn("POSTGRES_HOST_AUTH_METHOD: trust", compose)

    def test_postgres_healthcheck_authenticates_and_runs_a_query(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertIn("psql -h 127.0.0.1", compose)
        self.assertIn("SELECT 1", compose)
        self.assertNotIn("pg_isready", compose)

    def test_pgadmin_runs_as_unprivileged_app_user_after_setup(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertIn('PUID: "1000"', compose)
        self.assertIn('PGID: "1000"', compose)
        self.assertIn('PGADMIN_DISABLE_POSTFIX: "1"', compose)
        self.assertIn('PGADMIN_CONFIG_UPGRADE_CHECK_ENABLED: "False"', compose)

    def test_database_and_pgadmin_state_are_persistent(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        # PostgreSQL 18+ deliberately mounts the parent directory so future
        # major-version migrations can coexist under versioned PGDATA paths.
        self.assertIn("${APP_DATA_DIR}/data/postgres:/var/lib/postgresql", compose)
        self.assertIn("${APP_DATA_DIR}/data/pgadmin:/var/lib/pgadmin", compose)
        self.assertIn("${APP_DATA_DIR}/data/secrets:/run/secrets:ro", compose)
        self.assertIn("${APP_DATA_DIR}/hooks/pre-start:/app/init-secrets.sh:ro", compose)
        self.assertIn('RUN_IN_INIT_CONTAINER: "1"', compose)

    def test_postgres_is_not_published_to_the_host(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertNotRegex(compose, r"[\"']?(?:0\.0\.0\.0:)?5432:5432[\"']?")
        self.assertIn('expose:\n      - "5432"', compose)

    def test_umbrel_proxy_protects_pgadmin(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        self.assertIn("APP_HOST: kame-postgres_pgadmin_1", compose)
        self.assertIn("APP_PORT: 8080", compose)
        self.assertIn('PGADMIN_LISTEN_PORT: "8080"', compose)
        self.assertNotIn("PROXY_AUTH_ADD", compose)

    def test_no_high_risk_container_privileges(self) -> None:
        compose = (APP / "docker-compose.yml").read_text()
        forbidden = ("privileged:", "network_mode: host", "/var/run/docker.sock", "pid: host")
        for value in forbidden:
            self.assertNotIn(value, compose)

    def test_pgadmin_has_pre_registered_secret_free_server(self) -> None:
        servers = json.loads((APP / "servers.json").read_text())
        server = servers["Servers"]["1"]
        self.assertEqual(server["Host"], "kame-postgres_postgres_1")
        self.assertEqual(server["Port"], 5432)
        self.assertEqual(server["MaintenanceDB"], "postgres")
        self.assertEqual(server["Username"], "postgres")
        self.assertEqual(server["ConnectionParameters"]["passfile"], ".pgpass")
        serialized = json.dumps(servers).lower()
        self.assertNotIn("password", serialized)

    def test_managed_passfile_authenticates_the_admin_role_in_all_databases(self) -> None:
        initializer = (APP / "hooks" / "pre-start").read_text()
        self.assertIn(
            'kame-postgres_postgres_1:5432:*:postgres:${canonical_password}',
            initializer,
        )
        self.assertNotIn(
            'kame-postgres_postgres_1:5432:postgres:postgres:${canonical_password}',
            initializer,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

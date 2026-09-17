# PostgreSQL + pgAdmin for Umbrel

A Kame App Store package combining PostgreSQL 18 and pgAdmin 4. The two upstream images are versioned, digest-pinned, and support both `linux/amd64` and `linux/arm64`.

## First login

Umbrel generates a stable password for this app and displays it in the app's **Credentials** panel.

- pgAdmin email: `admin@umbrel.local`
- pgAdmin password: the password displayed by Umbrel
- PostgreSQL user: `postgres`
- PostgreSQL database: `postgres`
- PostgreSQL password: a separate per-install secret registered automatically

The bundled server appears automatically in pgAdmin under **Kame → PostgreSQL on Umbrel** and uses a restrictive `.pgpass` file generated locally from the canonical database secret. Its entry is scoped to the bundled PostgreSQL host, port, and `postgres` administrative role, while accepting every database on that server so newly created databases can be browsed. The secret is published atomically without overwriting an existing value on the first clean installation. Every full app start or update preserves it and safely repairs pgAdmin's passfile; an isolated automatic restart of only the pgAdmin container reuses the already-persistent passfile. Opening the server does not require copying the PostgreSQL superuser password into the browser.

pgAdmin 9 still asks for the database password the first time you connect, even when a `.pgpass` file is present: it is protecting the saved credential behind its master password. Type the passphrase stored in `data/secrets/postgres-password` once and let pgAdmin save it, or leave it unsaved and rely on the managed passfile for non-interactive clients.

Changing the pgAdmin password is optional. If you change it, Umbrel will still display the original generated credential; save the replacement in your password manager. The PostgreSQL superuser secret is intentionally different and should normally be left for administration through pgAdmin. Create separate roles instead of sharing it with client applications.

## Network access

PostgreSQL is available to other Umbrel apps at:

```text
host: kame-postgres_postgres_1
port: 5432
database: postgres
user: postgres
```

Port `5432` is **not published to the Umbrel host, LAN, or internet**. This is intentional: Umbrel's shared Docker network is not a trust boundary, and a database should not be exposed more broadly without TLS, firewall rules, and dedicated non-superuser roles.

Create a separate PostgreSQL role and database for every client app. Do not give normal applications the `postgres` superuser credential.

## Persistence and updates

Persistent state lives below Umbrel's app data directory:

- `data/postgres/` — databases, roles, WAL, and PostgreSQL configuration
- `data/pgadmin/` — pgAdmin users, settings, registered servers, and saved credentials
- `data/secrets/` — restrictive, canonical PostgreSQL bootstrap secret

Normal container restarts and app updates preserve all three directories. PostgreSQL 18 stores its cluster under the versioned `/var/lib/postgresql/18/docker` path inside the mounted parent directory.

Never change the released app id (`kame-postgres`): Umbrel includes it when deriving both credentials. `PGDATA` is explicitly locked to `/var/lib/postgresql/18/docker`, so an accidental PostgreSQL 19 image cannot silently initialize a new empty cluster. A planned major upgrade still requires a tested `pg_upgrade` or dump/restore migration.

If an existing PostgreSQL cluster is present but its canonical secret is missing or malformed, startup fails closed instead of inventing a replacement that could lock out the database.

pgAdmin upgrades may migrate its configuration database forward. Back up `data/pgadmin/` before upgrading pgAdmin because downgrading to an older image may require restoring the matching pre-upgrade data.

## Backups

Before significant changes, create a logical backup with pgAdmin's Backup tool or `pg_dump`. An app update is not a backup. Uninstalling with data deletion, deleting the app data directory, or resetting Umbrel without restoring its seed can destroy data or invalidate the generated initial credential.

## Security choices

- No credentials or `.env` files are committed.
- Umbrel derives separate purpose-specific secrets for pgAdmin and PostgreSQL.
- PostgreSQL host authentication uses SCRAM-SHA-256.
- PostgreSQL data checksums are enabled at initialization.
- PostgreSQL health checks authenticate over TCP and execute `SELECT 1`.
- pgAdmin is protected by both Umbrel's app proxy and its own login.
- pgAdmin disables Postfix and update telemetry/checks.
- Long-running pgAdmin processes run as Umbrel's unprivileged uid/gid `1000:1000`.
- Neither service receives privileged mode, host networking, or the Docker socket.

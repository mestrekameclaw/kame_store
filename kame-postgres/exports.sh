# Derive an install-specific PostgreSQL superuser password separately from
# Umbrel's user-facing APP_PASSWORD used to sign in to pgAdmin.
export APP_POSTGRES_PASSWORD="$(derive_entropy "${app_entropy_identifier}-POSTGRES-PASSWORD" | head -c 64)"

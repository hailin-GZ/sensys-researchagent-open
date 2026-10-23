# Deployment

The repository contains application source, not production infrastructure or an existing service backup. Install it on infrastructure you control and provide new credentials. Do not reuse another installation's database, keys, account exports, or browser profile.

1. Create a dedicated unprivileged service user and a private state directory outside the source checkout.
2. Install the pinned Python dependencies in a virtual environment and install Chromium for that service user if browser capture is required.
3. Create a private encryption key. Configure `SENSYS_SECRET_KEY_FILE`, `SENSYS_MODEL`, `SENSYS_DATA_DIR`, `SENSYS_RUNTIME_DIR`, and optionally `SENSYS_SETTINGS_FILE` consistently for every process.
4. Initialize the administrator on the fresh database. Configure and explicitly test your own provider, then create application user access keys with appropriate quotas.
5. Supervise the research worker, dialog worker, user service, and administrator service as separate processes. Run from the source checkout. The HTTP servers bind to loopback by default.
6. Place an HTTPS reverse proxy in front of the user service. Keep the administrator service private or restrict it to trusted network access. Configure `SENSYS_PUBLIC_ORIGIN` and `SENSYS_ADMIN_ORIGIN` to the exact HTTPS origins; set `SENSYS_SECURE_COOKIE=1`.
7. Keep `SENSYS_ALLOW_BENCHMARK_DNS=0` in production. Do not disable TLS validation, host checks, or CSRF checks. Do not automatically retry model or state-changing HTTP requests.
8. Verify encryption, separate authentication, quota settlement, cross-user isolation, original-source downloads, stop/resume behavior, and graceful shutdown with synthetic data before accepting real users.
9. Maintain encrypted, access-restricted backups of private state and its encryption key. Test restoration separately. A code rollback must not overwrite newer user records with an old database.

Administrator budget edits are persisted runtime configuration, not source-code changes. Research tasks take a snapshot when they start; changing a tier does not reset accumulated usage or alter a running task's allowance.

The application can make billable provider requests. Offline regression checks do not certify every provider, public platform, concurrency level, or deployment environment. Verify the exact integrations and workload you intend to operate.

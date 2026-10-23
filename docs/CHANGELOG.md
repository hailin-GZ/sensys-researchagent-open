# Public distribution history

## v2.1.1-public

- Use the standard Playwright browser cache on Windows as well as Unix, while retaining the explicit executable override.
- Add regression checks for explicit, default-cache, and missing browser paths.
- Preserve the initial audited public snapshot as `v2.1.0-public`. The application data/configuration format remains compatible with 2.1.0.

## v2.1.0-public

- Publish the sanitized English source distribution, English user/admin interfaces, provider-neutral deployment configuration, and setup documentation.
- Exclude all private runtime state, credentials, installed SDKs, user records, and production infrastructure files.
- Retain third-party licenses, document local example redactions, and validate bundled method integrity.

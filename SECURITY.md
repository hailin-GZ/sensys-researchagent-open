# Security and private state

Do not submit credentials, personal records, or a live database in a public issue. Use GitHub private vulnerability reporting if the repository offers it; otherwise submit a minimal synthetic reproduction without sensitive material.

This source distribution intentionally excludes API keys and provider profiles, administrator and user access credentials, encrypted credential values, encryption keys, SDK installations and account caches, databases and backups, conversations, uploaded documents, research results, browser profiles, server certificates, SSH material, logs, and production infrastructure settings.

## Operating an installation

- Configure your own provider credentials through the administrator console. Never put provider credentials in browser code, prompts, a repository URL, or committed configuration.
- Keep the administrator service private. Use separate HTTPS origins, secure cookies, origin checks, CSRF validation, and a reverse proxy for remote deployment.
- Use a private encryption key owned by the service user with mode `0600` on Unix. Windows also supports account-bound credential encryption; those encrypted values are not portable between accounts or operating systems.
- Restrict filesystem permissions and backup access. Encrypting a provider credential does not make an entire conversation database safe to publish.
- Treat user messages, downloaded pages, attachments, method documents, and tool output as untrusted data. Keep source evidence distinct from executable instructions.
- Respect public-source access rules, consent, rate limits, and platform terms. Do not bypass logins, verification challenges, or private-network protections.
- Budget settings limit the application workload. Providers and platforms enforce their own independent limits.

## Preparing a public change

Use a separate source-only directory. Scan filenames and bytes, known private values and their encoded variants, current files, every historical Git blob, and release archives. A `.gitignore` does not remove already committed content. Do not disable scanner rules simply to obtain a clean result.

Before publishing, run the included source auditor and an independent secret scanner. After publication, clone or download the exact commit again, compare its complete file hashes, and repeat both checks. Local audits are evidence about the checked revision, not a guarantee against every unknown secret format or future contribution.

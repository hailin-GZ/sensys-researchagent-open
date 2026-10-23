# SENSYS Research Agent

An evidence-oriented assistant for market insights and user research. Chat about a question, authorize research when ready, and inspect the sources behind the resulting analysis.

## Features

- Separate conversational and research workers: ordinary chat does not automatically start an investigation.
- Standard and deep research budgets, editable in the administrator console without a fixed business maximum.
- Persistent research findings, source archives, exact quotations, independent review, and explicit evidence gaps.
- Stop and resume controls that retain acquired materials and previously reviewed reports.
- Separate user and administrator authentication, account-scoped downloads, quota accounting, and encrypted provider credentials.
- An English user workspace and administrator console, with responsive layouts and downloadable source packages.
- A 760-record capability catalog, 247 bundled method documents, 23 function interfaces, and 21 public-data routes. Catalog entries are not a claim that every service is installed, authenticated, or accessible.

This repository is a sanitized English source distribution. It does not include a hosted service, working API credentials, access keys, user accounts, conversations, research archives, production databases, or deployment secrets. You must configure your own provider and create your own accounts.

## Quick start

Python 3.12 or newer is required. The existing transport expects a Responses-compatible provider supporting structured output, streaming, tool calls, and the configured reasoning options. Model compatibility is not implied by a provider accepting a connection.

```bash
python -m venv runtime/.venv
# Linux/macOS:
source runtime/.venv/bin/activate
# Windows PowerShell instead:
# runtime/.venv/Scripts/Activate.ps1
python -m pip install -r agent/requirements.txt
python -m playwright install chromium
python scripts/setup_local.py
```

The setup command creates a new private encryption key and prints environment-variable assignments, not the key. Apply those assignments in every process that runs this installation. Choose your provider's exact model identifier:

```bash
export SENSYS_MODEL=YOUR_MODEL_ID
export SENSYS_SECRET_KEY_FILE=/absolute/path/to/your/checkout/runtime/private/secret.key
```

PowerShell equivalents:

```powershell
$env:SENSYS_MODEL = 'YOUR_MODEL_ID'
$env:SENSYS_SECRET_KEY_FILE = (Resolve-Path runtime/private/secret.key).Path
```

Initialize a fresh administrator once:

```bash
python admin/server.py init
```

Save the generated administrator credential privately. Initialization refuses to replace an existing administrator. Then run these four commands in separate terminals, with the same environment:

```bash
python -m agent worker
python -m agent dialog-worker
python web-redesign/server.py serve
python admin/server.py serve
```

Open the user workspace at `http://127.0.0.1:8766/` and the administrator console at `http://127.0.0.1:8767/`. Windows users may use `start-agent.ps1` after configuring the environment and initializing the administrator.

In the administrator console, add your provider configuration, run its explicit connection/basic-call checks, and enable it after the checks pass. Those checks make real provider requests and may incur charges. Create a user access key and assign its quota. Signing in as a user uses that access key, not the provider API key.

## Configuration

`agent/settings.json` supplies portable defaults. `SENSYS_SETTINGS_FILE` selects a private runtime settings file. `SENSYS_MODEL` overrides the deployment model identifier; it must match the active provider profile. Use `SENSYS_DATA_DIR` and `SENSYS_RUNTIME_DIR` to place private state outside the checkout.

Administrators can edit both research tiers in the console. Changes affect new tasks; existing tasks retain their budget snapshot. Continuations receive a new turn allowance while preserving accumulated usage. Account and daily quotas remain independent limits. No research result count is a guarantee of completeness.

Native provider web search is optional and disabled in this public distribution. Enable `native_web_search` only after verifying that your provider supports it. The ordinary public-source acquisition routes remain available. Browser capture requires a separately installed Chromium executable; downloaded browser binaries are not distributed here.

For deployment guidance, see [Deployment](docs/DEPLOYMENT.md). For privacy and security, see [Security](SECURITY.md). For third-party licenses and local documentation edits, see [Third-party notices](THIRD_PARTY_NOTICES.md).

## Offline checks

```bash
python -m unittest discover -s agent/tests -p "test*.py"
python -m unittest discover -s skills/sensys-market-research/tests -p "test*.py"
python -m unittest discover -s admin -p "test*.py"
python -m unittest discover -s web-redesign -p "test_access.py"
python scripts/audit_public_source.py .
```

The regression suite uses synthetic or anonymized fixtures and mocked provider calls. Some fixtures preserve multilingual matching as Unicode escapes; the interface, documentation, prompts, and default report instructions are English. Offline checks do not establish live provider or source availability. Public platforms may rate-limit, require separate permission, or return incomplete content; failures and uncertainty must remain explicit.

## License

Original project code is available under the [MIT License](LICENSE). Bundled third-party method documents retain their own licenses and attribution. A method mentioning a paid service, SDK, connector, or account does not bundle that SDK, grant access, or authorize its use.

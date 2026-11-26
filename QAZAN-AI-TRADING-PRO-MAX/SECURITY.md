# Security Policy & Secret Remediation Guide — QAZAN-AI-TRADING-PRO-MAX

## Zero-Secret Architecture
QAZAN-AI-TRADING-PRO-MAX is engineered to operate with **zero paid API keys** and **zero cloud-platform credentials**:
- Public market data uses keyless REST/WebSocket endpoints (`api.binance.com`, `fapi.binance.com`, `www.okx.com`, `api.coingecko.com`, `api.coinpaprika.com`).
- Macro economic data uses public official central bank and government feeds (`federalreserve.gov`, `bls.gov`, `ecb.europa.eu`, `bankofengland.co.uk`, ForexFactory public calendar).
- Machine learning inference (`Scikit-learn`, `XGBoost`) executes strictly locally on the backend host.

## Secret Prevention Rules
1. Never commit `.env`, `.env.local`, `.env.production`, `*.keystore`, `*.jks`, or runtime SQLite `*.db` files. All are ignored in `.gitignore` and excluded in `scripts/create_project_backup.py`.
2. Store Android release signing variables (`QAZAN_KEYSTORE_FILE`, `QAZAN_KEYSTORE_PASSWORD`, `QAZAN_KEY_ALIAS`, `QAZAN_KEY_PASSWORD`) exclusively in local shell exports or encrypted CI/CD Secrets.
3. Never hardcode private hosting domains or platform preview URLs in source files; configure `VITE_QAZAN_NATIVE_BACKEND_ORIGIN` at build time or inside the in-app Settings UI.

## What to Do If a Secret or Keystore Is Exposed
If a secret, `.env` file, or `.keystore` is ever committed accidentally to a Git repository:
1. **Revoke & Rotate Immediately**: Regenerate any exposed API token, password, or signing key immediately (treat exposed secrets as permanently compromised).
2. **Purge From Git History**: Remove the file from all commits using `git filter-repo --path <secret-file> --invert-paths` (do not just delete it in a new commit and push, as it would remain in Git history).
3. **Force-Push & Invalidate Caches**: Force-push the rewritten branches/tags and invalidate downstream CI caches or artifact caches.
4. **Verify Clean Workspace**: Re-run `python3 -m pytest backend/tests/test_release_open_source.py -v` before pushing again.

## Responsible Disclosure
Please report security issues privately through GitHub Security Advisories on the repository rather than opening public issues with exploit details.

# ODRegister — Annual Open Data Plan Registry

- Application source root: `04.Development/`.
- Database engine: standard PostgreSQL 16. Local schema and migrations are implemented; an online PostgreSQL service has not yet been provisioned.
- Backend: Python 3.13 / FastAPI / SQLAlchemy / psycopg. Frontend: React / TypeScript / Vite.
- This is a curated source upload, not a production deployment or a complete IT&E installation package.
- Database model: `04.Development/backend/models.py`. Frozen Alembic/SQL revisions: `04.Development/backend/migrations/`, current head `l1_0002`.
- Migration files describe the schema; provisioning database roles/grants and applying migrations require a separate authorized installation procedure. Application build does not create a database or seed accounts.
- Hosted PostgreSQL provider, region and connection are pending. Neon is only an optional PostgreSQL hosting provider; no alternative database engine is required.
- Private runtime configuration: `DATABASE_URL`, `L1_ENV`, `L1_APP_ORIGIN`. Supply values through private environment settings; never commit credentials.
- UI build from the application root: `python build.py`. The build installs locked frontend dependencies and generates `web/` plus `backend/web_manifest.json`.
- Automatic Git deployments are disabled in the root and application Vercel configuration pending manual review and actual project settings verification. See [Vercel Git configuration](https://vercel.com/docs/project-configuration/git-configuration).
- Excluded: local databases, dumps, credentials, private customer documents, manual-test data and generated UI bundles.
- This source does not contain the project internal development ledger, local test fixture utilities or a full handover package. The working project retains these separately.

## Preview operator tools

- Explicit remote preview installers and credential tests are under `04.Development/scripts/db/` and `04.Development/tests/db/`.
- The synthetic seed is authorized only for the named, isolated preview. It uses immutable generated data, preserves passwords on re-entry and refuses unrecognized or populated targets. Never use it as a production reference import.
- [Remote preview installation guide](docs/REMOTE_PREVIEW_DB_EN.md).
- Updated app TLS handling resolves system CA bundles across macOS/Linux while preserving hostname verification.
- The temporary Vercel Function region is `fra1`; final operating provider/region remain undecided.
- Deployment publication requires the account holder's Vercel identity verification. Staging these files does not mean a deployment has succeeded.

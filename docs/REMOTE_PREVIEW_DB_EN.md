# Remote preview PostgreSQL installation and verification

- Verified: 21 November 2026; task L1-P6-01; isolated demonstration environment.
- User authorized a free temporary configuration. Neon / Frankfurt is a temporary implementation choice; the final operating provider and region remain undecided.
- Vercel team: SRB (`srb24`), Hobby. Resource: `odregister-preview`, Neon Free, Frankfurt (`fra1`). Auth and Realtime are disabled.
- Actual server: PostgreSQL 18.7, provisioned by the Vercel native integration. Local development remains PostgreSQL 16.15. Do not label the remote instance as PostgreSQL 16.
- The application still uses standard PostgreSQL through SQLAlchemy/psycopg. No Neon SDK or provider authentication was added to the runtime.

## Private input and execution

Run from `04.Development/` with its locked Python environment. The operator tools deliberately accept only this named preview resource; they do not retarget local, shared, production or IT&E databases.

- `.data/online-postgres/provider.json`: private provider connection configuration, captured from the authorized dashboard without printing it. Requires `provider`, `resource` and `connections` with `DATABASE_URL` and `DATABASE_URL_UNPOOLED` keys. Never commit this file or paste its values into messages.
- `.data/online-postgres/roles.json`: installation identity, private resume marker and three generated login secrets. The schema owner cannot log in. Preserve this file to resume; never replace it to reset a populated instance.
- `.data/online-postgres/runtime.json`: least-privilege app connection and proposed runtime settings. All private inputs/outputs are mode 0600 under a mode-0700 directory; credential writes publish atomically.
- A named, empty, isolated preview database is required for the first installation. Existing unrecognized roles, tables or schema markers are rejected. There is no reset or downgrade command.

```bash
uv run --offline python -m scripts.db.remote install
uv run --offline python -m scripts.db.remote verify
uv run --offline python -m scripts.db.remote_acceptance
uv run --offline pytest -q tests/db/test_remote_config.py
```

- `install` provisions explicit SQL roles, applies frozen Alembic revisions through `l1_0002`, then verifies the structure and privileges. A recognized re-entry preserves credentials and business rows.
- `verify` compares the actual database to application metadata and checks the complete app/backup privilege matrix.
- `remote_acceptance` checks constraints, actual denied writes/DDL, installation re-entry, and local ASGI requests against the real remote database. It does not deploy an HTTP endpoint.
- Tool errors contain only sanitized types/SQLSTATE. Never enable raw driver diagnostics, SQL parameter logging or shell tracing around secret inputs.

## Installed structure and privileges

- Business schema `layer1`: 15 tables, 124 columns, 50 indexes, 15 primary keys, 22 foreign keys, 10 unique constraints and 52 check constraints.
- PostgreSQL 18 also represents 95 NOT NULL constraints in the catalog. These are separate from the 52 check constraints, and do not imply a model change.
- Metadata comparison: zero structural differences; deferred planned-dataset order constraint verified.
- Dedicated SQL-created roles: `layer1_preview_owner`, `layer1_preview_migrator`, `layer1_preview_app`, `layer1_preview_backup`. All four lack superuser/createdb/createrole/replication/bypass-RLS privileges. App and backup are not members of the owner or `neon_superuser` roles.
- App permissions match the existing reviewed 15-table policy; revision/audit tables allow SELECT/INSERT only. Backup has SELECT only. Effective privileges verified across 15 tables × 7 operations × 2 roles = 210 combinations.
- Actual app CREATE TABLE, app audit UPDATE and backup account DELETE were denied with SQLSTATE 42501. No probe table or business row was left behind.
- Empty schema installed; zero business rows. No local manual-test accounts, private user inputs, production reference data or synthetic demo seed was copied remotely.

## Runtime connection

- TLS uses `verify-full` and a CA bundle at `/etc/ssl/cert.pem` on the current Mac. A different operator OS must supply an appropriate CA bundle before using these operator tools.
- The provider's pooled endpoint rejected the app's existing startup `options`. The prepared runtime uses the direct app-role connection and SQLAlchemy NullPool, preserving application code. The provider owner login must not become the application's `DATABASE_URL`.
- Proposed settings: `L1_ENV=preview`, `L1_DB_POOL_MODE=null`, `L1_CONNECT_TIMEOUT=5`. Set `L1_APP_ORIGIN` to the actual HTTPS deployment origin; its current private template value is intentionally unset.
- Do not automatically attach the provider integration's owner-level environment values to the application. Use only the app-role URL from the private runtime file.
- Direct connection capacity, concurrency and load acceptance remain later verification work.

## Limits and next work

- The real app role returned expected results for `/api/runtime`, `/api/health`, `/api/public/cycles`, `/api/auth/me` and `/api/admin/monitoring/2027` through local ASGI requests. These are not public Vercel URL tests or full business-flow regression.
- No first administrator or reference/demo data has been provisioned remotely. No Vercel application has been deployed. Local manual review remains uncompleted unless separately recorded by the user.
- Prior 681-case local regression evidence was not rerun for this infrastructure step. New operator credential/resume tests: 8 passing cases.
- A PostgreSQL 18-compatible dump client is required to back up this remote instance. Existing local PostgreSQL 16 dump/restore scripts are local-only; no remote backup/restore or cross-major restore acceptance is claimed.
- Existing GitHub application source commit: `d3ac91257d53148a8ee8a464e8e8776aa250c800`. The new operator scripts currently reside in the local workspace; include them in a reviewed later source/handover synchronization.
- Next task L1-P6-02: configure preview bootstrap and approved reference/demo inputs, apply private Vercel app settings, deploy, then verify the remote workflow. Mac-off verification and user acceptance remain separate evidence.

Sources: [Neon SQL-role privilege behavior](https://neon.com/docs/manage/roles), [managed Postgres compatibility](https://neon.com/docs/reference/compatibility).

## P6-02 preparation checkpoint

- The authorized isolated preview now contains 105 synthetic seed rows and five usable seeded logins. `scripts/db/remote_demo.py` prepares this data only for the recognized preview; re-entry preserves user data/passwords. It does not copy local manual-test inputs.
- The updated runtime resolves a system CA bundle across macOS/Linux while retaining hostname verification. Four certificate tests and fifteen existing API foundation tests pass; staged source has not yet replaced GitHub commit d3ac912.
- The Vercel Deploy action requires an emailed six-digit identity code. The operator handed the browser to the account holder; public deployment, final hostname and remote workflow verification remain pending.

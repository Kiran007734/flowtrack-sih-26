# Phase 2 test report

**Report status:** partial verification complete. This report records only executed commands. Docker, real PostgreSQL, Redis/Celery worker, and native Vite/Vitest checks are not counted as passing. The strict acceptance audit is in `phase-2-acceptance-matrix.md`.

| Test group | Command | Exit | Run | Passed | Failed | Skipped | Actual result / dependency |
|---|---|---:|---:|---:|---:|---:|---|
| Docker availability | `docker --version`; `docker compose version` | 1 | 0 | 0 | 0 | 0 | Docker is unavailable. Compose build, service health, PostgreSQL/Redis integration, broker execution, and restart-persistence checks are blocked. |
| Backend dependencies | `uv venv --python 3.12 .venv`; `uv pip install --python .venv\\Scripts\\python.exe -e ".[dev]"` | 0 | 0 | 0 | 0 | 0 | Installed under uv-managed CPython 3.12.13; `uv.lock` generated. |
| Backend lint/format | `.\\.venv\\Scripts\\ruff.exe format app alembic tests`; `.\\.venv\\Scripts\\ruff.exe check app alembic tests` | 0 | 0 | 0 | 0 | 0 | All checks passed. |
| Backend unit/API/security | `.\\.venv\\Scripts\\pytest.exe -q` | 0 | 13 | 12 | 0 | 1 | The PostgreSQL-contract test was explicitly skipped because `TEST_POSTGRES_DATABASE_URL` is unavailable. Passing tests use isolated SQLite only for portable host service/API coverage, not PostgreSQL proof. |
| Alembic offline PostgreSQL SQL | `python -m alembic upgrade head --sql` | 0 | 0 | 0 | 0 | 0 | Generated PostgreSQL-dialect SQL for revision `0001_phase2_foundation`. |
| Alembic migration mechanics | `DATABASE_URL=sqlite+pysqlite:///./migration-check.sqlite3 python -m alembic upgrade head`; `alembic current` | 0 | 0 | 0 | 0 | 0 | Reached `0001_phase2_foundation (head)`; this is not a substitute for a fresh real PostgreSQL migration. |
| OpenAPI | See exact command below | 0 | 0 | 0 | 0 | 0 | OpenAPI 3.1.0 generated with 22 paths; the application create operation declares required `Idempotency-Key`. |
| Compose manifest syntax | See exact command below | 0 | 0 | 0 | 0 | 0 | Parsed the seven declared services, including the explicit short-lived `migrate` service. This is syntax-only validation, not a Docker execution result. |
| Frontend dependency resolution | `npm install --ignore-scripts --no-audit --no-fund` | 0 | 0 | 0 | 0 | 0 | `package-lock.json` generated. Scripts were skipped because the host blocks native Node modules. |
| Frontend lint | `npm run lint` | 0 | 0 | 0 | 0 | 0 | ESLint passed with no warnings/errors. |
| Frontend type check | `npm run typecheck` | 0 | 0 | 0 | 0 | 0 | Strict TypeScript checking passed. |
| Frontend unit/component | `npm run test` | 1 | 0 | 0 | 0 | 0 | Windows Application Control blocked `rollup.win32-x64-msvc.node`; Vitest did not start, so its two test files are not counted as executed. |
| Frontend production build | `npm run build` | 1 | 0 | 0 | 0 | 0 | TypeScript stage passed, then the same policy blocked Rollup before Vite build. |

## Phase 2.1 update — executed 2026-10-27

- Backend Ruff format/check passed; `pytest -q` ran 14 tests: **13 passed, 1 skipped**. The skipped PostgreSQL contract test needs `TEST_POSTGRES_DATABASE_URL`.
- Revision `0002_command_idempotency` persists replay-safe command responses. A fresh SQLite migration reached that revision; offline PostgreSQL SQL generation completed through it. This is not evidence of a live PostgreSQL migration.
- A fresh SQLite seed database ran `python -m app.db.seed` twice; both runs reported 3 applications, 2 institutions, 2 regions, and 7 users. The final database had 4 workflow versions.
- `npm run typecheck` and `npm run lint` passed. `npm run test` and `npm run build` both exited 1 before executing tests/build because Windows Application Control blocked `@rollup/rollup-win32-x64-msvc`.

## Required verification before operational handoff

On a Docker-capable host, build Compose; run the short-lived `migrate` service against a fresh PostgreSQL database; run the seed command twice; start API, worker, scheduler, and web; call readiness; queue the Celery diagnostic task; submit an application while workers are stopped; restart the worker; verify persisted PostgreSQL state and one idempotent in-app notification. Then run Vitest and the production build where native Rollup execution is permitted. Those results must be added here before calling the stack fully operational.

## Exact latest host-only commands

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -c "from app.main import app; spec=app.openapi(); operation=spec['paths']['/api/v1/applications']['post']; header=next(p for p in operation['parameters'] if p['name']=='Idempotency-Key'); print('OpenAPI', spec['openapi'], 'paths', len(spec['paths']), 'idempotency_required', header['required'])"
```

```powershell
Set-Location ..
@'
from pathlib import Path
import yaml
root = Path.cwd()
compose = yaml.safe_load((root / 'docker-compose.yml').read_text(encoding='utf-8'))
assert set(compose['services']) == {'postgres', 'redis', 'migrate', 'api', 'worker', 'scheduler', 'web'}
assert compose['services']['migrate']['profiles'] == ['tools']
assert 'POSTGRES_APP_USER' in compose['services']['api']['environment']['DATABASE_URL']
print('compose YAML parsed; services:', ', '.join(compose['services']))
'@ | .\backend\.venv\Scripts\python.exe -
```

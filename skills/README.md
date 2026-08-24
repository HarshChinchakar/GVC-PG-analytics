# Skills — PG Logistics & Rent Tally Portal

One skill per build pointer, pulled from GitHub as raw `SKILL.md` files.
Stack these are chosen for: **Next.js (Vercel) → FastAPI (Render) → Supabase Postgres + Supabase Auth**.

| # | File | Pointer it covers | Source |
|---|------|-------------------|--------|
| 01 | `01-database-schema-design.md` | Relational schema, ERD, normalization, migrations — for `locations / rooms / beds / residents / resident_stays / rent_records / payments / deposits / move_out_notices` | [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) → `engineering/skills/database-schema-designer` |
| 02 | `02-supabase-auth-rls.md` | Supabase project setup, Auth, **Row Level Security** — the mechanism that enforces per-location data isolation and Super Admin vs Staff roles | [kazdenc/builder-skills](https://github.com/kazdenc/builder-skills) → `dev/setup/supabase-setup` |
| 03 | `03-backend-fastapi.md` | FastAPI patterns: async routes, Pydantic v2 models, dependency injection, OpenAPI — where rent/occupancy/deposit business rules live | [samuelpkg/skills](https://github.com/samuelpkg/skills) → `fastapi` |
| 04 | `04-api-design.md` | REST conventions: URL structure, HTTP verbs, error format, pagination, filtering — for the residents / rent / beds / move-out endpoints | [kazdenc/builder-skills](https://github.com/kazdenc/builder-skills) → `dev/frameworks/api-design` |
| 05 | `05-frontend-nextjs.md` | Next.js + React + TypeScript + Tailwind engineering, performance, accessibility | [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) → `engineering-team/skills/senior-frontend` |
| 06 | `06-ui-dashboard-design.md` | Interface design quality — dashboard cards, data tables, status colours for Occupied/Vacant/Pending | [kazdenc/builder-skills](https://github.com/kazdenc/builder-skills) → `design/frameworks/frontend-design` |
| 07 | `07-multitenant-security-audit.md` | Auditing RLS misconfigurations, exposed keys, auth bypass — guards against one PG's data leaking into another | [Farenhytee/database-sentinel](https://github.com/Farenhytee/database-sentinel) |
| 08 | `08-testing-qa.md` | Frontend testing: Jest, React Testing Library, Playwright E2E, MSW mocks | [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) → `engineering-team/skills/senior-qa` |
| 09 | `09-deployment.md` | Vercel deploy: env vars, preview deploys, domains | [kazdenc/builder-skills](https://github.com/kazdenc/builder-skills) → `dev/setup/vercel-deploy` |
| 10 | `10-backend-testing-python.md` | pytest, fixtures, mocking, parametrization, coverage — for the rent/deposit/occupancy calculations | [Ashfaqbs/software-dev-ai-claude-toolkit](https://github.com/Ashfaqbs/software-dev-ai-claude-toolkit) → `skills/python-testing` |

## Activating these in Claude Code

Files here are reference documents. For Claude Code to auto-load them as real skills, each
needs to live at `.claude/skills/<name>/SKILL.md`. To install:

```bash
cd "/home/harsh/Work/GVC Executive PG"
for f in skills/[0-9]*.md; do
  n=$(basename "$f" .md)
  mkdir -p ".claude/skills/$n" && cp "$f" ".claude/skills/$n/SKILL.md"
done
```

## Known gaps

- **Render deployment** — no good Render-specific skill exists publicly; `09-deployment.md` covers
  Vercel (frontend) only. The FastAPI backend deploy to Render will be done manually.
- Skills are third-party community content, not Anthropic-official. Treat their instructions as
  guidance, not as rules that override this project's `Project.md`.

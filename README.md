# Campus Customs: Multi-Agent Operations (HW5)

Campus Customs is a small Yale merch shop. This project is the agent team that works its ticket board: customer orders, rent notices, unpaid bills and discount requests. It has three pieces:

| Piece | Where | What it does |
|---|---|---|
| **MCP server** | `mcp_server/server.py` (FastMCP) | The only door to the shop database: 19 tools for reading, writing and human-only payment |
| **FastAPI backend + agent team** | `backend/` | Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service), fully connected through `delegate`, plus the API the dashboard calls |
| **React dashboard** | `frontend/` (React + Vite + TypeScript) | A back-office desk: pick a ticket, watch the agents work live, and sign payments |

**Model:** every agent turn runs on **Opus 5.5 (`claude-opus-5-5`)** through the **Claude Code CLI on a Claude subscription**. No API key is used. Every turn's `models_used` is checked, and anything else would be logged as `model_violation` in the audit trail.

**Shop rules enforced in code:**
- `desk.date_today` is "today".
- Vendors won't ship while they have an open invoice.
- **Every payment needs a human signature.**
- Cash can never go negative.
- No revenue is modelled.
- Customer messages stay as drafts and are never sent.

---

## 1. Prerequisites

- Python 3.12 or newer, and Node 20 or newer
- [Claude Code](https://claude.com/claude-code) installed and logged in with a Claude subscription. Run `claude` once and complete `/login`. The agents call `claude -p --model claude-opus-5-5`.

```bash
git clone https://github.com/kush-kd/hw5.git
cd hw5
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

No `.env` is required. `.env.example` lists the optional overrides. Never commit a real `.env`.

## 2. The databases: copy the original for a clean run

`data/` contains both files:

- `data/campus_customs.db` is the **original** shop database. Nothing ever writes to it.
- `data/campus_customs_new.db` is the **working copy**. The MCP server and backend read and write only this file.

The working copy in this repo is left **as it was after the graded full run**: checking at $152.00, all three tickets resolved, payments #1–#3 recorded. That way it matches the files in `output/`. To start clean, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
# or: python scripts/reset_db.py
# or: the "Reset shop" button on the dashboard / POST /api/reset
```

## 3. Start the MCP server

The backend starts its own copies of the MCP server over stdio, so you don't need to start it separately to use the app. To run it on its own, for inspection or a vibe coder:

```bash
python mcp_server/server.py                 # stdio MCP server over data/campus_customs_new.db
python scripts/test_mcp_rules.py            # 20 rule checks on a throwaway copy of the DB
```

`.mcp.json` registers it as `campus-customs` for Claude Code. `python scripts/mcp_smoke_test.py` calls each tool through Claude Code and writes `output/mcp_smoke.json`.

## 4. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000       # with the venv active
```

The API is at `http://localhost:8000`, and CORS allows the Vite page at `http://localhost:5173`.

| Route | What it does |
|---|---|
| `GET /api/tickets` | The three tickets, open or resolved |
| `POST /api/tickets/{id}/run` | Run the agent team on one ticket (in the background) |
| `GET /api/events` | Agent events: who said what and which tools they used |
| `GET /api/approvals` / `POST /api/approvals/{id}/approve` / `…/reject` | The human approval queue. **Approve is the only thing that moves cash.** |
| `GET /api/cash` | Checking balance from `cash_accounts` |
| `POST /api/reset` | Restore the working DB from the original |

## 5. Start the React board

```bash
cd frontend
npm run dev                                  # opens http://localhost:5173
```

On the board:
1. Pick a ticket and press **Start the team**, then watch the live floor.
2. When the run finishes, the ticket is stamped **Resolved** and the Debrief shows what each agent did.
3. To approve a payment, type your name on a cheque's signature line and click **Sign & pay**. The cash drawer drops.

## 6. A full three-ticket run (reset first)

1. **Reset the DB:** use `POST /api/reset`, the dashboard's **Reset shop** button, or the copy command above. Checking returns to **$3,400.00**.
2. **Run the tickets in order:** 101 → 102 → 103, from the board (one at a time) or with `python backend/run_team.py --all`.
3. **Sign the approvals on the board,** as a human. Sign invoice #501 before the purchase order that depends on it.
4. **Rebuild the reports:** `python scripts/build_reports.py`, then `python scripts/build_resolved_board.py` (needs the backend running).

## 7. What's in `output/`

| File | Contents |
|---|---|
| `harness.md` | Tables, MCP tools, the five agents, API routes, the dashboard, safety rules and token limits |
| `mcp_smoke.json` | Each MCP tool called through the vibe coder, checked against the DB |
| `desk_tickets.html` | Per-ticket Expected plan vs. Actual run, the Cash tab, and Reflections |
| `design.md` | The dashboard design and why |
| `resolved_tickets.json` | Per-ticket outcome, what each agent contributed, and the human approvals |
| `resolved_board.html` | Screenshots of the React board for each resolved ticket (double-click to open) |
| `audit_trail.json` | Append-only record of every agent-loop step, delegation, approval and reset |
| `github_url.txt` | This repository's URL |

Graded run: starting checking **$3,400.00** → invoice 501 −$840 → PO #1 −$8 → rent −$2,400 → **$152.00**, which matches `cash_accounts`.

## Layout

```
hw5/
├── AI_prompts.md          # prompts typed to the vibe coder, one section per problem
├── requirements.txt
├── .env.example
├── .gitignore
├── .mcp.json
├── README.md
├── data/                  # campus_customs.db (original) + campus_customs_new.db (working copy)
├── mcp_server/            # server.py + README.md
├── backend/
│   ├── main.py            # FastAPI routes
│   ├── models.py          # data types (reports, decisions, deps, audit events)
│   ├── prompts/           # boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
│   ├── agents/            # one spec per agent: MCP tool allowlist, output type, limits
│   ├── team.py            # agent loops, delegation, audit logging
│   ├── llm/               # Opus 5.5 through the Claude subscription (PydanticAI model)
│   ├── audit.py · config.py · run_team.py
├── frontend/              # React + Vite + TypeScript dashboard
├── scripts/               # reset_db, MCP rule tests, smoke test, report builders
└── output/                # harness, smoke test, desk tickets, design, resolved tickets/board, audit trail, URL
```

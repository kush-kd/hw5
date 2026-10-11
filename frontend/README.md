# Campus Customs Back Office: React dashboard

React + Vite + TypeScript desk for watching the agent team and signing payments.

```bash
npm install
npm run dev        # opens http://localhost:5173
```

The board calls the FastAPI backend at `http://localhost:8000`. Start it first, from `backend/`, with `uvicorn main:app --reload --port 8000`. The backend allows this origin with CORS. To point the board elsewhere, set `VITE_API_BASE` in `frontend/.env` (see `.env.example`).

What it does:
- lists the three tickets
- lets you pick one and start the agent team on it
- shows each agent live as it works
- stamps the ticket resolved when the run finishes
- summarizes what each agent did
- lets a human sign or reject payments, purchase orders and price approvals
- shows the checking balance, which drops when you sign a payment

Design notes are in `../output/design.md`.

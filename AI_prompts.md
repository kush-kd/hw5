# AI Prompts Log

This is a log of the prompts I gave the AI vibe coder while building Campus Customs Multi-Agent Operations. It has one section per assignment problem.

## Setup: Scenario and data

**Prompt:**
We're building Campus Customs Multi-Agent Operations, the agent team that runs the shop. Open tickets land on a board: customer orders, rent, unpaid bills, discount requests. Build three pieces that talk to each other: an MCP server, a FastAPI backend with a multi-agent team, and a React dashboard where a human can watch the agents work and approve requests. The team is fully connected, so any agent can delegate to any other. The agents are:
- **Boss:** reads each ticket, decides who works on it, and makes the final call.
- **Inventory:** checks stock by SKU and size, spots shortfalls, and finds the vendor who can restock.
- **Accounting:** watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval.
- **Facilities:** handles the shop space (leases, rent).
- **Customer Service:** drafts customer messages.

I put `data.zip` in the HW5 folder. Unzip it, look at `data/campus_customs.db` to understand the data, and make a working copy, `data/campus_customs_new.db`, for the MCP server and backend. Keep the original untouched so we can reset.

The shop rules:
- `desk.date_today` is "today".
- Vendor lead times come from `vendors`.
- A vendor won't ship while it has an open unpaid invoice.
- Every payment needs human approval and must update the relevant tables.
- The pay tool refuses if cash would go negative.
- Cash only goes out.
- Reset the database before a full run.
- Never email customers or call real vendors; drafts stay on the board.

We'll work one problem at a time and push to a public GitHub repo at the end.

**Follow-up:** "Use Opus 5.5 through my Claude subscription for every agent." What was missing after the first prompt: it didn't say which model the agents run on or how the AI calls are made. We agreed on Opus 5.5 through my Claude subscription, with no API key.

## Problem 1: Vibe coder prompts

**Prompt:**
Create `AI_prompts.md` at the start of the assignment and keep it updated as we work. This file is the log of what I typed to you, the vibe coder, in my own words. Put one section per problem. Each section must include:
- the problem number and title
- at least one prompt I typed, in my own words as much as possible
- a follow-up prompt if I needed one, with one sentence on what was missing after the first prompt

**Follow-up:** None needed.

## Problem 2: Understand the database

**Prompt:**
Open `data/campus_customs.db` and look through every table and its fields. Copy the original file to `data/campus_customs_new.db`; later problems update that working copy. Study the three open tickets so you can see how they link to the other tables. Start `output/harness.md`. For each table, list the fields and one short line on why that table matters for the agents. We'll keep growing the harness file in later problems. Ask me if you have any questions.

**Follow-up:** None needed.

## Problem 3: Build the MCP server

**Prompt:**
Write an MCP server in `mcp_server/` using FastMCP. It talks to `data/campus_customs_new.db`. You don't need to connect or run it in this problem. Every agent in this homework uses the tools in this MCP server, and we'll add more tools later. For now, write three tools you know you'll need for the tickets in the database. Keep the names clear. Never invent any data; only use information in the database. In `output/harness.md`, list each of the three MCP tools. For every tool, include which table it reads, which ticket it helps unlock (101, 102, or 103), and one sentence on why that tool is the right one for that ticket. Don't be vague: a line like "reads inventory" scores low, so tie each tool to the ticket and be precise. Also add a short `mcp_server/README.md` that explains what the MCP server is for, which database file it uses, and the three tools it has.

**Follow-up:** None needed.

## Problem 4: Add the MCP server to the vibe coder and test each tool

**Prompt:**
In the vibe coder, add our MCP server to this project so the vibe coder can call the tools. Save the connection JSON in `.mcp.json` at the project root, or wherever the vibe coder saves its local MCP server list. Then, with the vibe coder connected, test each of the three MCP tools. Save the evidence in `output/mcp_smoke.json`. For each tool, include the prompt I asked the vibe coder, the tool name, and the tool output, which must match the values in `data/campus_customs_new.db`.

**Follow-up:** "Why are you comparing the shop's today to the computer's real date? Did the instructions ask for that?" Then: "This was the initial instruction. Did you not pay attention?" (with a screenshot of the `desk.date_today` rule). What was missing after the first prompt: the MCP tools already used `desk.date_today`, but the Claude Code session answering the smoke-test prompts wasn't told that rule. It compared the shop date with its own system date and added a confusing warning. The smoke test now gives every run the shop rule as context, so the replies use only 2026-08-31.

## Problem 5: Build the agent team and grow the MCP tools

**Prompt:**
Build the agent team for Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities and Customer Service. Include prompts, models and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in `backend/prompts/`, one file per agent. Put the data types in `backend/models.py`, and the agent files under `backend/`; the layout can vary as long as the five roles are clear. Use my Claude subscription and Opus 5.5 for every agent. Write each prompt in your own words, with the shop rules that agent needs. Detailed prompts that cover every aspect of an agent's work and scope score higher than a short generic prompt, so be as detailed as possible and cover everything. Add any tools the agents need to the MCP server so they can work on the open tickets. Shop facts come from the MCP server over `data/campus_customs_new.db`. Don't invent data, and don't create a second shop-tools layer that bypasses MCP. Wire the agents so they append to `output/audit_trail.json` as they run: for each agent-loop step, record enough to audit later, and don't wipe the file on each run. In `output/harness.md`, list each agent and each MCP tool, including the ones added in this problem, with the tables each tool uses. Also add a short safety section covering the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. Update `mcp_server/README.md` so the tool list matches what we have now. Ask me if you have any questions.

**Follow-up:** None needed.

## Problem 6: Plan the three tickets

**Prompt:**
Before wiring the backend, write down what you expect the team to do on each open ticket. Build `output/desk_tickets.html`, a page I can double-click to open, with one tab per ticket (101, 102, 103). Also add empty Cash and Reflections tabs for later problems; leave them blank or add a short "coming later" note for now. For each ticket, fill in only the Expected section, and leave room for an Actual section that we'll fill after running the agents. In each ticket's Expected section, write in your own words:
- who the Boss should call first, and why
- all the agent delegations you expect, not just "Boss calls everyone"
- which MCP tools you expect that run to use

A plan that sends every specialist on every ticket scores low. Be thorough and don't skip anything.

**Follow-up:** None needed.

## Problem 7: Backend routes

**Prompt:**
The React dashboard in the next problem needs a backend it can call. In `backend/main.py`, use FastAPI and add routes that:
- return the three tickets and whether each is open or resolved
- take a ticket id and run the agent team on that ticket
- return recent agent events (what each agent said and which tools it used) so the board can refresh
- approve a payment or purchase after a human clicks Approve (agents only prepare the payment; this route is what actually changes cash)
- return the current checking balance from `cash_accounts`
- reset the database to the original values when I want a fresh run

From the `backend/` folder, the server starts with `uvicorn main:app --reload --port 8000`, which runs the backend at `http://localhost:8000` for the dashboard. In `output/harness.md`, list each route in one line: what URL, and what it does. Ask me if you have any questions.

**Follow-up:** None needed.

## Problem 8: The agent dashboard

**Prompt:**
Build the frontend dashboard in `frontend/` with React + Vite + TypeScript. The page should call the routes we built in Problem 7. At a minimum, the board should:
- list all three tickets
- let me pick one ticket and start the agent team on it
- show each agent and what it's saying or doing while the ticket runs
- mark a ticket resolved when the run finishes
- show a short summary of what each agent did on that ticket
- let a human approve a payment or purchase when asked
- show the checking balance, which should drop after an approved payment

Make the dashboard look good. Be creative with the layout and feel. This is a real desk people would want to sit at, so put thought into how it looks; this is how it will be assessed, so put in as much effort as you can. Point the frontend at the backend on `http://localhost:8000`, and on the backend allow the Vite page origin (`http://localhost:5173`) so the browser can call these routes. The board starts with `npm run dev`, which opens the React desk in the browser so I can pick tickets and watch the agents. Write `output/design.md` with what you chose for the dashboard's look (the layout, how the agents read differently, how resolved tickets and cash show up) and why, including the creative choices that make it feel special and something people would actually enjoy using.

**Follow-up:** None needed.

## Problem 9: Full run and the resolved board

**Prompt:**
Before testing the agents on a full run over the three tickets, reset the working database `data/campus_customs_new.db` again so we start clean, and note the starting checking balance. Then run all three tickets on the board (101, 102, 103) until each is resolved. Open `output/desk_tickets.html` from Problem 6. On each ticket tab, fill in the Actual section from this run: which agents worked, what they delegated, and which tools they used. Keep the Expected section so I can compare the two. On the Cash tab of the same file, itemize the money:
- the starting checking balance after the reset
- for each ticket, how cash changed when that ticket was resolved, and why (which payment or purchase, and the dollar amount)
- the ending checking balance, which must match `cash_accounts` in the working database

Wrong cash math loses points even if the board shows every ticket resolved. Also save:
- `output/resolved_tickets.json`: for each ticket, the id, final status, a short outcome, what each agent contributed, and any human approvals
- `output/resolved_board.html`: a page I can double-click, with a screenshot of the React board for each resolved ticket

Append real runs to `output/audit_trail.json`. Finish `output/harness.md` so it covers the tables, MCP tools, the five agents, the API routes, the dashboard, and the safety rules.

**Follow-up:** "I can't click and type my name. How do I do that?" Then: "Approve is not working. When I try to do it, it's still stuck." What was missing after the first prompt: on a smaller window, the Approvals section fell below the ticket and was covered by the ticket board, and the cheque's "signature" line looked like a field but wasn't one. So I couldn't sign. The dashboard was fixed: a "waiting for your signature" button jumps to Approvals, nothing overlaps them anymore, and the signature line is now a real field. After that, I signed every approval myself in the dashboard.

## Problem 10: Reflections

**Prompt:**
Open `output/desk_tickets.html` and fill in the Reflections tab. Answer in my own voice, and be detailed and thorough:
- How would you evaluate the performance of the agents on each ticket, and why?
- For each ticket, how did the Actual compare to the Expected plan written earlier?
- What would have been simpler as one agent with tools, and why?
- Describe three new problems Campus Customs might face that this agent team could solve with the tools we built.
- Describe three new problems Campus Customs might face that this agent team could not solve with the tools we built, and explain the tools and agents we would need to solve them.

Tie every answer to this app and the three tickets we ran, using the ticket tabs and the Cash tab on the same page as evidence. Generic AI essays without Campus Customs details score low, so be as detailed, clear and thorough as possible.

**Follow-up:** None needed.

## Problem 11: Submit to GitHub

**Prompt:**
Push the code to a public GitHub repository so graders can clone it. I'll submit the repo URL to Canvas; also put it in `output/github_url.txt`. Don't push my real `.env` to the repo. Do include both database files under `data/` (the original and the working copy) so graders can run the app easily. Follow the expected file layout. The README should explain how to:
- copy the original DB to the working copy when you need a clean run
- start the MCP server
- start the FastAPI backend
- start the React board
- reset the DB before a full three-ticket run

I already have other work on my GitHub, so push this in a way that adds a separate repo with its own link and doesn't delete or overwrite anything.

**Follow-up:** None needed.

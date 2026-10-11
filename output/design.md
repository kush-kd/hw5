# Dashboard design: the Campus Customs back office

## The idea: a real desk, not a control panel

Most agent dashboards look like server monitors: dark panels, log lines, status LEDs. Campus Customs is a small Yale merch shop on Chapel Street, and the person using this board is a shop manager, not an SRE. So I designed it as **the shop's back-office desk**: warm ivory paper, Yale-blue ink, and brass for anything that touches money. Each object on the desk is something a shop manager already knows how to read:

- tickets are **index cards pinned to a board**
- agents sit around a **team table**
- payments are **cheques you sign**
- customer replies are **letters marked "Draft · not sent"**
- the shop's date is a **tear-off desk calendar**
- cash is a **brass-trimmed cash drawer**

The goal was a screen that feels calm and trustworthy when real money and real customers are involved, and that's also fun to watch while five agents work.

## Layout (three columns, left to right = the order work flows)

```
┌──────────── Campus Customs · Back Office ── [AUG 31 calendar] ──── [ Checking  $3,400.00 ▮▮▮░░ ] ── Reset ┐
│ THE BOARD          │ #101 Bulldog tee                       [Start the team] │ YOUR SIGNATURE            │
│ ┌─ index card ─┐   │ ( Boss )( Inventory )( Accounting )( Facilities )( CS ) │ Signing as: ____________   │
│ │ #101  ✓ stamp│   │ Live floor | Debrief | Drafts & notes        [run ▾]    │ ┌──── cheque ────┐         │
│ └──────────────┘   │  ┌ Boss decides ───────────────────────┐                │ │ Pay to ... $840 │         │
│ ┌─ index card ─┐   │  │ reasoning…  get_ticket(101) …       │                │ │ ____ Sign & pay │         │
│ └──────────────┘   │  └─────────────────────────────────────┘                │ └─────────────────┘         │
│                    │  Boss ──→ Inventory  "check CC-TEE-WHITE…"              │ Ledger                      │
└────────────────────┴──────────────────────────────────────────────────────────┴────────────────────────────┘
```

- **Left, the Board:** all three tickets as index cards with a coloured top edge per ticket type (green for an order, teal for rent, rose for a discount) and a red pin. Each card shows the ask (`1 × CC-TEE-WHITE · S`), the requester's own words in italics, a status pill, and small counters for approvals waiting and drafts. The cards sit slightly tilted, like they're pinned by hand, and straighten when you hover or select one. Clicking a card picks that ticket.
- **Centre, the Workspace:** the selected ticket's header (type, subject, requester, linked invoice or lease) and the **Start the team** button. Under it, the **team table** (five seats), and three tabs: **Live floor** (what's happening now), **Debrief** (what each agent did), and **Drafts & notes** (letters to customers and the notes each agent left on the ticket). A run picker keeps earlier runs, including the ones before a reset, one click away.
- **Right, Your signature:** the approval inbox, with a "Signing as" line and cheques for every pending request across all tickets. Requests for the selected ticket float to the top and are outlined. Below them is the **Ledger**: payments made, approvals and rejections, each with who signed.

Left to right matches the order of the work: a ticket arrives → agents work it → you sign. Your eye never has to jump back and forth.

## How the agents read differently

Each agent has its own **colour, icon and verb**, used everywhere they appear (seat, feed bubble, handoff, report card, note, cheque "prepared by"), so you can tell who's talking without reading the name:

| Agent | Colour | Icon | On the floor it… |
|---|---|---|---|
| Boss | Yale navy | crown | *decides* |
| Inventory | green | package | *counts* |
| Accounting | brass | calculator | *tallies* |
| Facilities | teal | building | *checks* |
| Customer Service | rose | heart speech bubble | *writes* |

- **Team table seats:** each seat has a resting, **working**, **done**, or **not needed** state. A working agent's avatar fills with its colour, "breathes" with a soft pulsing ring, and shows typing dots. A finished agent gets a green check and a tool count, for example "5 tools". After the run, agents the Boss never called fade to grey and say *Not needed*. That makes it obvious at a glance that the Boss didn't send every specialist to every ticket.
- **Speech bubbles:** each step on the Live floor is a bubble tinted in the agent's colour, with a coloured spine on the left. It shows the agent's short reasoning in plain English, then the **MCP tool calls as monospace "receipts"**, for example `check_stock(CC-TEE-WHITE · S · 1)`. Raw tool results stay folded under *Show what the MCP server returned*, so the feed stays readable but is fully auditable.
- **Handoffs are their own visual moment:** a striped strip reading `Boss → Inventory` with a nudging arrow and the delegated task quoted in serif italics. Delegated work is **indented by depth**, so a specialist calling another specialist shows up as nesting.
- **Reports and the final call stand out:** a specialist's finished report is a white "report filed" card in its colour. The Boss's final call is a navy banner with brass lettering, the most authoritative object in the feed.
- **Typography carries tone:** the voices (reasoning, letters, the Boss's decision) are set in **Fraunces**, a warm serif. The machinery (tool names, SKUs, ids, amounts in the ledger) is in **JetBrains Mono**. The interface itself is in **Inter**. You can tell what a person or agent said from what a system did.

## How resolved tickets show up

- When the run finishes, the Boss sets the ticket to `resolved` through MCP. The card on the board then gets a **green rubber "RESOLVED" stamp**. It slams in with a little overshoot animation, rotated and in double-ruled ink with `mix-blend-mode: multiply`, so it looks inked onto the card.
- The board header keeps a running tally, for example "**2**/3 resolved".
- A toast confirms *"Ticket #101 resolved"* with the Boss's decision.
- The workspace flips by itself from **Live floor** to **Debrief**. The Boss's call is at the top, with a brass **"For you, at the desk"** box listing exactly what the human has to sign and in what order. Below it are **What each agent did** cards: each agent's summary, the actions it took, its blockers, and a fold-out of every fact it relied on, with the MCP tool it came from.
- "Resolved" means the agents are done. It never means money moved. Approvals still waiting show up as an hourglass counter on the card and as cheques in the inbox.

## How cash shows up

- **The cash drawer** in the header is always visible:
  - the **checking balance** from `cash_accounts`, in large tabular serif numerals
  - a bar showing how much of it is **promised to pending approvals** (brass hatching) against what's free
  - the line *"$X awaiting your signature · $Y free after"*

  "Free after pending" is the number the agents actually plan against, so the human sees the same constraint the agents do.
- **When you sign a payment, the balance counts down** to the new value over about a second, with an eased tween. The drawer glows brass for a moment. A toast confirms *"Paid $840.00 · Vendor invoice. Checking is now $2,560.00. Signed by …"*. The drop is impossible to miss, and so is the connection between your click and the money.
- **The note "no revenue modelled · cash only goes out"** sits in the drawer, because that rule changes how you read the number.
- **Cheques show the consequence before you sign:** *"checking after signing: $2,560.00"*. If a cheque can't be paid, it says why and the **Sign & pay** button is locked:
  - *"Sign #1 first. The vendor won't ship until that invoice is paid."* for a purchase order that depends on an unpaid invoice.
  - *"Not enough cash … the pay tool would refuse."*

  The backend enforces both rules anyway. The UI just explains them before you try.
- **Price approvals are a different kind of paper.** Discount requests are rose-tinted price slips, not cheques. They show the unit price, the % off and the margin, and say plainly *"no cash moves"*.

## Creative choices that make it feel special

- **Signing is a ritual.** You type your name once ("Signing as"). It's remembered and appears in italic serif on every cheque's signature line. Approving is literally *signing*, and your name is what the backend records as `approved_by`. It makes the human approval rule feel like a real responsibility, not a confirm dialog.
- **The desk calendar** shows the shop's date (`desk.date_today`, Mon Aug 31 2026) instead of the computer's date, because every due date, overdue count and ETA in the shop is measured from it.
- **Paper textures, built with no images:** faint ruled lines on the index cards, guilloche-style crosshatch on the cheques (like real bank paper), a stamp-ruled "Draft · not sent" mark on letters, and a soft paper grain on the background.
- **Motion with meaning only:**
  - bubbles rise in as they arrive, and the feed follows them unless you've scrolled up to read
  - the handoff arrow nudges
  - working seats breathe
  - the stamp slams down
  - the balance counts down

  Nothing moves just for show, and `prefers-reduced-motion` turns all of it off.
- **Safety is visible, not hidden:** the header says *"Human-signed payments only"*, cheques say who prepared them, drafts are stamped *not sent*, and the reset dialog explains exactly what happens and that the audit trail is kept.
- **It never lies about state.** Everything comes from the backend: tickets, cash, approvals and the audit-trail events. The board polls every 1–1.5 seconds while agents are working, and every 4 seconds when idle. The Live floor is rebuilt from `output/audit_trail.json`, so what you watch is the same record an auditor would read later.

## Practical details

- **Stack:** React 19 + Vite + TypeScript, and `lucide-react` icons. Fonts are self-hosted with `@fontsource`, so it works offline.
- **API:** `VITE_API_BASE` (default `http://localhost:8000`). The backend's CORS allows `http://localhost:5173`.
- **One run at a time:** the Start button disables everywhere while any ticket is running, and says which ticket is busy. Every run plans against the same cash drawer, so overlapping runs would plan against the wrong number.
- **Responsive:** below 1280px the inbox moves under the workspace as a grid of cheques. Below 860px everything stacks.
- **Accessibility:** real buttons and tabs with ARIA states, live regions for the feed, toasts and cash, visible focus rings, and colour never used alone (every agent also has an icon and a name).

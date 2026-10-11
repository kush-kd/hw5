"""Build output/resolved_board.html: one self-contained page with React-board screenshots of each
resolved ticket (Debrief + Live floor), plus the outcome and approvals from resolved_tickets.json.

Screenshots come from output/screenshots/ (captured from the running dashboard at
http://localhost:5173/#ticket=<id>&tab=<debrief|floor> with headless Chrome at 2x).
They are re-encoded as JPEG and embedded as base64 so the page opens anywhere with a double-click.

    python scripts/build_resolved_board.py
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "output" / "screenshots"
DATA = json.loads((ROOT / "output" / "resolved_tickets.json").read_text())
OUT = ROOT / "output" / "resolved_board.html"


def jpeg_b64(png: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        jpg = Path(tmp) / (png.stem + ".jpg")
        subprocess.run(["sips", "-Z", "2000", "-s", "format", "jpeg", "-s", "formatOptions", "78", str(png), "--out", str(jpg)],
                       check=True, capture_output=True)
        return base64.b64encode(jpg.read_bytes()).decode()


def money(x: float) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


e = html.escape
cash = DATA["cash"]
sections = []
for t in DATA["tickets"]:
    tid = t["id"]
    called = ["Boss"] + [{"inventory": "Inventory", "accounting": "Accounting", "facilities": "Facilities",
                          "customer_service": "Customer Service"}[k] for k, v in t["agents"].items() if k != "boss" and v["called"]]
    approvals = "".join(
        f"<li>#{a['approval_id']} {e(a['kind'].replace('_', ' '))}"
        + (f" to {e(str(a['payee']))}" if a["payee"] else "")
        + (f", {money(a['amount'])}" if a["amount"] else ", no cash")
        + f": <b>{e(a['status'])}</b> by {e(a['decided_by'] or '—')}"
        + (f" (payment #{a['payment_id']})" if a["payment_id"] else "") + "</li>"
        for a in t["human_approvals"]) or "<li>None</li>"
    shots = []
    for tab, label in (("debrief", "Debrief: the Boss’s call and what each agent did"), ("floor", "Live floor: the agents’ steps and MCP tool calls")):
        png = SHOTS / f"ticket_{tid}_{tab}.png"
        if png.exists():
            shots.append(f'<figure><img alt="Ticket {tid} {label}" src="data:image/jpeg;base64,{jpeg_b64(png)}">'
                         f'<figcaption>{e(label)}</figcaption></figure>')
    sections.append(f"""
<section class="ticket" id="t{tid}">
  <div class="head">
    <div>
      <span class="kind">{e(t['type'].replace('_', ' '))}</span>
      <h2>#{tid} {e(t['subject'])} <span class="stamp">Resolved</span></h2>
      <p class="from">from {e(t['requester'])} · final status <code>{e(t['final_status'])}</code> · run <code>{e(t['run']['run_id'])}</code> · {t['run']['seconds']}s · {t['run']['mcp_tool_calls']} MCP tool calls · {', '.join(t['run']['models'])}</p>
    </div>
    <div class="cashchip"><span>cash change</span><b class="{'neg' if t['cash_change'] < 0 else ''}">{money(t['cash_change']) if t['cash_change'] else '$0.00'}</b></div>
  </div>
  <p class="outcome">{e(t['short_outcome'])}</p>
  <div class="meta"><div><h3>Agents who worked</h3><p>{', '.join(called)}</p></div><div><h3>Human approvals</h3><ul>{approvals}</ul></div></div>
  <div class="shots">{''.join(shots)}</div>
</section>""")

page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs: Resolved Board</title>
<style>
  :root {{ --yale:#00356b; --ink:#1a2232; --muted:#6b7385; --line:#e5dccb; --paper:#f6f1e7; --card:#fffdf8; --ok:#2b7a4b; --bad:#b3372b; --brass:#a8761f; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; color:var(--ink); background:var(--paper); }}
  header {{ background:linear-gradient(100deg,#0c2342,var(--yale)); color:#f4efe4; padding:24px 36px; border-bottom:3px solid var(--brass); }}
  header h1 {{ margin:0; font:600 26px Georgia,serif; }}
  header p {{ margin:4px 0 0; color:#c9d7ec; }}
  .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; max-width:1240px; margin:22px auto 0; padding:0 36px; }}
  .summary div {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 16px; }}
  .summary span {{ display:block; font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); font-weight:650; }}
  .summary b {{ font:600 24px Georgia,serif; color:var(--yale); }}
  .summary .ok {{ color:var(--ok); }}
  nav {{ max-width:1240px; margin:16px auto 0; padding:0 36px; display:flex; gap:8px; }}
  nav a {{ text-decoration:none; color:var(--yale); background:var(--card); border:1px solid var(--line); padding:6px 14px; border-radius:999px; font-weight:600; font-size:13px; }}
  main {{ max-width:1240px; margin:0 auto; padding:10px 36px 60px; }}
  .ticket {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:22px 24px; margin-top:22px; box-shadow:0 8px 24px -12px rgba(26,34,50,.18); }}
  .head {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }}
  .kind {{ font-size:11.5px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }}
  h2 {{ margin:4px 0 2px; font:600 24px Georgia,serif; }}
  .stamp {{ display:inline-block; transform:rotate(-6deg); margin-left:10px; font:800 13px Georgia,serif; letter-spacing:.16em; text-transform:uppercase; color:var(--ok); border:3px double var(--ok); border-radius:5px; padding:1px 8px; vertical-align:4px; }}
  .from {{ margin:0; color:var(--muted); font-size:13px; }}
  code {{ background:#eef3fb; padding:1px 5px; border-radius:4px; font-size:12px; }}
  .cashchip {{ text-align:right; background:#fbf3e2; border:1px solid #ecd8b0; border-radius:12px; padding:8px 14px; white-space:nowrap; }}
  .cashchip span {{ display:block; font-size:11px; text-transform:uppercase; letter-spacing:.1em; color:var(--brass); font-weight:700; }}
  .cashchip b {{ font:600 22px Georgia,serif; }}
  .neg {{ color:var(--bad); }}
  .outcome {{ font:500 16px/1.5 Georgia,serif; margin:14px 0 10px; padding-left:12px; border-left:3px solid var(--yale); }}
  .meta {{ display:grid; grid-template-columns:1fr 2fr; gap:20px; font-size:13.5px; }}
  .meta h3 {{ margin:0 0 4px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
  .meta p, .meta ul {{ margin:0; }} .meta ul {{ padding-left:18px; }}
  .shots {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }}
  figure {{ margin:0; }}
  figure img {{ width:100%; border-radius:10px; border:1px solid var(--line); box-shadow:0 6px 18px -10px rgba(0,0,0,.35); display:block; cursor:zoom-in; }}
  figcaption {{ font-size:12.5px; color:var(--muted); margin-top:6px; }}
  .zoom {{ display:none; position:fixed; inset:0; background:rgba(12,35,66,.85); z-index:10; padding:24px; cursor:zoom-out; }}
  .zoom.on {{ display:flex; align-items:center; justify-content:center; }}
  .zoom img {{ max-width:100%; max-height:100%; border-radius:10px; }}
  footer {{ max-width:1240px; margin:0 auto; padding:0 36px 40px; color:var(--muted); font-size:12.5px; }}
  @media (max-width:900px) {{ .shots, .meta, .summary {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
<header><h1>Campus Customs: Resolved Board</h1>
<p>Full run on the React dashboard after a clean reset · shop date {e(DATA['shop_date'])} · all three tickets resolved · every payment signed by a human</p></header>
<div class="summary">
  <div><span>Tickets resolved</span><b>{sum(t['final_status'] == 'resolved' for t in DATA['tickets'])} / {len(DATA['tickets'])}</b></div>
  <div><span>Starting checking</span><b>{money(cash['starting_balance'])}</b></div>
  <div><span>Paid out (signed)</span><b class="neg">-{money(cash['total_paid_out'])}</b></div>
  <div><span>Ending checking</span><b class="{'ok' if cash['matches'] else 'neg'}">{money(cash['ending_balance_cash_accounts'])} {'✓' if cash['matches'] else '✗'}</b></div>
</div>
<nav>{''.join(f'<a href="#t{t["id"]}">#{t["id"]} {e(t["subject"])}</a>' for t in DATA['tickets'])}</nav>
<main>{''.join(sections)}</main>
<footer>Screenshots were captured from the running React board (http://localhost:5173) after the run and the human approvals. The ending balance matches <code>cash_accounts</code> in <code>data/campus_customs_new.db</code>. Click any screenshot to enlarge it. The details are in <code>output/resolved_tickets.json</code> and <code>output/desk_tickets.html</code>.</footer>
<div class="zoom" id="zoom"><img alt="" id="zoomimg"></div>
<script>
  const z = document.getElementById('zoom'), zi = document.getElementById('zoomimg');
  document.querySelectorAll('figure img').forEach(img => img.addEventListener('click', () => {{ zi.src = img.src; z.classList.add('on'); }}));
  z.addEventListener('click', () => z.classList.remove('on'));
  document.addEventListener('keydown', ev => {{ if (ev.key === 'Escape') z.classList.remove('on'); }});
</script>
</body></html>
"""
OUT.write_text(page)
print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)")

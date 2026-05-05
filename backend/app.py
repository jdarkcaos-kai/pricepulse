from fastapi.responses import FileResponse
import os
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from backend.emails import (
    send_email,
    tpl_waitlist_confirm,
    tpl_watch_confirm,
    tpl_price_change_alert,
    tpl_price_change_waitlist,
)

app = FastAPI(title="PricePulse API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH   = os.getenv("DB_PATH", "./pricepulse.db")
PORT      = int(os.getenv("PORT", 8001))
ADMIN_KEY = os.getenv("ADMIN_KEY", "")


# ── DB ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tools (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            slug        TEXT UNIQUE NOT NULL,
            website     TEXT,
            description TEXT,
            category    TEXT,
            logo        TEXT DEFAULT '🔧',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pricing (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id       INTEGER REFERENCES tools(id),
            plan_name     TEXT NOT NULL,
            price_monthly REAL,
            price_annual  REAL,
            currency      TEXT DEFAULT 'USD',
            notes         TEXT,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS price_changes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id     INTEGER REFERENCES tools(id),
            plan_name   TEXT,
            old_price   REAL,
            new_price   REAL,
            change_pct  REAL,
            change_type TEXT DEFAULT 'increase',
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS waitlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            plan        TEXT DEFAULT 'free',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchers (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER REFERENCES tools(id),
            email   TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tool_id, email)
        );
    """)
    conn.commit()
    _seed(conn)
    conn.close()


def _seed(conn):
    if conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0] > 0:
        return

    tools = [
        # Productividad
        ("Notion",      "notion",      "notion.so",     "All-in-one workspace",              "Productivity",    "📝"),
        ("Linear",      "linear",      "linear.app",    "Issue tracking for software teams",  "Project Mgmt",   "🔷"),
        ("Airtable",    "airtable",    "airtable.com",  "Spreadsheet-database hybrid",        "Productivity",   "📊"),
        ("Monday.com",  "monday",      "monday.com",    "Work management platform",           "Project Mgmt",   "📅"),
        ("Jira",        "jira",        "atlassian.com", "Issue & project tracking",           "Project Mgmt",   "🎯"),
        # Diseño
        ("Figma",       "figma",       "figma.com",     "Collaborative design tool",          "Design",         "🎨"),
        ("Canva",       "canva",       "canva.com",     "Visual design platform",             "Design",         "🖼"),
        ("Webflow",     "webflow",     "webflow.com",   "No-code web builder",                "Design",         "🌐"),
        ("Framer",      "framer",      "framer.com",    "Interactive design & web",           "Design",         "⚡"),
        # Dev / infra
        ("GitHub",      "github",      "github.com",    "Code hosting & collaboration",       "Dev Tools",      "🐙"),
        ("GitLab",      "gitlab",      "gitlab.com",    "DevOps platform",                    "Dev Tools",      "🦊"),
        ("Vercel",      "vercel",      "vercel.com",    "Frontend cloud platform",            "Hosting",        "▲"),
        ("Railway",     "railway",     "railway.app",   "App deployment platform",            "Hosting",        "🚂"),
        ("Netlify",     "netlify",     "netlify.com",   "Web hosting & serverless",           "Hosting",        "🟢"),
        ("Supabase",    "supabase",    "supabase.com",  "Open-source Firebase alternative",   "Database",       "⚡"),
        ("PlanetScale", "planetscale", "planetscale.com","Serverless MySQL platform",         "Database",       "🪐"),
        ("Cloudflare",  "cloudflare",  "cloudflare.com","Network & security platform",        "Infra",          "🔶"),
        ("Sentry",      "sentry",      "sentry.io",     "Error & performance monitoring",     "Monitoring",     "🐛"),
        ("PostHog",     "posthog",     "posthog.com",   "Product analytics suite",            "Analytics",      "🦔"),
        ("Cursor",      "cursor",      "cursor.com",    "AI-powered code editor",             "Dev Tools",      "🖱"),
        # Comunicación
        ("Slack",       "slack",       "slack.com",     "Business messaging",                 "Communication",  "💬"),
        ("Zoom",        "zoom",        "zoom.us",       "Video conferencing",                 "Communication",  "📹"),
        ("Loom",        "loom",        "loom.com",      "Async video messaging",              "Communication",  "🎥"),
        ("Intercom",    "intercom",    "intercom.com",  "Customer messaging platform",        "Support",        "💬"),
        # Marketing / ventas
        ("HubSpot",     "hubspot",     "hubspot.com",   "CRM & marketing automation",         "CRM",            "🟠"),
        ("Mailchimp",   "mailchimp",   "mailchimp.com", "Email marketing",                    "Marketing",      "🐒"),
        ("ConvertKit",  "convertkit",  "convertkit.com","Email for creators",                 "Marketing",      "✉️"),
        ("Stripe",      "stripe",      "stripe.com",    "Payments infrastructure",            "Payments",       "💳"),
        # AI / LLM
        ("OpenAI API",  "openai-api",  "openai.com",    "GPT API access",                     "AI",             "🤖"),
        ("Anthropic",   "anthropic",   "anthropic.com", "Claude API",                         "AI",             "🧠"),
        ("Mixpanel",    "mixpanel",    "mixpanel.com",  "Product analytics",                  "Analytics",      "📈"),
        ("Amplitude",   "amplitude",   "amplitude.com", "Digital analytics platform",         "Analytics",      "📊"),
        ("Retool",      "retool",      "retool.com",    "Internal tools builder",             "Dev Tools",      "🔧"),
        ("Doppler",     "doppler",     "doppler.com",   "Secrets & env management",           "Dev Tools",      "🔑"),
        ("PagerDuty",   "pagerduty",   "pagerduty.com", "Incident management",                "Monitoring",     "🚨"),
    ]

    pricing_data = {
        "notion":      [("Free", 0, 0), ("Plus", 10, 8), ("Business", 18, 15), ("Enterprise", None, None)],
        "linear":      [("Free", 0, 0), ("Business", 8, 6), ("Enterprise", None, None)],
        "airtable":    [("Free", 0, 0), ("Plus", 10, 8), ("Pro", 20, 16), ("Enterprise", None, None)],
        "monday":      [("Basic", 9, 8), ("Standard", 12, 10), ("Pro", 19, 16), ("Enterprise", None, None)],
        "jira":        [("Free", 0, 0), ("Standard", 8.15, 7.75), ("Premium", 16, 15.25)],
        "figma":       [("Starter", 0, 0), ("Professional", 15, 12), ("Organization", 45, 45)],
        "canva":       [("Free", 0, 0), ("Pro", 14.99, 12.99), ("Teams", 29.99, 25.99)],
        "webflow":     [("Starter", 0, 0), ("Basic", 14, 12), ("CMS", 23, 20), ("Business", 39, 35)],
        "framer":      [("Free", 0, 0), ("Mini", 5, 4), ("Basic", 15, 12), ("Pro", 30, 25)],
        "github":      [("Free", 0, 0), ("Team", 4, 3.67), ("Enterprise", 21, 19.25)],
        "gitlab":      [("Free", 0, 0), ("Premium", 29, 24), ("Ultimate", 99, 89)],
        "vercel":      [("Hobby", 0, 0), ("Pro", 20, 20), ("Enterprise", None, None)],
        "railway":     [("Hobby", 5, 5), ("Pro", 20, 20), ("Enterprise", None, None)],
        "netlify":     [("Free", 0, 0), ("Pro", 19, 19), ("Business", 99, 99)],
        "supabase":    [("Free", 0, 0), ("Pro", 25, 25), ("Team", 599, 599)],
        "planetscale": [("Hobby", 0, 0), ("Scaler", 39, 39), ("Team", 299, 299)],
        "cloudflare":  [("Free", 0, 0), ("Pro", 25, 20), ("Business", 250, 200)],
        "sentry":      [("Free", 0, 0), ("Team", 26, 23), ("Business", 80, 69)],
        "posthog":     [("Free", 0, 0), ("Paid", 0, 0)],
        "cursor":      [("Hobby", 0, 0), ("Pro", 20, 16), ("Business", 40, 32)],
        "slack":       [("Free", 0, 0), ("Pro", 8.75, 7.25), ("Business+", 15, 12.50)],
        "zoom":        [("Basic", 0, 0), ("Pro", 15.99, 13.33), ("Business", 19.99, 16.66)],
        "loom":        [("Starter", 0, 0), ("Business", 12.50, 10), ("Enterprise", None, None)],
        "intercom":    [("Essential", 39, 39), ("Advanced", 99, 99), ("Expert", 139, 139)],
        "hubspot":     [("Free", 0, 0), ("Starter", 20, 18), ("Professional", 890, 800)],
        "mailchimp":   [("Free", 0, 0), ("Essentials", 13, 11), ("Standard", 20, 17)],
        "convertkit":  [("Free", 0, 0), ("Creator", 25, 9), ("Creator Pro", 50, 25)],
        "stripe":      [("Standard", 0, 0)],
        "openai-api":  [("Pay-as-you-go", 0, 0)],
        "anthropic":   [("Pay-as-you-go", 0, 0)],
        "mixpanel":    [("Free", 0, 0), ("Growth", 28, 25), ("Enterprise", None, None)],
        "amplitude":   [("Starter", 0, 0), ("Plus", 49, 49), ("Enterprise", None, None)],
        "retool":      [("Free", 0, 0), ("Team", 10, 8.33), ("Business", 50, 41.67)],
        "doppler":     [("Community", 0, 0), ("Team", 7, 6), ("Enterprise", None, None)],
        "pagerduty":   [("Free", 0, 0), ("Professional", 21, 19), ("Business", 41, 36)],
    }

    # Historial real de cambios de precio
    changes = [
        ("figma",       "Organization",  45,   45,   0,    "restructure",  "2023-06-01"),
        ("figma",       "Professional",  12,   15,   25,   "increase",     "2023-06-01"),
        ("slack",       "Pro",           6.67, 8.75, 31,   "increase",     "2023-09-01"),
        ("slack",       "Business+",     12.50, 15,  20,   "increase",     "2023-09-01"),
        ("railway",     "Hobby",         0,    5,    None, "new_tier",     "2024-03-01"),
        ("supabase",    "Team",          599,  599,  0,    "restructure",  "2024-01-01"),
        ("cursor",      "Pro",           20,   20,   0,    "new_product",  "2024-06-01"),
        ("notion",      "Plus",          8,    10,   25,   "increase",     "2023-05-01"),
        ("vercel",      "Pro",           20,   20,   0,    "stable",       "2024-01-01"),
        ("hubspot",     "Starter",       45,   20,  -56,   "decrease",     "2024-01-01"),
        ("github",      "Team",          4,    4,    0,    "stable",       "2024-01-01"),
        ("zoom",        "Pro",           14.99, 15.99, 7,  "increase",     "2023-08-01"),
        ("intercom",    "Essential",     74,   39,  -47,   "decrease",     "2023-10-01"),
        ("canva",       "Pro",           12.99, 14.99, 15, "increase",     "2023-07-01"),
        ("loom",        "Business",      8,    12.50, 56,  "increase",     "2023-09-01"),
    ]

    for name, slug, website, desc, cat, logo in tools:
        conn.execute(
            "INSERT OR IGNORE INTO tools (name, slug, website, description, category, logo) VALUES (?,?,?,?,?,?)",
            (name, slug, website, desc, cat, logo)
        )

    conn.commit()

    for slug, plans in pricing_data.items():
        row = conn.execute("SELECT id FROM tools WHERE slug=?", (slug,)).fetchone()
        if not row:
            continue
        tool_id = row[0]
        for plan_name, monthly, annual in plans:
            conn.execute(
                "INSERT INTO pricing (tool_id, plan_name, price_monthly, price_annual) VALUES (?,?,?,?)",
                (tool_id, plan_name, monthly if monthly is not None else None, annual if annual is not None else None)
            )

    conn.commit()

    for slug, plan, old_p, new_p, pct, ctype, date in changes:
        row = conn.execute("SELECT id FROM tools WHERE slug=?", (slug,)).fetchone()
        if not row:
            continue
        conn.execute(
            "INSERT INTO price_changes (tool_id, plan_name, old_price, new_price, change_pct, change_type, detected_at) VALUES (?,?,?,?,?,?,?)",
            (row[0], plan, old_p, new_p, pct, ctype, date)
        )

    conn.commit()


# ── Models ───────────────────────────────────────────────────────

class WaitlistIn(BaseModel):
    email: str

class WatchIn(BaseModel):
    email: str
    tool_slug: str

class PriceUpdateIn(BaseModel):
    tool_slug:   str
    plan_name:   str
    new_price:   float
    change_type: str = "increase"  # increase | decrease | restructure | new_tier


# ── Endpoints ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "product": "pricepulse"}


@app.get("/api/tools")
def list_tools(
    q: str = Query(default="", description="Buscar por nombre"),
    category: str = Query(default="", description="Filtrar por categoría"),
    limit: int = Query(default=50, le=100),
):
    conn = get_db()
    sql = "SELECT t.*, COUNT(DISTINCT w.id) as watchers FROM tools t LEFT JOIN watchers w ON w.tool_id=t.id WHERE 1=1"
    params = []
    if q:
        sql += " AND LOWER(t.name) LIKE ?"
        params.append(f"%{q.lower()}%")
    if category:
        sql += " AND t.category=?"
        params.append(category)
    sql += " GROUP BY t.id ORDER BY watchers DESC, t.name LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        tool = dict(r)
        plans = conn.execute(
            "SELECT plan_name, price_monthly, price_annual FROM pricing WHERE tool_id=? ORDER BY price_monthly",
            (tool["id"],)
        ).fetchall()
        tool["plans"] = [dict(p) for p in plans]
        tool["has_free"] = any(p["price_monthly"] == 0 for p in plans)
        result.append(tool)
    conn.close()
    return {"tools": result, "total": len(result)}


@app.get("/api/tools/{slug}")
def get_tool(slug: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM tools WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool = dict(row)
    tool["plans"] = [dict(p) for p in conn.execute(
        "SELECT * FROM pricing WHERE tool_id=? ORDER BY price_monthly", (tool["id"],)
    ).fetchall()]
    tool["changes"] = [dict(c) for c in conn.execute(
        "SELECT * FROM price_changes WHERE tool_id=? ORDER BY detected_at DESC LIMIT 10", (tool["id"],)
    ).fetchall()]
    tool["watchers"] = conn.execute(
        "SELECT COUNT(*) FROM watchers WHERE tool_id=?", (tool["id"],)
    ).fetchone()[0]
    conn.close()
    return tool


@app.get("/api/categories")
def get_categories():
    conn = get_db()
    rows = conn.execute(
        "SELECT category, COUNT(*) as count FROM tools GROUP BY category ORDER BY count DESC"
    ).fetchall()
    conn.close()
    return {"categories": [dict(r) for r in rows]}


@app.get("/api/changes")
def recent_changes(limit: int = Query(default=15, le=50)):
    conn = get_db()
    rows = conn.execute("""
        SELECT pc.*, t.name as tool_name, t.slug, t.logo
        FROM price_changes pc
        JOIN tools t ON t.id = pc.tool_id
        WHERE pc.change_type != 'stable'
        ORDER BY pc.detected_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return {"changes": [dict(r) for r in rows]}


@app.get("/api/stats")
def stats():
    conn = get_db()
    total_tools   = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
    total_changes = conn.execute("SELECT COUNT(*) FROM price_changes").fetchone()[0]
    total_watches = conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    increases     = conn.execute("SELECT COUNT(*) FROM price_changes WHERE change_type='increase'").fetchone()[0]
    decreases     = conn.execute("SELECT COUNT(*) FROM price_changes WHERE change_type='decrease'").fetchone()[0]
    conn.close()
    return {
        "tools_tracked": total_tools,
        "changes_detected": total_changes,
        "users_watching": total_watches,
        "increases": increases,
        "decreases": decreases,
    }


@app.post("/api/waitlist")
def join_waitlist(data: WaitlistIn):
    conn = get_db()
    already = conn.execute("SELECT id FROM waitlist WHERE email=?", (data.email,)).fetchone()
    if already:
        conn.close()
        return {"ok": True, "message": "Ya estás en la lista.", "total": 0}
    conn.execute("INSERT INTO waitlist (email) VALUES (?)", (data.email,))
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    conn.close()
    # Email de confirmación
    send_email(
        to=data.email,
        subject="You're on the PricePulse list 📊",
        html=tpl_waitlist_confirm(data.email, total),
    )
    return {"ok": True, "message": "¡Estás en la lista! Revisa tu email.", "total": total}


@app.get("/api/waitlist/count")
def waitlist_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    conn.close()
    return {"count": count}


@app.post("/api/watch")
def watch_tool(data: WatchIn):
    conn = get_db()
    tool = conn.execute("SELECT * FROM tools WHERE slug=?", (data.tool_slug,)).fetchone()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool = dict(tool)
    already = conn.execute(
        "SELECT id FROM watchers WHERE tool_id=? AND email=?", (tool["id"], data.email)
    ).fetchone()
    if not already:
        conn.execute("INSERT INTO watchers (tool_id, email) VALUES (?,?)", (tool["id"], data.email))
        conn.commit()
        plans = [dict(p) for p in conn.execute(
            "SELECT plan_name, price_monthly FROM pricing WHERE tool_id=? ORDER BY price_monthly",
            (tool["id"],)
        ).fetchall()]
        send_email(
            to=data.email,
            subject=f"Now watching {tool['name']} — PricePulse",
            html=tpl_watch_confirm(
                email=data.email,
                tool_name=tool["name"],
                tool_logo=tool["logo"] or "🔧",
                tool_slug=data.tool_slug,
                plans=plans,
            ),
        )
    count = conn.execute("SELECT COUNT(*) FROM watchers WHERE tool_id=?", (tool["id"],)).fetchone()[0]
    conn.close()
    return {"ok": True, "watchers": count}


@app.post("/api/admin/price-update")
def admin_price_update(data: PriceUpdateIn, authorization: str = Header(default="")):
    """Actualiza un precio y envía alertas a todos los watchers del tool."""
    if not ADMIN_KEY or authorization != f"Bearer {ADMIN_KEY}":
        raise HTTPException(status_code=403, detail="Unauthorized")

    conn = get_db()
    tool = conn.execute("SELECT * FROM tools WHERE slug=?", (data.tool_slug,)).fetchone()
    if not tool:
        conn.close()
        raise HTTPException(status_code=404, detail="Tool not found")
    tool = dict(tool)

    # Obtener precio actual para calcular cambio
    current = conn.execute(
        "SELECT price_monthly FROM pricing WHERE tool_id=? AND plan_name=?",
        (tool["id"], data.plan_name)
    ).fetchone()
    old_price = float(current[0]) if current and current[0] is not None else 0.0
    change_pct = round(((data.new_price - old_price) / old_price * 100), 1) if old_price else None

    # Actualizar precio
    conn.execute(
        "UPDATE pricing SET price_monthly=?, updated_at=? WHERE tool_id=? AND plan_name=?",
        (data.new_price, datetime.utcnow().isoformat(), tool["id"], data.plan_name)
    )
    # Registrar cambio
    conn.execute(
        "INSERT INTO price_changes (tool_id, plan_name, old_price, new_price, change_pct, change_type) VALUES (?,?,?,?,?,?)",
        (tool["id"], data.plan_name, old_price, data.new_price, change_pct, data.change_type)
    )
    conn.commit()

    # Alertar a watchers específicos del tool
    watchers = conn.execute(
        "SELECT email FROM watchers WHERE tool_id=?", (tool["id"],)
    ).fetchall()
    watcher_emails = [w[0] for w in watchers]

    # Alertar también a usuarios de waitlist (resumen semanal simplificado)
    waitlist = conn.execute("SELECT email FROM waitlist").fetchall()
    waitlist_emails = [w[0] for w in waitlist if w[0] not in watcher_emails]

    conn.close()

    sent_watchers = 0
    for email in watcher_emails:
        html, subject = tpl_price_change_alert(
            email=email,
            tool_name=tool["name"],
            tool_logo=tool["logo"] or "🔧",
            tool_slug=data.tool_slug,
            plan_name=data.plan_name,
            old_price=old_price,
            new_price=data.new_price,
            change_pct=change_pct,
            change_type=data.change_type,
        )
        if send_email(email, subject, html):
            sent_watchers += 1

    sent_waitlist = 0
    for email in waitlist_emails:
        html, subject = tpl_price_change_waitlist(
            email=email,
            tool_name=tool["name"],
            tool_logo=tool["logo"] or "🔧",
            plan_name=data.plan_name,
            old_price=old_price,
            new_price=data.new_price,
            change_pct=change_pct,
            change_type=data.change_type,
        )
        if send_email(email, subject, html):
            sent_waitlist += 1

    return {
        "ok": True,
        "tool": tool["name"],
        "plan": data.plan_name,
        "old_price": old_price,
        "new_price": data.new_price,
        "change_pct": change_pct,
        "emails_sent": {"watchers": sent_watchers, "waitlist": sent_waitlist},
    }


@app.delete("/api/unsubscribe")
def unsubscribe(email: str = Query(...)):
    """Elimina el email de waitlist y watchers."""
    conn = get_db()
    conn.execute("DELETE FROM waitlist WHERE email=?", (email,))
    conn.execute("DELETE FROM watchers WHERE email=?", (email,))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Unsubscribed successfully."}


@app.get("/api/debug/email")
def debug_email(to: str = Query(...)):
    """Endpoint temporal de debug — envia un email de prueba y retorna el resultado."""
    import json as _json, urllib.request as _req
    from backend.emails import send_email as _send
    app_url = os.getenv("APP_URL", "")
    ok = _send(to, "[DEBUG] PricePulse email test", f"<p>Test desde Railway via Gmail. APP_URL={app_url}</p>")
    return {"ok": ok, "to": to, "provider": "gmail_smtp"}


@app.on_event("startup")
def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

@app.get("/", include_in_schema=False)
@app.get("/{_spa_path:path}", include_in_schema=False)
async def _serve_spa(_spa_path: str = ""):
    import os as _os
    _idx = _os.path.join(_os.path.dirname(__file__), "..", "frontend", "index.html")
    if not _os.path.exists(_idx):
        _idx = "frontend/index.html"
    if _os.path.exists(_idx):
        return FileResponse(_idx, media_type="text/html")
    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "frontend not found"}, status_code=404)

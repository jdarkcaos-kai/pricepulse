"""
PricePulse — Email system via Resend API.

Variables de entorno necesarias:
  RESEND_API_KEY  — API key de resend.com (gratis hasta 3000 emails/mes)
  FROM_EMAIL      — ej: "PricePulse <alerts@tudominio.com>"
  APP_URL         — URL pública del producto, ej: https://pricepulse.up.railway.app
"""
import os
import json
import urllib.request
import urllib.error
from typing import Optional

# ── Core sender (Gmail SMTP) ─────────────────────────────────────

def send_email(to: str, subject: str, html: str) -> bool:
    """Envia un email via Gmail SMTP con App Password."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    from_name  = os.getenv("FROM_NAME", "PricePulse")

    if not gmail_user or not gmail_pass:
        print(f"[EMAIL] Sin GMAIL_USER/GMAIL_APP_PASSWORD — email a {to} no enviado: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{gmail_user}>"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


# ── Base template ────────────────────────────────────────────────

def _wrap(body: str) -> str:
    app_url = os.getenv("APP_URL", "https://pricepulse-production-ee9b.up.railway.app")
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/></head>
<body style="background:#0a0e1a;color:#f0f4ff;font-family:ui-sans-serif,system-ui,sans-serif;margin:0;padding:0;">
  <div style="max-width:560px;margin:40px auto;padding:0 20px;">
    <div style="text-align:center;margin-bottom:28px;">
      <span style="font-size:22px;font-weight:900;color:#6366f1;">📈 PricePulse</span>
    </div>
    {body}
    <div style="text-align:center;margin-top:28px;font-size:12px;color:rgba(240,244,255,.25);">
      PricePulse · Tracking SaaS pricing so you don't have to<br/>
      <a href="{app_url}/unsubscribe?email={{email}}" style="color:rgba(240,244,255,.25);">Unsubscribe</a>
    </div>
  </div>
</body>
</html>"""


# ── Templates ────────────────────────────────────────────────────

def tpl_waitlist_confirm(email: str, total: int) -> str:
    body = f"""
    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:32px;text-align:center;">
      <div style="font-size:44px;margin-bottom:16px;">✅</div>
      <h1 style="font-size:22px;font-weight:800;margin:0 0 12px;">You're on the list!</h1>
      <p style="font-size:15px;color:rgba(240,244,255,.55);line-height:1.65;margin:0 0 24px;">
        You're one of <strong style="color:#f0f4ff;">{total} people</strong> watching for SaaS price changes.<br/>
        We'll email you the moment a price goes up — or down.
      </p>

      <div style="background:#1a2235;border-radius:8px;padding:16px;margin-bottom:24px;text-align:left;">
        <div style="font-size:11px;color:rgba(240,244,255,.35);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;">Currently tracking</div>
        <div style="font-size:13px;color:rgba(240,244,255,.7);line-height:1.7;">
          📝 Notion &nbsp;·&nbsp; 🎨 Figma &nbsp;·&nbsp; ▲ Vercel &nbsp;·&nbsp; 🐙 GitHub<br/>
          💬 Slack &nbsp;·&nbsp; 🚂 Railway &nbsp;·&nbsp; 🖱 Cursor &nbsp;·&nbsp; and 28 more
        </div>
      </div>

      <a href="{APP_URL}" style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;padding:13px 28px;border-radius:8px;font-weight:700;font-size:14px;">Browse all tracked tools →</a>
    </div>"""
    return _wrap(body).replace("{email}", email)


def _plan_row(p: dict) -> str:
    m = p.get("price_monthly")
    color = "#22c55e" if m == 0 else "#f0f4ff"
    price = "Free" if m == 0 else ("Custom" if m is None else f"${m}/mo")
    return (
        f"<tr>"
        f"<td style='padding:7px 12px;font-weight:600'>{p['plan_name']}</td>"
        f"<td style='padding:7px 12px;color:{color};font-weight:700'>{price}</td>"
        f"</tr>"
    )


def tpl_watch_confirm(email: str, tool_name: str, tool_logo: str, tool_slug: str, plans: list) -> str:
    plan_rows = "".join(_plan_row(p) for p in plans[:5])
    body = f"""
    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:28px;">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px;">
        <div style="font-size:36px;background:#1a2235;border-radius:10px;width:56px;height:56px;display:flex;align-items:center;justify-content:center;">{tool_logo}</div>
        <div>
          <div style="font-size:18px;font-weight:800;">Now watching {tool_name}</div>
          <div style="font-size:13px;color:rgba(240,244,255,.45);margin-top:2px;">We'll alert you when prices change</div>
        </div>
      </div>

      <div style="font-size:11px;color:rgba(240,244,255,.35);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;">Current pricing</div>
      <table style="width:100%;border-collapse:collapse;background:#1a2235;border-radius:8px;overflow:hidden;font-size:13px;margin-bottom:20px;">
        <thead><tr style="background:rgba(255,255,255,.04);">
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:rgba(240,244,255,.4);font-weight:600;">Plan</th>
          <th style="padding:8px 12px;text-align:left;font-size:11px;color:rgba(240,244,255,.4);font-weight:600;">Monthly</th>
        </tr></thead>
        <tbody>{plan_rows}</tbody>
      </table>

      <a href="{APP_URL}" style="display:block;background:#6366f1;color:#fff;text-decoration:none;text-align:center;padding:12px;border-radius:8px;font-weight:700;font-size:14px;">View on PricePulse →</a>
    </div>"""
    return _wrap(body).replace("{email}", email)


def tpl_price_change_alert(
    email: str,
    tool_name: str,
    tool_logo: str,
    tool_slug: str,
    plan_name: str,
    old_price: float,
    new_price: float,
    change_pct: Optional[float],
    change_type: str,
) -> str:
    is_increase = change_type == "increase"
    color     = "#ef4444" if is_increase else "#22c55e"
    arrow     = "↑" if is_increase else "↓"
    badge_bg  = "rgba(239,68,68,.12)"  if is_increase else "rgba(34,197,94,.12)"
    pct_str   = f"{arrow} {abs(change_pct):.0f}%" if change_pct else arrow
    subject_prefix = "⚠️ Price increase" if is_increase else "✅ Price decrease"

    old_str = "Free" if old_price == 0 else f"${old_price:.0f}/mo"
    new_str = "Free" if new_price == 0 else f"${new_price:.0f}/mo"

    body = f"""
    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:28px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px;">
        <div style="font-size:36px;background:#1a2235;border-radius:10px;width:56px;height:56px;display:flex;align-items:center;justify-content:center;">{tool_logo}</div>
        <div style="flex:1;">
          <div style="font-size:18px;font-weight:800;">{tool_name}</div>
          <div style="font-size:13px;color:rgba(240,244,255,.45);">Plan: {plan_name}</div>
        </div>
        <div style="background:{badge_bg};color:{color};border-radius:8px;padding:6px 12px;font-size:14px;font-weight:800;">{pct_str}</div>
      </div>

      <div style="background:#1a2235;border-radius:8px;padding:18px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;justify-content:center;gap:24px;">
          <div style="text-align:center;">
            <div style="font-size:11px;color:rgba(240,244,255,.35);margin-bottom:6px;">BEFORE</div>
            <div style="font-size:24px;font-weight:700;color:rgba(240,244,255,.4);text-decoration:line-through;">{old_str}</div>
          </div>
          <div style="font-size:24px;color:{color};">→</div>
          <div style="text-align:center;">
            <div style="font-size:11px;color:rgba(240,244,255,.35);margin-bottom:6px;">NOW</div>
            <div style="font-size:24px;font-weight:800;color:{color};">{new_str}</div>
          </div>
        </div>
      </div>

      <a href="{APP_URL}" style="display:block;background:#6366f1;color:#fff;text-decoration:none;text-align:center;padding:12px;border-radius:8px;font-weight:700;font-size:14px;">View full pricing history →</a>
    </div>

    <div style="background:#111827;border:1px solid rgba(255,255,255,.05);border-radius:8px;padding:16px;font-size:13px;color:rgba(240,244,255,.5);line-height:1.6;">
      You're receiving this because you're watching <strong style="color:#f0f4ff;">{tool_name}</strong> on PricePulse.
    </div>"""
    return _wrap(body).replace("{email}", email), f"{subject_prefix}: {tool_name} · {plan_name}"


def tpl_price_change_waitlist(
    email: str,
    tool_name: str,
    tool_logo: str,
    plan_name: str,
    old_price: float,
    new_price: float,
    change_pct: Optional[float],
    change_type: str,
    n_changes_this_week: int = 1,
) -> tuple:
    """Para usuarios de la waitlist (resumen, no alerta inmediata)."""
    is_increase = change_type == "increase"
    color   = "#ef4444" if is_increase else "#22c55e"
    arrow   = "↑" if is_increase else "↓"
    pct_str = f"{arrow} {abs(change_pct):.0f}%" if change_pct else arrow
    old_str = f"${old_price:.0f}/mo"
    new_str = f"${new_price:.0f}/mo"
    subj    = f"📊 PricePulse weekly: {n_changes_this_week} price change{'s' if n_changes_this_week>1 else ''} this week"

    body = f"""
    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:28px;">
      <h2 style="font-size:17px;font-weight:800;margin:0 0 16px;">This week in SaaS pricing</h2>
      <div style="background:#1a2235;border-radius:8px;padding:14px;display:flex;align-items:center;gap:12px;margin-bottom:20px;">
        <div style="font-size:28px;">{tool_logo}</div>
        <div style="flex:1;">
          <div style="font-weight:700;">{tool_name} · {plan_name}</div>
          <div style="font-size:13px;color:rgba(240,244,255,.5);">{old_str} → <span style="color:{color};font-weight:700;">{new_str}</span></div>
        </div>
        <div style="color:{color};font-weight:800;">{pct_str}</div>
      </div>
      <a href="{APP_URL}" style="display:block;background:#6366f1;color:#fff;text-decoration:none;text-align:center;padding:12px;border-radius:8px;font-weight:700;font-size:14px;">See all changes →</a>
    </div>"""
    return _wrap(body).replace("{email}", email), subj

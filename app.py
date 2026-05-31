"""OrderPilot — FastAPI app.

Serves three things, all with ZERO config:
  • GET  /            → the in-browser CHAT SIMULATOR (talk to the bot, no Telegram)
  • POST /api/chat    → the bot-logic endpoint the simulator (and tests) call
  • GET  /admin/...   → the server-rendered admin dashboard (orders, conversations, stats)

The same `orderpilot.bot.handle_message()` powering /api/chat is what the live
Telegram bot uses — see orderpilot/telegram_bot.py. The live bot stays OFF
unless TELEGRAM_BOT_TOKEN is set.
"""
import json
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orderpilot import bot, config, db

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "orderpilot" / "templates"))

app = FastAPI(title="OrderPilot", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE / "orderpilot" / "static")),
          name="static")


def _plain(text: str) -> str:
    """Drop the bot's *bold* / _italic_ markers for plain-text admin previews."""
    return (text or "").replace("*", "").replace("_", "")


templates.env.filters["plain"] = _plain


@app.on_event("startup")
def _startup() -> None:
    db.init_db(seed=True)


def _ctx(request: Request, **extra) -> dict:
    base = {
        "request": request,
        "shop_name": config.SHOP_NAME,
        "shop_tagline": config.SHOP_TAGLINE,
        "demo_banner": config.DEMO_BANNER,
        "live_telegram": config.LIVE_TELEGRAM_ENABLED,
    }
    base.update(extra)
    return base


# --- simulator ----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def simulator(request: Request):
    return templates.TemplateResponse(request, "simulator.html", _ctx(request))


@app.post("/api/chat")
async def api_chat(request: Request):
    """Bot-logic endpoint. Body: {session_id, message}. Returns the replies."""
    payload = await request.json()
    session_id = (payload.get("session_id") or "sim-anon").strip()
    message = payload.get("message", "")
    replies = bot.handle_message(session_id, message, channel="simulator")
    return JSONResponse({"replies": replies})


@app.post("/api/reset")
async def api_reset(request: Request):
    """Start a fresh conversation in the simulator (greets with the menu)."""
    payload = await request.json()
    session_id = (payload.get("session_id") or "sim-anon").strip()
    with db.connect() as conn:
        db.ensure_conversation(conn, session_id)
        replies = bot.reset_to_menu(conn, session_id)
        bot._record(conn, session_id, replies)
    return JSONResponse({"replies": replies})


# --- admin --------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, status: str | None = None):
    with db.connect() as conn:
        st = db.stats(conn)
        orders = db.list_orders(conn, status=status)
        orders = [_order_row(o) for o in orders]
    return templates.TemplateResponse(
        request, "admin_dashboard.html",
        _ctx(request, stats=st, orders=orders, statuses=db.ORDER_STATUSES,
             active_status=status),
    )


@app.get("/admin/order/{order_id}", response_class=HTMLResponse)
def admin_order(request: Request, order_id: str):
    with db.connect() as conn:
        order = db.get_order(conn, order_id)
        if order is None:
            return HTMLResponse("Order not found", status_code=404)
        order = _order_row(order)
        conv = db.get_conversation(conn, order["conversation_id"]) \
            if order["conversation_id"] else None
        messages = db.get_messages(conn, order["conversation_id"]) \
            if order["conversation_id"] else []
        messages = [dict(m) for m in messages]
    return templates.TemplateResponse(
        request, "admin_order.html",
        _ctx(request, order=order, statuses=db.ORDER_STATUSES,
             conversation=dict(conv) if conv else None, messages=messages),
    )


@app.post("/admin/order/{order_id}/status")
def admin_set_status(order_id: str, status: str = Form(...)):
    with db.connect() as conn:
        db.set_order_status(conn, order_id, status)
    return RedirectResponse(f"/admin/order/{order_id}", status_code=303)


@app.get("/admin/conversations", response_class=HTMLResponse)
def admin_conversations(request: Request):
    with db.connect() as conn:
        convs = [dict(c) for c in db.list_conversations(conn)]
    return templates.TemplateResponse(
        request, "admin_conversations.html", _ctx(request, conversations=convs)
    )


@app.get("/admin/conversation/{conv_id}", response_class=HTMLResponse)
def admin_conversation(request: Request, conv_id: str):
    with db.connect() as conn:
        conv = db.get_conversation(conn, conv_id)
        if conv is None:
            return HTMLResponse("Conversation not found", status_code=404)
        messages = [dict(m) for m in db.get_messages(conn, conv_id)]
    return templates.TemplateResponse(
        request, "admin_conversation.html",
        _ctx(request, conversation=dict(conv), messages=messages),
    )


@app.post("/admin/reset")
def admin_reset():
    db.reset_db()
    return RedirectResponse("/admin", status_code=303)


def _order_row(o) -> dict:
    d = dict(o)
    d["items"] = json.loads(d["items"])
    d["item_count"] = sum(i["qty"] for i in d["items"])
    return d

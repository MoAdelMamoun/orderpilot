"""The conversational bot logic — a small, explicit state machine.

This is the heart of OrderPilot and is shared verbatim by BOTH the in-browser
simulator and the real Telegram handler. `handle_message()` takes a
conversation id and the customer's text, reads/writes conversation state in
SQLite, and returns the bot's reply lines. It never touches Telegram or the
web layer directly, which is exactly why the same logic can power either.
"""
import json

from . import config, db
from .catalog import CATALOG, FAQS, get_product, product_by_index

CURRENCY = config.CURRENCY

# Conversation states
IDLE = "IDLE"               # main menu
BROWSING = "BROWSING"       # picking items
ASK_QTY = "ASK_QTY"         # how many of the chosen item
ASK_NAME = "ASK_NAME"       # checkout: name
ASK_PHONE = "ASK_PHONE"     # checkout: phone
CONFIRM = "CONFIRM"         # confirm the order
ASK_ORDER_ID = "ASK_ORDER_ID"  # checking status
FAQ_MENU = "FAQ_MENU"       # browsing FAQs


def money(amount: float) -> str:
    return f"{CURRENCY}{amount:,.2f}"


def _menu_text() -> str:
    return (
        f"Welcome to *{config.SHOP_NAME}* ({config.SHOP_TAGLINE})! ☕\n"
        "How can I help you today?\n"
        "1️⃣  Browse the menu & order\n"
        "2️⃣  Check an order's status\n"
        "3️⃣  FAQ\n"
        "4️⃣  Talk to a human\n\n"
        "_Reply with a number. Type *menu* anytime to come back here._"
    )


def _catalog_text() -> str:
    lines = ["Here's our menu — reply with an item number to add it:"]
    for i, p in enumerate(CATALOG, start=1):
        lines.append(f"{i}. {p.emoji} {p.name} — {money(p.price)}")
    lines.append("\nType *done* to check out, or *menu* to go back.")
    return "\n".join(lines)


def _cart_summary(cart: list[dict]) -> str:
    if not cart:
        return "_(your order is empty)_"
    lines = []
    total = 0.0
    for item in cart:
        line_total = item["price"] * item["qty"]
        total += line_total
        lines.append(f"• {item['qty']} × {item['name']} — {money(line_total)}")
    lines.append(f"*Total: {money(total)}*")
    return "\n".join(lines)


def _cart_total(cart: list[dict]) -> float:
    return round(sum(i["price"] * i["qty"] for i in cart), 2)


def _faq_menu_text() -> str:
    lines = ["❓ *FAQ* — reply with a number:"]
    for i, (q, _) in enumerate(FAQS, start=1):
        lines.append(f"{i}. {q}")
    lines.append("\nType *menu* to go back.")
    return "\n".join(lines)


def reset_to_menu(conn, conv_id: str) -> list[str]:
    db.update_conversation(conn, conv_id, state=IDLE, context={})
    return [_menu_text()]


def handle_message(conv_id: str, text: str, channel: str = "simulator") -> list[str]:
    """Process one inbound message and return the bot's reply line(s).

    All state is persisted, so each call is self-contained — perfect for both a
    stateless web request and a Telegram update.
    """
    text = (text or "").strip()
    with db.connect() as conn:
        conv = db.ensure_conversation(conn, conv_id, channel=channel)
        db.add_message(conn, conv_id, "customer", text)

        ctx = json.loads(conv["context"] or "{}")
        state = conv["state"]
        low = text.lower()

        # Global commands available from any state.
        if low in ("menu", "start", "/start", "hi", "hello", "/menu"):
            replies = reset_to_menu(conn, conv_id)
            _record(conn, conv_id, replies)
            return replies

        replies = _dispatch(conn, conv_id, state, ctx, text, low, channel)
        _record(conn, conv_id, replies)
        return replies


def _record(conn, conv_id: str, replies: list[str]) -> None:
    for r in replies:
        db.add_message(conn, conv_id, "bot", r)


def _dispatch(conn, conv_id, state, ctx, text, low, channel) -> list[str]:
    cart = ctx.get("cart", [])

    if state == IDLE:
        if low in ("1", "menu order", "order", "browse"):
            db.update_conversation(conn, conv_id, state=BROWSING, context=ctx)
            return [_catalog_text()]
        if low in ("2", "status"):
            db.update_conversation(conn, conv_id, state=ASK_ORDER_ID, context=ctx)
            return ["Sure — what's your order number? (e.g. *ORD-1001*)"]
        if low in ("3", "faq"):
            db.update_conversation(conn, conv_id, state=FAQ_MENU, context=ctx)
            return [_faq_menu_text()]
        if low in ("4", "human", "agent", "help"):
            db.update_conversation(conn, conv_id, handoff=True)
            return [
                "🙋 I've flagged this chat for a human teammate.\n"
                "_(No real staff will reply; this just shows the handoff "
                "being recorded for the admin dashboard.)_\n\n"
                "Type *menu* to keep using the bot."
            ]
        return ["Sorry, I didn't catch that.", _menu_text()]

    if state == BROWSING:
        if low in ("done", "checkout", "check out"):
            if not cart:
                return ["Your order is empty — add an item first.", _catalog_text()]
            db.update_conversation(conn, conv_id, state=ASK_NAME, context=ctx)
            return [
                "Great! Here's your order:\n" + _cart_summary(cart) +
                "\n\nWhat *name* should we put on the order?"
            ]
        if low.isdigit():
            product = product_by_index(int(low))
            if product:
                ctx["pending_sku"] = product.sku
                db.update_conversation(conn, conv_id, state=ASK_QTY, context=ctx)
                return [f"How many *{product.name}* would you like? (reply with a number)"]
        return [
            "Please reply with an item number, *done* to check out, or *menu*.",
            _catalog_text(),
        ]

    if state == ASK_QTY:
        if low.isdigit() and int(low) > 0:
            qty = int(low)
            product = get_product(ctx.get("pending_sku", ""))
            if product:
                cart = ctx.get("cart", [])
                # Merge with an existing line for the same product.
                for item in cart:
                    if item["sku"] == product.sku:
                        item["qty"] += qty
                        break
                else:
                    cart.append({"sku": product.sku, "name": product.name,
                                 "price": product.price, "qty": qty})
                ctx["cart"] = cart
                ctx.pop("pending_sku", None)
                db.update_conversation(conn, conv_id, state=BROWSING, context=ctx)
                return [
                    f"Added *{qty} × {product.name}*.\n\nYour order so far:\n"
                    + _cart_summary(cart)
                    + "\n\nAdd another item (reply with a number) or type *done*."
                ]
            db.update_conversation(conn, conv_id, state=BROWSING, context=ctx)
            return [_catalog_text()]
        return ["Please reply with a quantity as a number (e.g. *2*)."]

    if state == ASK_NAME:
        name = text.strip()
        if len(name) < 2:
            return ["Please tell me the name for the order."]
        ctx["name"] = name
        db.update_conversation(conn, conv_id, state=ASK_PHONE,
                               context=ctx, customer_name=name)
        return [f"Thanks, {name}! What's a phone number we can reach you on?\n"
                "_(Please use a fake 555 number.)_"]

    if state == ASK_PHONE:
        ctx["phone"] = text.strip()
        db.update_conversation(conn, conv_id, state=CONFIRM, context=ctx)
        return [
            "Please confirm your order:\n\n"
            + _cart_summary(ctx.get("cart", []))
            + f"\n\n👤 {ctx.get('name')}\n📞 {ctx.get('phone')}\n\n"
            "Reply *yes* to confirm, or *no* to cancel."
        ]

    if state == CONFIRM:
        if low in ("yes", "y", "confirm"):
            cart = ctx.get("cart", [])
            order_id = db.create_order(
                conn, conversation_id=conv_id,
                customer_name=ctx.get("name", "Guest"),
                phone=ctx.get("phone", ""),
                address=ctx.get("address", "Pickup"),
                items=cart, channel=channel,
            )
            db.update_conversation(conn, conv_id, state=IDLE, context={})
            return [
                f"✅ Order *{order_id}* confirmed — {money(_cart_total(cart))}.\n"
                "We'll start preparing it shortly!\n\n"
                f"_(Sample order — nothing is really prepared.)_\n"
                f"Reply *2* anytime to check its status, or *menu* for the menu."
            ]
        if low in ("no", "n", "cancel"):
            db.update_conversation(conn, conv_id, state=IDLE, context={})
            return ["No problem — I've cancelled that order. Type *menu* to start over."]
        return ["Please reply *yes* to confirm or *no* to cancel."]

    if state == ASK_ORDER_ID:
        order = db.get_order(conn, text)
        db.update_conversation(conn, conv_id, state=IDLE, context=ctx)
        if order:
            items = json.loads(order["items"])
            human = {
                "new": "received and waiting to be confirmed",
                "confirmed": "confirmed",
                "preparing": "being prepared right now",
                "done": "ready / completed",
                "cancelled": "cancelled",
            }.get(order["status"], order["status"])
            return [
                f"📦 Order *{order['id']}* is *{human}*.\n"
                + _cart_summary(items)
                + "\n\nType *menu* for anything else."
            ]
        return [
            f"I couldn't find an order with that number. "
            f"Order numbers look like *ORD-1001*.\n\nType *menu* to go back."
        ]

    if state == FAQ_MENU:
        if low.isdigit() and 1 <= int(low) <= len(FAQS):
            q, a = FAQS[int(low) - 1]
            return [f"*{q}*\n{a}\n\n" + _faq_menu_text()]
        return ["Please pick a question number, or type *menu*.", _faq_menu_text()]

    # Fallback — unknown state, recover gracefully.
    return reset_to_menu(conn, conv_id)

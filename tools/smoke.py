"""End-to-end smoke check of the OrderPilot bot logic (no FastAPI, no Telegram).

Drives a full conversation through `bot.handle_message()` — browse, add an
item, check out, confirm — then asserts the order was persisted to SQLite and
is visible to the admin queries. Uses a throwaway temp database.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point the app at a throwaway DB before importing anything that reads config.
import os
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["ORDERPILOT_DB_PATH"] = _tmp.name

from orderpilot import bot, db  # noqa: E402


def say(conv, text):
    replies = bot.handle_message(conv, text)
    print(f"  > {text!r}")
    for r in replies:
        first = r.splitlines()[0]
        print(f"    bot: {first[:70]}")
    return replies


def main():
    db.init_db(seed=True)
    conv = "smoke-session"

    print("Conversation:")
    say(conv, "hi")            # menu
    say(conv, "1")             # browse
    say(conv, "2")             # choose Cappuccino (item #2)
    say(conv, "2")             # qty 2
    say(conv, "5")             # choose Butter Croissant (item #5)
    say(conv, "1")             # qty 1
    say(conv, "done")          # checkout
    say(conv, "Dana Example")  # name
    say(conv, "+1-555-0123")   # phone
    final = say(conv, "yes")   # confirm

    # The confirmation reply must contain an order id.
    confirm_text = " ".join(final)
    assert "ORD-" in confirm_text, "no order id in confirmation"
    order_id = confirm_text.split("ORD-")[1].split("*")[0].split(" ")[0].strip()
    order_id = "ORD-" + order_id
    print("\nCreated:", order_id)

    with db.connect() as conn:
        order = db.get_order(conn, order_id)
        assert order is not None, "order was not persisted"
        items = __import__("json").loads(order["items"])
        assert sum(i["qty"] for i in items) == 3, "expected 3 items total"
        assert abs(order["total"] - (4.50 * 2 + 3.25)) < 0.001, "total mismatch"
        assert order["customer_name"] == "Dana Example"

        # Status workflow.
        assert db.set_order_status(conn, order_id, "preparing")
        assert not db.set_order_status(conn, order_id, "not-a-status")

        st = db.stats(conn)
        msgs = db.get_messages(conn, conv)

    # Status lookup via the bot.
    status_reply = " ".join(say(conv, "2") + say(conv, order_id))
    assert "being prepared" in status_reply, "status lookup did not reflect update"

    # Human handoff path.
    say(conv, "4")
    with db.connect() as conn:
        c = db.get_conversation(conn, conv)
        assert c["handoff"] == 1, "handoff flag not set"

    print("\nStats:", st)
    print("messages persisted:", len(msgs))
    print("seeded + new orders:", st["total_orders"])
    assert st["total_orders"] >= 4, "expected seed orders + the new one"
    print("\nOK: bot + persistence healthy")

    Path(_tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()

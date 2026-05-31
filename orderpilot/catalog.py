"""The fictional shop's product catalog.

Hard-coded, obviously-fake menu for a make-believe coffee shop. No prices,
products, or shops here are real.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: float
    emoji: str


CATALOG: list[Product] = [
    Product("ESP", "Espresso", 3.00, "☕"),
    Product("CAP", "Cappuccino", 4.50, "☕"),
    Product("LAT", "Caffè Latte", 4.75, "🥛"),
    Product("CLD", "Cold Brew", 5.00, "🧊"),
    Product("CRS", "Butter Croissant", 3.25, "🥐"),
    Product("MUF", "Blueberry Muffin", 3.50, "🧁"),
]

_BY_SKU = {p.sku: p for p in CATALOG}


def get_product(sku: str) -> Product | None:
    return _BY_SKU.get(sku)


def product_by_index(index: int) -> Product | None:
    """1-based lookup, matching how items are numbered to the customer."""
    if 1 <= index <= len(CATALOG):
        return CATALOG[index - 1]
    return None


# Static FAQ answers for the fictional shop.
FAQS: list[tuple[str, str]] = [
    ("What are your opening hours?",
     "We're open every day, 7:00 AM – 6:00 PM (demo answer)."),
    ("Where are you located?",
     "123 Example Street, Springfield (a fictional address for this demo)."),
    ("Do you offer delivery?",
     "Yes — free delivery on demo orders within 3 km. This is sample copy only."),
    ("What payment methods do you accept?",
     "Cash and major cards on pickup/delivery. No real payment is taken in the demo."),
]

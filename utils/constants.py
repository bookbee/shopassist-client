"""Project-wide constants."""
from __future__ import annotations

GST_RATE: float = 0.18
FREE_SHIPPING_THRESHOLD: int = 999
SHIPPING_FLAT_FEE: int = 79

CURRENCY: str = "₹"

PAGES: dict[str, str] = {
    "Home": "home",
    "Catalog": "catalog",
    "Cart": "cart",
    "Orders": "orders",
    "Profile": "profile",
    "About": "about",
}

# Pages reachable only through in-app actions (not the navbar)
HIDDEN_PAGES: tuple[str, ...] = ("product", "checkout")

CATEGORIES: tuple[str, ...] = (
    "All",
    "Apparel",
    "Drinkware",
    "Stationery",
    "Accessories",
    "Memorabilia",
)

DELIVERY_DAYS_ESTIMATE: int = 5

TICKET_RESPONSE_TIME: str = "within 24 hours"

CHAT_QUICK_ACTIONS: tuple[str, ...] = (
    "Where is order ord-1001?",
    "What material is the hoodie?",
    "Suggest gifts below ₹1000",
    "I want to return a product",
)

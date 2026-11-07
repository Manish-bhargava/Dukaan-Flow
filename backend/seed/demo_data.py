"""Deterministic demo data for local development and testing. All people, shops, phone
numbers, GSTINs and brands are fictional.

Demo-data assumptions (business has NOT confirmed these — see PROJECT.md §12):
- Dealer prices are stored per PIECE (price_basis="PIECE"). The supplied sample prices
  (₹8.10 for a 75g biscuit with 96 per case) look like per-piece prices, but this must be
  confirmed. price_basis is configurable per retailer price row.
- Dealer prices EXCLUDE GST (tax_inclusive=False). Also configurable per price row.
- GST rates are illustrative demo values per product; confirm actual HSN rates.
- Scheme thresholds and stock are counted in cases (the product's order_unit).
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Fixed dates keep the seed deterministic.
PRICE_EFFECTIVE_FROM = datetime(2026, 1, 1, tzinfo=IST)
SCHEME_STARTS_AT = datetime(2026, 1, 1, tzinfo=IST)

DEMO_PRICE_BASIS = "PIECE"
DEMO_TAX_INCLUSIVE = False

# key -> (name, phone, role)
STAFF_USERS = {
    "admin": ("Vivek Malhotra", "9000000001", "ADMIN"),
    "order_desk": ("Neha Tiwari", "9000000002", "ORDER_DESK"),
    "salesman_sunil": ("Sunil Yadav", "9000000003", "SALESMAN"),
    "salesman_deepak": ("Deepak Verma", "9000000004", "SALESMAN"),
}

# key -> shop details. Price multiplier creates retailer-specific prices from the base price.
RETAILERS = {
    "sharma": {
        "shop_name": "Sharma Kirana Store",
        "owner_name": "Ramesh Sharma",
        "phone": "9000000101",
        "address": "12, Napier Town Main Road",
        "gstin": "23AAAPS1234A1Z5",
        "salesman": "salesman_sunil",
        "price_multiplier": Decimal("1.00"),  # gets exactly the sample dealer prices
        "credit_limit": Decimal("50000.00"),
        "outstanding": Decimal("35000.00"),
    },
    "gupta": {
        "shop_name": "Gupta General Store",
        "owner_name": "Mahesh Gupta",
        "phone": "9000000102",
        "address": "45, Wright Town",
        "gstin": None,
        "salesman": "salesman_sunil",
        "price_multiplier": Decimal("0.98"),
        "credit_limit": Decimal("100000.00"),
        "outstanding": Decimal("20000.00"),
    },
    "jain": {
        "shop_name": "Jain Provision Store",
        "owner_name": "Anil Jain",
        "phone": "9000000103",
        "address": "8, Civil Lines",
        "gstin": "23AABPJ5678B1Z2",
        "salesman": "salesman_sunil",
        "price_multiplier": Decimal("1.01"),
        "credit_limit": Decimal("75000.00"),
        "outstanding": Decimal("0.00"),
    },
    "patel": {
        "shop_name": "Patel Kirana & General",
        "owner_name": "Suresh Patel",
        "phone": "9000000104",
        "address": "Gorakhpur Bazaar",
        "gstin": None,
        "salesman": "salesman_deepak",
        "price_multiplier": Decimal("1.02"),
        "credit_limit": Decimal("25000.00"),
        "outstanding": Decimal("24500.00"),  # nearly at limit: useful for credit-hold demos
    },
    "agrawal": {
        "shop_name": "Agrawal Traders",
        "owner_name": "Pankaj Agrawal",
        "phone": "9000000105",
        "address": "Adhartal Main Road",
        "gstin": "23AACPA9012C1Z8",
        "salesman": None,  # unassigned
        "price_multiplier": Decimal("0.97"),
        "credit_limit": Decimal("200000.00"),
        "outstanding": Decimal("60000.00"),
    },
}
RETAILER_CITY = "Jabalpur"

# key -> (name, phone, email, retailer key). Retailers sign in with phone + OTP; the OTP
# is emailed to this address.
RETAILER_USERS = {
    "retailer_sharma": ("Ramesh Sharma", "9000000101", "sharma.kirana@example.com", "sharma"),
    "retailer_gupta": ("Mahesh Gupta", "9000000102", "gupta.general@example.com", "gupta"),
    # Demo login with a real inbox, so the OTP email can be shown in a live demo.
    "retailer_jain": ("Anil Jain", "9000000103", "testemail4dukaanflow@gmail.com", "jain"),
}

CATEGORIES = ["Biscuits", "Home Care", "Tea", "Noodles"]

# (sku, name, brand, category, pack_size, units_per_case, base dealer price, stock cases, gst %)
PRODUCTS = [
    ("SKU-BS-075", "Glucose Biscuit", "Sunrise Foods", "Biscuits", "75g", 96, "8.10", 340, "5"),
    ("SKU-BS-150", "Glucose Biscuit", "Sunrise Foods", "Biscuits", "150g", 48, "16.20", 120, "5"),
    ("SKU-CB-100", "Cream Biscuit", "Sunrise Foods", "Biscuits", "100g", 60, "18.50", 75, "5"),
    ("SKU-DT-1KG", "Detergent Powder", "Dhavala Home Care", "Home Care", "1kg", 20, "101.50", 85, "18"),
    ("SKU-DT-500", "Detergent Powder", "Dhavala Home Care", "Home Care", "500g", 40, "52.00", 12, "18"),
    ("SKU-DB-150", "Detergent Bar", "Dhavala Home Care", "Home Care", "150g", 72, "9.50", 200, "18"),
    ("SKU-DW-500", "Dishwash Liquid", "Dhavala Home Care", "Home Care", "500ml", 24, "85.00", 8, "18"),
    ("SKU-TE-250", "Tea Leaf", "Chai Bahar", "Tea", "250g", 40, "118.00", 0, "5"),
    ("SKU-TE-500", "Tea Leaf", "Chai Bahar", "Tea", "500g", 24, "230.00", 30, "5"),
    ("SKU-NS-070", "Instant Noodles", "Swaad Foods", "Noodles", "70g", 96, "11.20", 150, "5"),
]
BASE_UNIT = "piece"
ORDER_UNIT = "case"

# An expired price for one retailer, to verify that only the currently effective price is used.
HISTORICAL_PRICES = [
    # (retailer key, sku, price, effective_from, effective_to)
    ("sharma", "SKU-BS-075", "7.90", datetime(2025, 7, 1, tzinfo=IST), PRICE_EFFECTIVE_FROM),
]

# (key, sku, type, min_quantity, free_quantity, discount %, starts_at, ends_at)
SCHEMES = [
    ("bs075_buy10_get1", "SKU-BS-075", "FREE_GOODS", "10", "1", None, SCHEME_STARTS_AT, None),
    ("dt1kg_5plus_3pct", "SKU-DT-1KG", "SLAB_DISCOUNT", "5", None, "3", SCHEME_STARTS_AT, None),
    # Expired scheme: must not be returned as applicable.
    (
        "ns070_summer_buy20_get2",
        "SKU-NS-070",
        "FREE_GOODS",
        "20",
        "2",
        None,
        datetime(2026, 4, 1, tzinfo=IST),
        datetime(2026, 7, 1, tzinfo=IST),
    ),
]

# (retailer key, alias as the retailer writes it, sku). Same phrase can map differently per retailer.
ALIASES = [
    ("sharma", "chhota biscuit", "SKU-BS-075"),
    ("sharma", "bada biscuit", "SKU-BS-150"),
    ("sharma", "washing powder", "SKU-DT-1KG"),
    ("gupta", "washing powder", "SKU-DT-500"),
    ("gupta", "chai patti 250", "SKU-TE-250"),
    ("jain", "noodle packet", "SKU-NS-070"),
]

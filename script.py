#!/usr/bin/env python3
"""
FitForYou – Backdated Git commit history generator.
Tailored to the actual project: Flask app, models, storage, templates.
Run from inside your git repo folder.
"""

import subprocess
import random
from datetime import datetime, timedelta
import os

# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────
CONTRIBUTORS = [
    {"name": "Adam Grotkovský",  "email": "xgrotkovsky@stuba.sk"},
    {"name": "Oliver Haban",     "email": "xhaban@stuba.sk"},
    {"name": "Jakub Hidvégi",    "email": "xhidvegi@stuba.sk"},
    {"name": "Viktor Lipčák",    "email": "viktor.lipcak66@gmail.com"},
]

DAYS_BACK     = 30
TOTAL_COMMITS = 40   # feels natural for a ~1 month Flask project

# ─────────────────────────────────────────────
# Commit messages — realistic for THIS project
# ─────────────────────────────────────────────
# Format: (message, weight)
# Higher weight = appears more often (routine work)
WEIGHTED_MESSAGES = [
    # ── Project bootstrap ───────────────────────────────────────
    ("Initial project setup, Flask app skeleton",                          1),
    ("Add requirements.txt and .gitignore",                                1),
    ("Set up DataStore and JSON repository layer",                         1),
    ("Add seed script with demo users and categories",                     1),

    # ── Models ──────────────────────────────────────────────────
    ("Define User, Category, Product models",                              1),
    ("Add Order and OrderItem models with lifecycle statuses",             1),
    ("Add Payment model, card and bank_transfer support",                  1),
    ("Add DesignRequest model and status labels",                          1),
    ("Add Supplier, SupplierOrder, SupplierOrderItem models",              1),
    ("Add Delivery and ClaimRecord models",                                1),
    ("Add price_over_limit helper to DesignRequest",                       2),
    ("Fix custom_price() surcharge calculation in Product",                2),

    # ── Storage layer ───────────────────────────────────────────
    ("Implement generic Repository with upsert and filter",                1),
    ("Add thread-safe file locking to Repository.save()",                  2),
    ("Add UserRepo.by_email() and by_role() finders",                      2),
    ("Add OrderRepo.draft_for() and non_draft() helpers",                  2),
    ("Add DeliveryRepo active/completed/by_worker filters",                2),
    ("Fix next_id() when JSON file is empty",                              2),

    # ── Auth & routing ──────────────────────────────────────────
    ("Implement login, logout and registration routes",                    1),
    ("Add role_required decorator for portal access control",              1),
    ("Add inject_cart_count context processor",                            2),
    ("Fix redirect after login for non-customer roles",                    2),

    # ── Catalog (UC01) ──────────────────────────────────────────
    ("Add catalog index with category filter",                             2),
    ("Add product detail page with similar products",                      2),
    ("Implement cart add route (UC01a)",                                   2),
    ("Implement custom dimensions cart route (UC01b)",                     2),
    ("Add dimension validation – reject out-of-range values",              2),
    ("Add cart update and remove item routes",                             2),

    # ── Checkout & Payment (UC02) ────────────────────────────────
    ("Add checkout route with delivery method selection",                  2),
    ("Warn on delivery date less than 3 days out",                        2),
    ("Implement card payment flow with transaction ID",                    2),
    ("Add bank transfer alt flow with variable symbol",                    2),
    ("Add simulate_fail flag for failed payment testing",                  2),
    ("Auto-create Delivery record after successful payment",               2),
    ("Add admin route to manually confirm bank transfer",                  2),

    # ── Design requests (UC03) ───────────────────────────────────
    ("Add customer design request form and submission",                    2),
    ("Add designer dashboard with pending/in-progress split",              2),
    ("Implement designer_work: submit design and cancel",                  2),
    ("Flash warning when estimated price exceeds limit by 40%",            2),
    ("Add customer approve/revision/cancel design routes",                 2),

    # ── Warehouse (UC04) ─────────────────────────────────────────
    ("Add warehouse dashboard with open supplier orders",                  2),
    ("Implement receive route: full, partial, claim actions",              2),
    ("Auto-update product stock on goods receipt",                         2),
    ("Create ClaimRecord on damaged goods (UC04 exception)",               2),
    ("Add warehouse inventory view",                                       2),

    # ── Admin portal (UC05) ──────────────────────────────────────
    ("Add admin dashboard with summary counts",                            2),
    ("Add catalogue management: list, new, edit, deactivate",             2),
    ("Add admin orders and design request overview pages",                 2),

    # ── Delivery (UC06 / UC07) ───────────────────────────────────
    ("Add field worker dashboard with unassigned deliveries",              2),
    ("Implement confirm_delivery and reschedule actions",                  2),
    ("Add assembly start/confirm flow (UC07)",                             2),
    ("Add clearance service add/decline actions (UC08)",                   2),
    ("Add damage_claim action and ClaimRecord creation",                   2),
    ("Mark delivery as failed and notify customer (UC06 exception)",       2),
    ("Add customer cancel-after-failed-delivery with refund",              2),

    # ── Templates ───────────────────────────────────────────────
    ("Add base layout with navbar and flash messages",                     1),
    ("Add login and registration templates",                               2),
    ("Add catalog index and product detail templates",                     2),
    ("Add cart template with quantity controls",                           2),
    ("Add checkout and payment templates",                                 2),
    ("Add order list and order detail templates",                          2),
    ("Add designer dashboard and work templates",                          2),
    ("Add warehouse receive and inventory templates",                      2),
    ("Add admin catalog and orders templates",                             2),
    ("Add delivery dashboard and detail templates",                        2),
    ("Add 403 and 404 error page templates",                               2),
    ("Fix broken Jinja2 loop variable in cart template",                   3),
    ("Fix missing url_for reference in payment template",                  3),
    ("Improve mobile responsiveness in catalog layout",                    3),
    ("Add Bootstrap badge colors for order status labels",                 3),

    # ── Polish & fixes ───────────────────────────────────────────
    ("Add Slovak flash messages across all routes",                        3),
    ("Refactor role_home() to centralise dashboard redirects",             3),
    ("Clean up unused imports in app.py",                                  3),
    ("Add missing order.all() method to OrderRepo",                        3),
    ("Fix designer filter_fn lambda for my_all query",                     3),
    ("Seed: add demo paid order with scheduled delivery",                  2),
    ("Seed: add two supplier orders with items for UC04 demo",             2),
    ("Update README with setup and demo credentials",                      2),
    ("Final cleanup and code review fixes",                                1),
]

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def build_pool():
    pool = []
    for msg, weight in WEIGHTED_MESSAGES:
        pool.extend([msg] * weight)
    return pool

def random_date_in_range():
    now   = datetime.now()
    start = now - timedelta(days=DAYS_BACK)
    secs  = random.randint(0, int((now - start).total_seconds()))
    dt    = start + timedelta(seconds=secs)
    # Plausible student hours: 10:00 – 23:30
    dt    = dt.replace(
        hour=random.randint(10, 23),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
    )
    return dt

def format_date(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def make_commit(contributor, message, date_str):
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"]     = date_str
    env["GIT_COMMITTER_DATE"]  = date_str
    env["GIT_AUTHOR_NAME"]     = contributor["name"]
    env["GIT_AUTHOR_EMAIL"]    = contributor["email"]
    env["GIT_COMMITTER_NAME"]  = contributor["name"]
    env["GIT_COMMITTER_EMAIL"] = contributor["email"]

    result = subprocess.run(
        ["git", "commit", "--allow-empty", "-m", message],
        env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ⚠️  Error: {result.stderr.strip()}")
    else:
        print(f"  ✅ [{date_str}] {contributor['name']}: {message}")

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    check = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        print("❌ Not inside a Git repository! Run: git init first.")
        return

    print(f"\n🚀 Generating {TOTAL_COMMITS} backdated commits over the last {DAYS_BACK} days...\n")

    pool     = build_pool()
    dates    = sorted([random_date_in_range() for _ in range(TOTAL_COMMITS)])
    used     = set()
    messages = []

    for _ in range(TOTAL_COMMITS):
        # Prefer unused messages; fall back to any if pool exhausted
        candidates = [m for m in pool if m not in used]
        if not candidates:
            candidates = pool
        msg = random.choice(candidates)
        used.add(msg)
        messages.append(msg)

    # First commit always goes to Adam (project owner feel)
    for i in range(TOTAL_COMMITS):
        contributor = CONTRIBUTORS[0] if i == 0 else CONTRIBUTORS[i % len(CONTRIBUTORS)]
        make_commit(contributor, messages[i], format_date(dates[i]))

    print(f"\n✅ Done! {TOTAL_COMMITS} commits added.")
    print("👉 Now push with:  git push origin main\n")

if __name__ == "__main__":
    main()
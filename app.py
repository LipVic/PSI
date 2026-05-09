"""
FitForYou – Flask web application.
Data is stored in JSON files via the DataStore / Repository layer (storage.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, abort,
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user,
)

from models import (
    User, Order, OrderItem, Payment,
    DesignRequest, Delivery, ClaimRecord,
)
from storage import DataStore
from seed import seed

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "fitforyou-secret-key-2024"

store = DataStore()
seed(store)

login_manager = LoginManager(app)
login_manager.login_view = "auth_login"
login_manager.login_message = "Prosim prihlasite sa."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str):
    return store.users.get(int(user_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash("Nemáte oprávnenie na túto akciu.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_cart_count():
    count = 0
    if current_user.is_authenticated:
        draft = store.orders.draft_for(current_user.id)
        if draft:
            count = len(store.order_items.by_order(draft.id))
    return {"cart_count": count}


def _role_home(role: str) -> str:
    return {
        "designer":     url_for("designer_dashboard"),
        "admin":        url_for("admin_dashboard"),
        "warehouse":    url_for("warehouse_dashboard"),
        "field_worker": url_for("delivery_dashboard"),
    }.get(role, url_for("index"))


# ---------------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    categories = store.categories.all()
    featured = store.products.available()[:6]
    return render_template("index.html", categories=categories, featured=featured)


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
@app.route("/prihlasenie", methods=["GET", "POST"])
def auth_login():
    if current_user.is_authenticated:
        return redirect(_role_home(current_user.role))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = store.users.by_email(email)
        if user and user.check_password(password):
            login_user(user)
            flash(f"Vitajte, {user.name}!", "success")
            return redirect(request.args.get("next") or _role_home(user.role))
        flash("Nespravny e-mail alebo heslo.", "danger")
    return render_template("auth/login.html")


@app.route("/registracia", methods=["GET", "POST"])
def auth_register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip()
        pwd     = request.form.get("password", "")
        phone   = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        if store.users.by_email(email):
            flash("Tento e-mail je uz registrovany.", "warning")
            return render_template("auth/register.html")
        user = User(
            id=store.users.next_id(), name=name, email=email,
            password_hash="", role="customer",
            phone=phone, address=address,
        )
        user.set_password(pwd)
        store.users.save(user)
        login_user(user)
        flash("Registracia uspesna! Vitajte.", "success")
        return redirect(url_for("index"))
    return render_template("auth/register.html")


@app.route("/odhlasenie")
@login_required
def auth_logout():
    logout_user()
    flash("Boli ste odhlaseni.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# CATALOG  – UC01 / UC01a / UC01b
# ---------------------------------------------------------------------------
@app.route("/katalog")
def catalog_index():
    categories = store.categories.all()
    cat_id = request.args.get("kategoria", type=int)
    products = store.products.by_category(cat_id) if cat_id else store.products.available()
    return render_template("catalog/index.html",
                           categories=categories, products=products, selected_cat=cat_id)


@app.route("/katalog/produkt/<int:product_id>")
def catalog_product(product_id):
    product = store.products.get(product_id)
    if not product:
        abort(404)
    category = store.categories.get(product.category_id)
    similar = [p for p in store.products.by_category(product.category_id) if p.id != product_id][:4]
    return render_template("catalog/product_detail.html",
                           product=product, category=category, similar=similar)


# ---------------------------------------------------------------------------
# CART
# ---------------------------------------------------------------------------
def _get_or_create_draft() -> Order:
    draft = store.orders.draft_for(current_user.id)
    if not draft:
        draft = Order(id=store.orders.next_id(), customer_id=current_user.id)
        store.orders.save(draft)
    return draft


@app.route("/kosik")
@login_required
def cart_view():
    draft = store.orders.draft_for(current_user.id)
    items = store.order_items.by_order(draft.id) if draft else []
    products = {p.id: p for p in store.products.all()}
    return render_template("orders/cart.html", order=draft, items=items, products=products)


@app.route("/kosik/pridat/<int:product_id>", methods=["POST"])
@login_required
def cart_add(product_id):
    """UC01a – add standard item to cart."""
    product = store.products.get(product_id)
    if not product:
        abort(404)
    # UC01a exception: product unavailable
    if not product.is_available or product.stock < 1:
        flash("Produkt nie je momentalne dostupny.", "warning")
        return redirect(url_for("catalog_product", product_id=product_id))

    qty = max(1, int(request.form.get("quantity", 1)))
    draft = _get_or_create_draft()
    existing = next(
        (i for i in store.order_items.by_order(draft.id)
         if i.product_id == product_id and not i.is_custom), None)
    if existing:
        existing.quantity += qty
        store.order_items.save(existing)
    else:
        store.order_items.save(OrderItem(
            id=store.order_items.next_id(), order_id=draft.id,
            product_id=product_id, quantity=qty,
            unit_price=product.price, is_custom=False,
        ))
    store.recalculate_order(draft)
    flash(f"Produkt '{product.name}' bol pridany do kosika.", "success")
    return redirect(url_for("catalog_product", product_id=product_id))


@app.route("/kosik/pridat-na-mieru/<int:product_id>", methods=["POST"])
@login_required
def cart_add_custom(product_id):
    """UC01b – add custom-dimensions item to cart."""
    product = store.products.get(product_id)
    if not product:
        abort(404)
    if not product.allows_custom:
        flash("Tento produkt nepodporuje vyrobu na mieru.", "warning")
        return redirect(url_for("catalog_product", product_id=product_id))

    width  = request.form.get("custom_width",  type=float)
    height = request.form.get("custom_height", type=float)
    depth  = request.form.get("custom_depth",  type=float)
    color  = request.form.get("custom_color",  "").strip()
    special = request.form.get("special_requirements", "").strip()

    if not (width and height and depth):
        flash("Vyplnte prosim vsetky rozmery (sirka, vyska, hlbka).", "danger")
        return redirect(url_for("catalog_product", product_id=product_id))

    # UC01b exception – unrealistic dimensions
    if width < 10 or width > 500 or height < 10 or height > 500 or depth < 5 or depth > 300:
        flash("Zadane rozmery su nerealisticke. Povolene: sirka 10-500 cm, vyska 10-500 cm, hlbka 5-300 cm.", "danger")
        return redirect(url_for("catalog_product", product_id=product_id))

    draft = _get_or_create_draft()
    store.order_items.save(OrderItem(
        id=store.order_items.next_id(), order_id=draft.id,
        product_id=product_id, quantity=1,
        unit_price=product.custom_price(), is_custom=True,
        custom_width=width, custom_height=height, custom_depth=depth,
        custom_color=color, special_requirements=special,
    ))
    store.recalculate_order(draft)

    # UC01b alt: special requirements – note for staff
    if special:
        flash(f"Produkt '{product.name}' (na mieru) pridany. Specialne poziadavky budu spracovane nasim timom.", "info")
    else:
        flash(f"Produkt '{product.name}' na mieru pridany do kosika.", "success")
    return redirect(url_for("cart_view"))


@app.route("/kosik/odstraniť/<int:item_id>", methods=["POST"])
@login_required
def cart_remove(item_id):
    item = store.order_items.get(item_id)
    if not item:
        abort(404)
    draft = store.orders.get(item.order_id)
    if draft.customer_id != current_user.id:
        abort(403)
    store.order_items.delete(item_id)
    store.recalculate_order(draft)
    flash("Polozka bola odstranena z kosika.", "info")
    return redirect(url_for("cart_view"))


@app.route("/kosik/aktualizovat/<int:item_id>", methods=["POST"])
@login_required
def cart_update(item_id):
    item = store.order_items.get(item_id)
    if not item:
        abort(404)
    draft = store.orders.get(item.order_id)
    if draft.customer_id != current_user.id:
        abort(403)
    item.quantity = max(1, int(request.form.get("quantity", 1)))
    store.order_items.save(item)
    store.recalculate_order(draft)
    return redirect(url_for("cart_view"))


# ---------------------------------------------------------------------------
# CHECKOUT + PAYMENT  – UC01 / UC02
# ---------------------------------------------------------------------------
@app.route("/pokladna", methods=["GET", "POST"])
@login_required
def checkout():
    """UC01 – choose delivery, confirm order."""
    draft = store.orders.draft_for(current_user.id)
    if not draft or not store.order_items.by_order(draft.id):
        flash("Kosik je prazdny.", "warning")
        return redirect(url_for("catalog_index"))
    store.recalculate_order(draft)

    if request.method == "POST":
        method  = request.form.get("delivery_method", "pickup")
        address = request.form.get("delivery_address", "").strip()
        date_s  = request.form.get("delivery_date", "")
        notes   = request.form.get("notes", "").strip()

        if method in ("delivery", "delivery_assembly") and not address:
            flash("Zadajte dorucuvaciu adresu.", "danger")
            return redirect(url_for("checkout"))

        # UC01 exception: date too soon
        if date_s:
            try:
                chosen = datetime.strptime(date_s, "%Y-%m-%d")
                if chosen < datetime.utcnow() + timedelta(days=3):
                    flash("Upozornenie: Zvoleny datum je prilis skoro. Kontaktujte zakaznicku podporu pre overenie dostupnosti dorucenia.", "warning")
            except ValueError:
                date_s = ""

        draft.delivery_method  = method
        draft.delivery_address = address if method == "delivery" else "Osobny odber"
        draft.delivery_date    = date_s
        draft.notes            = notes
        draft.status           = "pending_payment"
        draft.updated_at       = datetime.utcnow().isoformat()
        store.orders.save(draft)
        return redirect(url_for("payment_view", order_id=draft.id))

    est_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
    items    = store.order_items.by_order(draft.id)
    products = {p.id: p for p in store.products.all()}
    return render_template("orders/checkout.html",
                           order=draft, items=items, products=products, est_date=est_date)


@app.route("/platba/<int:order_id>", methods=["GET", "POST"])
@login_required
def payment_view(order_id):
    """UC02 – pay the order."""
    order = store.orders.get(order_id)
    if not order:
        abort(404)
    if order.customer_id != current_user.id:
        abort(403)
    if order.status not in ("pending_payment", "awaiting_payment"):
        flash("Tato objednavka nie je cakajuca na platbu.", "info")
        return redirect(url_for("orders_list"))

    if request.method == "POST":
        method = request.form.get("payment_method", "card")

        if method == "bank_transfer":
            # UC02 alt: bank transfer
            ref = f"VS{order.id:06d}"
            store.payments.save(Payment(
                id=store.payments.next_id(), order_id=order.id,
                amount=order.total_price, method="bank_transfer",
                status="pending", bank_reference=ref,
            ))
            order.status = "awaiting_payment"
            order.updated_at = datetime.utcnow().isoformat()
            store.orders.save(order)
            flash(f"Bankovy prevod: posli {order.total_price:.2f} EUR na IBAN SK00 0000 0000 0000 0000 0000, variabilny symbol {ref}. Objednavka bude potvrdena po prijati platby.", "info")
            return redirect(url_for("order_detail", order_id=order.id))

        # UC02 exception: simulate failed payment
        if request.form.get("simulate_fail") == "1":
            store.payments.save(Payment(
                id=store.payments.next_id(), order_id=order.id,
                amount=order.total_price, method="card", status="failed",
            ))
            order.status = "awaiting_payment"
            order.updated_at = datetime.utcnow().isoformat()
            store.orders.save(order)
            flash("Platba zamietnutá: nedostatocny zostatok na ucte. Objednavka caka na platbu.", "danger")
            return redirect(url_for("order_detail", order_id=order.id))

        # Successful card payment
        txn = str(uuid.uuid4())[:8].upper()
        store.payments.save(Payment(
            id=store.payments.next_id(), order_id=order.id,
            amount=order.total_price, method="card", status="completed",
            transaction_id=txn, completed_at=datetime.utcnow().isoformat(),
        ))
        order.status = "paid"
        order.updated_at = datetime.utcnow().isoformat()
        store.orders.save(order)

        if order.delivery_method in ("delivery", "delivery_assembly"):
            requires_asm = order.delivery_method == "delivery_assembly"
            store.deliveries.save(Delivery(
                id=store.deliveries.next_id(), order_id=order.id,
                status="scheduled",
                scheduled_date=order.delivery_date or (datetime.utcnow() + timedelta(days=7)).isoformat(),
                address=order.delivery_address,
                requires_assembly=requires_asm,
                assembly_status="pending" if requires_asm else "",
            ))

        flash(f"Platba uspesna (TXN: {txn}). Faktura vam bola odoslana na e-mail.", "success")
        return redirect(url_for("order_detail", order_id=order.id))

    items    = store.order_items.by_order(order.id)
    products = {p.id: p for p in store.products.all()}
    return render_template("payment/pay.html", order=order, items=items, products=products)


@app.route("/platba/<int:order_id>/potvrdit-prevod", methods=["POST"])
@login_required
@role_required("admin", "warehouse")
def payment_confirm_bank(order_id):
    """UC02 alt: manually confirm bank transfer."""
    order = store.orders.get(order_id)
    pay   = store.payments.by_order(order_id)
    if pay and pay.method == "bank_transfer" and pay.status == "pending":
        pay.status       = "completed"
        pay.completed_at = datetime.utcnow().isoformat()
        store.payments.save(pay)
        order.status     = "paid"
        order.updated_at = datetime.utcnow().isoformat()
        store.orders.save(order)
        flash("Bankovy prevod bol potvrdeny.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


# ---------------------------------------------------------------------------
# ORDERS
# ---------------------------------------------------------------------------
@app.route("/objednavky")
@login_required
def orders_list():
    if current_user.role == "customer":
        orders = [o for o in store.orders.by_customer(current_user.id) if o.status != "draft"]
    elif current_user.role == "admin":
        orders = store.orders.non_draft()
    else:
        orders = []
    orders.sort(key=lambda o: o.created_at, reverse=True)
    return render_template("orders/list.html", orders=orders)


@app.route("/objednavky/<int:order_id>")
@login_required
def order_detail(order_id):
    order = store.orders.get(order_id)
    if not order:
        abort(404)
    if current_user.role == "customer" and order.customer_id != current_user.id:
        abort(403)
    items    = store.order_items.by_order(order_id)
    products = {p.id: p for p in store.products.all()}
    payment  = store.payments.by_order(order_id)
    delivery = store.deliveries.by_order(order_id)
    customer = store.users.get(order.customer_id)
    return render_template("orders/detail.html",
                           order=order, items=items, products=products,
                           payment=payment, delivery=delivery, customer=customer)


@app.route("/objednavky/<int:order_id>/zrusit-dorucenie", methods=["POST"])
@login_required
def order_cancel_failed_delivery(order_id):
    """UC06 exception (customer side): cancel order after failed delivery + refund."""
    order = store.orders.get(order_id)
    if not order or order.customer_id != current_user.id:
        abort(403)
    delivery = store.deliveries.by_order(order_id)
    if delivery and delivery.status == "failed":
        delivery.status = "cancelled"
        store.deliveries.save(delivery)
    order.status = "cancelled"
    order.notes  = (order.notes or "") + " | ZRUSENE ZAKAZNIKOM po neuspesnom doruceni – platba bude vratena."
    order.updated_at = datetime.utcnow().isoformat()
    store.orders.save(order)
    # Refund: mark payment as refunded
    pay = store.payments.by_order(order_id)
    if pay and pay.status == "completed":
        pay.status = "refunded"
        store.payments.save(pay)
    flash("Objednavka bola zrusena a platba bude vratena na vas ucet.", "success")
    return redirect(url_for("orders_list"))


@app.route("/objednavky/<int:order_id>/zrusit", methods=["POST"])
@login_required
def order_cancel(order_id):
    order = store.orders.get(order_id)
    if not order:
        abort(404)
    if current_user.role == "customer" and order.customer_id != current_user.id:
        abort(403)
    if order.status in ("paid", "processing", "shipped", "delivered"):
        flash("Zaplatenou alebo odoslanou objednavku nie je mozne zrusit.", "warning")
        return redirect(url_for("order_detail", order_id=order_id))
    order.status = "cancelled"
    order.updated_at = datetime.utcnow().isoformat()
    store.orders.save(order)
    flash("Objednavka bola zrusena.", "info")
    return redirect(url_for("orders_list"))


# ---------------------------------------------------------------------------
# DESIGN REQUEST  – UC03 (customer side)
# ---------------------------------------------------------------------------
@app.route("/dizajn/nova", methods=["GET", "POST"])
@login_required
def design_new():
    if request.method == "POST":
        store.design_requests.save(DesignRequest(
            id=store.design_requests.next_id(),
            customer_id=current_user.id,
            room_type=request.form.get("room_type", ""),
            style_preferences=request.form.get("style_preferences", ""),
            room_dimensions=request.form.get("room_dimensions", ""),
            customer_notes=request.form.get("customer_notes", ""),
            customer_price_limit=request.form.get("price_limit", type=float),
        ))
        flash("Poziadavka na dizajn bola odoslana dizajnerovi.", "success")
        return redirect(url_for("design_my"))
    return render_template("designer/new_request.html")


@app.route("/dizajn/moje")
@login_required
def design_my():
    reqs = sorted(store.design_requests.by_customer(current_user.id),
                  key=lambda d: d.created_at, reverse=True)
    return render_template("designer/my_requests.html", requests=reqs)


@app.route("/dizajn/<int:dr_id>/schvalit", methods=["POST"])
@login_required
def design_approve(dr_id):
    dr = store.design_requests.get(dr_id)
    if not dr or dr.customer_id != current_user.id:
        abort(403)
    dr.status      = "approved"
    dr.final_price = dr.estimated_price
    dr.updated_at  = datetime.utcnow().isoformat()
    store.design_requests.save(dr)
    flash("Dizajn bol schvaleny. Podklady boli odoslane do vyroby.", "success")
    return redirect(url_for("design_my"))


@app.route("/dizajn/<int:dr_id>/uprava", methods=["POST"])
@login_required
def design_revision(dr_id):
    """UC03 alt: customer requests revision."""
    dr = store.design_requests.get(dr_id)
    if not dr or dr.customer_id != current_user.id:
        abort(403)
    dr.status         = "revision_requested"
    dr.revision_count += 1
    dr.updated_at     = datetime.utcnow().isoformat()
    store.design_requests.save(dr)
    flash(f"Poziadavka na upravu c. {dr.revision_count} bola odoslana. Bude vam uctovany dodatocny poplatok.", "info")
    return redirect(url_for("design_my"))


@app.route("/dizajn/<int:dr_id>/zrusit", methods=["POST"])
@login_required
def design_cancel(dr_id):
    dr = store.design_requests.get(dr_id)
    if not dr or dr.customer_id != current_user.id:
        abort(403)
    dr.status    = "cancelled"
    dr.updated_at = datetime.utcnow().isoformat()
    store.design_requests.save(dr)
    flash("Poziadavka na dizajn bola zrusena.", "info")
    return redirect(url_for("design_my"))


# ---------------------------------------------------------------------------
# DESIGNER PORTAL  – UC03
# ---------------------------------------------------------------------------
@app.route("/portal/dizajner")
@login_required
@role_required("designer")
def designer_dashboard():
    pending     = store.design_requests.pending()
    in_progress = store.design_requests.by_designer(current_user.id)
    # All requests handled by this designer (any status except pending/unassigned)
    my_all = store.design_requests.filter_fn(
        lambda d: d.designer_id == current_user.id and d.status not in ("in_progress",)
    )
    customers = {u.id: u for u in store.users.all()}
    return render_template("designer/dashboard.html",
                           pending=pending, in_progress=in_progress,
                           my_all=my_all, customers=customers)


@app.route("/portal/dizajner/prevziat/<int:dr_id>", methods=["POST"])
@login_required
@role_required("designer")
def designer_take(dr_id):
    dr = store.design_requests.get(dr_id)
    if not dr:
        abort(404)
    dr.designer_id = current_user.id
    dr.status      = "in_progress"
    dr.updated_at  = datetime.utcnow().isoformat()
    store.design_requests.save(dr)
    flash("Poziadavka prevzata.", "success")
    return redirect(url_for("designer_work", dr_id=dr_id))


@app.route("/portal/dizajner/pracat/<int:dr_id>", methods=["GET", "POST"])
@login_required
@role_required("designer")
def designer_work(dr_id):
    """UC03 – designer works on design request."""
    dr = store.design_requests.get(dr_id)
    if not dr:
        abort(404)
    customer = store.users.get(dr.customer_id)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "submit_design":
            dr.material_suggestion = request.form.get("material_suggestion", "")
            dr.estimated_price     = request.form.get("estimated_price", type=float)
            dr.designer_notes      = request.form.get("designer_notes", "")
            dr.status              = "sent_to_customer"
            dr.updated_at          = datetime.utcnow().isoformat()
            store.design_requests.save(dr)
            # UC03 exception: price > 140% of limit
            if dr.price_over_limit():
                flash(
                    f"UPOZORNENIE: Odhadovana cena ({dr.estimated_price:.2f} EUR) prekracuje "
                    f"zakaznikov limit ({dr.customer_price_limit:.2f} EUR) o viac ako 40%. "
                    "Kontaktujte zakaznika s ponukou lacnejsich materialov.",
                    "warning",
                )
            else:
                flash("Navrh bol odoslany zakaznikovi na schvalenie.", "success")

        elif action == "cancel_request":
            # UC03 exception: storno
            dr.status    = "cancelled"
            dr.updated_at = datetime.utcnow().isoformat()
            store.design_requests.save(dr)
            flash("Poziadavka bola stornovana.", "info")
            return redirect(url_for("designer_dashboard"))

        return redirect(url_for("designer_work", dr_id=dr_id))

    return render_template("designer/work.html", dr=dr, customer=customer)


# ---------------------------------------------------------------------------
# WAREHOUSE PORTAL  – UC04
# ---------------------------------------------------------------------------
@app.route("/portal/sklad")
@login_required
@role_required("warehouse", "admin")
def warehouse_dashboard():
    open_orders      = store.supplier_orders.open_orders()
    completed_orders = store.supplier_orders.completed_orders()
    suppliers        = {s.id: s for s in store.suppliers.all()}
    return render_template("warehouse/dashboard.html",
                           orders=open_orders,
                           completed_orders=completed_orders,
                           suppliers=suppliers)


@app.route("/portal/sklad/<int:so_id>", methods=["GET", "POST"])
@login_required
@role_required("warehouse", "admin")
def warehouse_receive(so_id):
    """UC04 – receive material from supplier."""
    so = store.supplier_orders.get(so_id)
    if not so:
        abort(404)
    supplier = store.suppliers.get(so.supplier_id)
    items    = store.supplier_order_items.by_order(so_id)

    if request.method == "POST":
        all_received = True
        any_received = False

        for item in items:
            action       = request.form.get(f"item_{item.id}_action", "receive")
            recv_qty     = request.form.get(f"item_{item.id}_received_qty", type=int, default=item.ordered_qty)
            location     = request.form.get(f"item_{item.id}_location", "").strip()
            claim_reason = request.form.get(f"item_{item.id}_claim_reason", "").strip()

            if action == "claim":
                # UC04 exception: damaged goods
                item.status       = "claimed"
                item.claim_reason = claim_reason or "Material znehodnoteny alebo nezodpoveda kvalite."
                store.claims.save(ClaimRecord(
                    id=store.claims.next_id(),
                    description=item.claim_reason,
                    supplier_order_item_id=item.id,
                ))
                all_received = False

            elif action == "partial":
                # UC04 alt: partial delivery
                item.received_qty       = recv_qty
                item.warehouse_location = location
                item.status = "partial" if recv_qty < item.ordered_qty else "received"
                if recv_qty < item.ordered_qty:
                    all_received = False
                any_received = True
                if item.product_id and recv_qty:
                    prod = store.products.get(item.product_id)
                    if prod:
                        prod.stock += recv_qty
                        store.products.save(prod)

            else:
                # full receive
                item.received_qty       = item.ordered_qty
                item.warehouse_location = location
                item.status             = "received"
                any_received            = True
                if item.product_id:
                    prod = store.products.get(item.product_id)
                    if prod:
                        prod.stock += item.received_qty
                        store.products.save(prod)

            store.supplier_order_items.save(item)

        if all_received and any_received:
            so.status = "delivered"
            flash("Prijem tovaru dokonceny. Zasoby boli aktualizovane.", "success")
        elif any_received:
            so.status = "partial"
            flash("Ciastocny prijem zaznamenaný. Objednavka zostava otvorena.", "info")
        else:
            flash("Reklamacny protokol bol vygenerovany. Zasoby neboli navysene.", "warning")

        store.supplier_orders.save(so)
        return redirect(url_for("warehouse_dashboard"))

    return render_template("warehouse/receive.html", so=so, supplier=supplier, items=items)


@app.route("/portal/sklad/inventar")
@login_required
@role_required("warehouse", "admin")
def warehouse_inventory():
    """Warehouse inventory – current stock of all products."""
    categories = store.categories.all()
    cat_map    = {c.id: c for c in categories}
    products   = store.products.all()
    return render_template("warehouse/inventory.html", products=products, cat_map=cat_map)


# ---------------------------------------------------------------------------
# ADMIN PORTAL  – UC05
# ---------------------------------------------------------------------------
@app.route("/portal/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    return render_template("admin/dashboard.html",
                           product_count=len(store.products.all()),
                           order_count=len(store.orders.non_draft()),
                           pending_designs=len(store.design_requests.pending()),
                           user_count=len(store.users.all()))


@app.route("/portal/admin/katalog")
@login_required
@role_required("admin")
def admin_catalog():
    """UC05 – catalogue management."""
    categories = store.categories.all()
    cat_filter = request.args.get("cat", type=int)
    products   = [p for p in store.products.all() if not cat_filter or p.category_id == cat_filter]
    cat_map    = {c.id: c for c in categories}
    return render_template("admin/catalog.html",
                           products=products, categories=categories,
                           cat_map=cat_map, cat_filter=cat_filter)


@app.route("/portal/admin/katalog/novy", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_product_new():
    """UC05 – add new product."""
    categories = store.categories.all()
    if request.method == "POST":
        try:
            p = _build_product(store.products.next_id())
            store.products.save(p)
            flash(f"Produkt '{p.name}' bol pridany do katalogu.", "success")
            return redirect(url_for("admin_catalog"))
        except Exception as exc:
            # UC05 exception: save error
            flash(f"Chyba pri ukladani: {exc}. Skuste znova.", "danger")
    return render_template("admin/product_form.html", product=None, categories=categories)


@app.route("/portal/admin/katalog/upravit/<int:product_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_product_edit(product_id):
    """UC05 alt – edit existing product."""
    product    = store.products.get(product_id)
    categories = store.categories.all()
    if not product:
        abort(404)
    if request.method == "POST":
        updated = _build_product(product_id)
        store.products.save(updated)
        flash(f"Produkt '{updated.name}' bol aktualizovany.", "success")
        return redirect(url_for("admin_catalog"))
    return render_template("admin/product_form.html", product=product, categories=categories)


def _build_product(pid: int):
    from models import Product
    return Product(
        id=pid,
        category_id=int(request.form["category_id"]),
        name=request.form["name"].strip(),
        description=request.form.get("description", "").strip(),
        price=float(request.form["price"]),
        material=request.form.get("material", "").strip(),
        dimensions=request.form.get("dimensions", "").strip(),
        stock=int(request.form.get("stock", 0)),
        is_available=("is_available" in request.form),
        allows_custom=("allows_custom" in request.form),
        custom_surcharge_pct=float(request.form.get("custom_surcharge_pct", 20)),
        updated_at=datetime.utcnow().isoformat(),
    )


@app.route("/portal/admin/katalog/zmazat/<int:product_id>", methods=["POST"])
@login_required
@role_required("admin")
def admin_product_delete(product_id):
    product = store.products.get(product_id)
    if product:
        product.is_available = False
        store.products.save(product)
        flash(f"Produkt '{product.name}' bol deaktivovany.", "info")
    return redirect(url_for("admin_catalog"))


@app.route("/portal/admin/objednavky")
@login_required
@role_required("admin")
def admin_orders():
    orders    = sorted(store.orders.non_draft(), key=lambda o: o.created_at, reverse=True)
    customers = {u.id: u for u in store.users.all()}
    return render_template("admin/orders.html", orders=orders, customers=customers)


@app.route("/portal/admin/dizajny")
@login_required
@role_required("admin")
def admin_designs():
    designs   = sorted(store.design_requests.all(), key=lambda d: d.created_at, reverse=True)
    customers = {u.id: u for u in store.users.all()}
    return render_template("admin/designs.html", designs=designs, customers=customers)


# ---------------------------------------------------------------------------
# DELIVERY / FIELD WORKER PORTAL  – UC06
# ---------------------------------------------------------------------------
@app.route("/portal/terenny")
@login_required
@role_required("field_worker", "admin")
def delivery_dashboard():
    if current_user.role == "field_worker":
        deliveries  = store.deliveries.by_worker(current_user.id)
        completed   = store.deliveries.completed_by_worker(current_user.id)
        unassigned  = store.deliveries.unassigned()
    else:
        deliveries  = store.deliveries.active()
        completed   = store.deliveries.completed()
        unassigned  = []
    orders = {o.id: o for o in store.orders.all()}
    return render_template("delivery/dashboard.html",
                           deliveries=deliveries, unassigned=unassigned,
                           completed=completed, orders=orders)


@app.route("/portal/terenny/prevziat/<int:delivery_id>", methods=["POST"])
@login_required
@role_required("field_worker")
def delivery_take(delivery_id):
    delivery = store.deliveries.get(delivery_id)
    if not delivery:
        abort(404)
    delivery.field_worker_id = current_user.id
    store.deliveries.save(delivery)
    flash("Dorucenie bolo prevzate.", "success")
    return redirect(url_for("delivery_dashboard"))


@app.route("/portal/terenny/dorucenie/<int:delivery_id>", methods=["GET", "POST"])
@login_required
@role_required("field_worker", "admin")
def delivery_detail(delivery_id):
    """UC06 – manage a delivery."""
    delivery = store.deliveries.get(delivery_id)
    if not delivery:
        abort(404)
    order    = store.orders.get(delivery.order_id)
    customer = store.users.get(order.customer_id) if order else None
    items    = store.order_items.by_order(order.id) if order else []
    products = {p.id: p for p in store.products.all()}

    if request.method == "POST":
        action = request.form.get("action")

        if action == "confirm_delivery":
            # UC06 main: successful delivery
            delivery.status           = "delivered"
            delivery.completion_notes = request.form.get("notes", "")
            store.deliveries.save(delivery)
            if order:
                order.status     = "delivered"
                order.updated_at = datetime.utcnow().isoformat()
                store.orders.save(order)
            flash("Dorucenie potvrdene. Objednavka je uzavreta.", "success")
            return redirect(url_for("delivery_dashboard"))

        elif action == "reschedule":
            # UC06 alt: reschedule
            new_date = request.form.get("new_date", "")
            if new_date:
                delivery.scheduled_date = new_date
                delivery.status         = "rescheduled"
                store.deliveries.save(delivery)
                flash(f"Dorucenie bolo prelozene na {new_date}.", "info")
            else:
                flash("Zadajte novy datum.", "danger")
            return redirect(url_for("delivery_detail", delivery_id=delivery_id))

        # ── UC07 assembly actions ──────────────────────────────────────────
        elif action == "start_assembly":
            delivery.assembly_status = "in_progress"
            store.deliveries.save(delivery)
            flash("Montaz zaciata.", "info")
            return redirect(url_for("delivery_detail", delivery_id=delivery_id))

        elif action == "confirm_assembly":
            # UC07 main flow: assembly done, customer confirmed
            delivery.assembly_status    = "completed"
            delivery.status             = "delivered"
            delivery.completion_notes   = request.form.get("notes", "")
            store.deliveries.save(delivery)
            if order:
                order.status     = "delivered"
                order.updated_at = datetime.utcnow().isoformat()
                store.orders.save(order)
            flash("Montaz dokoncena a potvrdena zakaznikom. Objednavka je uzavreta. E-mail s potvrdenim bol odoslany.", "success")
            return redirect(url_for("delivery_dashboard"))

        elif action == "add_clearance":
            # UC08 clearance of old furniture requested
            fee = request.form.get("clearance_fee", type=float, default=150.0)
            delivery.clearance_requested = True
            delivery.clearance_fee       = fee
            store.deliveries.save(delivery)
            if order:
                order.total_price = round(order.total_price + fee, 2)
                order.notes = (order.notes or "") + f" | Vypratanie stareho nabytku: +{fee:.2f} EUR"
                order.updated_at = datetime.utcnow().isoformat()
                store.orders.save(order)
            flash(f"Sluzba vypratania pridana (+{fee:.2f} EUR). Cena na faktúre bola aktualizovana.", "success")
            return redirect(url_for("delivery_detail", delivery_id=delivery_id))

        elif action == "decline_clearance":
            # UC0/alt exception: customer refuses clearance → record failed assembly
            delivery.completion_notes = "Zakaznik odmietol vypratanie – montaz sa neuskutocnila."
            delivery.assembly_status  = "pending"
            store.deliveries.save(delivery)
            flash("Zakaznik odmietol vypratanie. Montaz nebola vykonana – zaznamenane v systeme.", "warning")
            return redirect(url_for("delivery_detail", delivery_id=delivery_id))

        elif action == "damage_claim":
            # UC07 exception: damaged/missing component
            description = request.form.get("damage_description", "Poskodenie alebo chybajuci komponent.")
            store.claims.save(ClaimRecord(
                id=store.claims.next_id(),
                description=description,
                delivery_id=delivery_id,
            ))
            delivery.assembly_status  = "damaged"
            delivery.completion_notes = description
            store.deliveries.save(delivery)
            flash("Reklamacny zaznam bol vytvoreny. Zarezervujte nahradny termin so zakaznikom.", "warning")
            return redirect(url_for("delivery_detail", delivery_id=delivery_id))

        elif action == "cannot_deliver":
            # UC06 exception: worker cannot arrive → mark delivery as failed
            # Customer will see an alert on their order and can cancel with refund
            delivery.status = "failed"
            delivery.completion_notes = request.form.get("fail_reason", "Pracovnik sa nedokaze dostavit.")
            store.deliveries.save(delivery)
            flash("Dorucenie oznacene ako neuspesne. Zakaznik bude notifikovany.", "warning")
            return redirect(url_for("delivery_dashboard"))

    return render_template("delivery/detail.html",
                           delivery=delivery, order=order,
                           customer=customer, items=items, products=products)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
@app.errorhandler(403)
def err_403(e):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def err_404(e):
    return render_template("errors/404.html"), 404


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
 
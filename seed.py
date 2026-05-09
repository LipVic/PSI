"""
Seed demo data into JSON files.
Run once – skips if users.json already has data.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from storage import DataStore
from models import (
    User, Category, Product, Order, OrderItem,
    Supplier, SupplierOrder, SupplierOrderItem,
    Delivery,
)


def seed(store: DataStore) -> None:
    if store.users.all():
        return  # already seeded

    # ── Users ──────────────────────────────────────────────────────────────
    roles = [
        ("Jana Nováková",     "customer@demo.com",  "customer"),
        ("Tomáš Krásny",      "designer@demo.com",  "designer"),
        ("Admin FitForYou",   "admin@demo.com",     "admin"),
        ("Miroslav Skladník", "warehouse@demo.com", "warehouse"),
        ("Peter Terénny",     "worker@demo.com",    "field_worker"),
    ]
    uid = 1
    user_map: dict[str, User] = {}
    for name, email, role in roles:
        u = User(id=uid, name=name, email=email, password_hash="", role=role)
        u.set_password("demo1234")
        store.users.save(u)
        user_map[role] = u
        uid += 1

    # ── Categories ─────────────────────────────────────────────────────────
    cat_data = [
        ("Stoly",    "Jedálenské, písacie a konferenčné stoly",    "bi-table"),
        ("Skrine",   "Šatníkové a knižničné skrine",               "bi-archive"),
        ("Postele",  "Manželské, jednolôžkové a detské postele",   "bi-moon"),
        ("Stoličky", "Jedálenské, kancelárske a barové stoličky",  "bi-person-workspace"),
        ("Pohovky",  "Rohové sedačky a dvojsedačky",               "bi-house-heart"),
        ("Komody",   "Nočné stolíky, komody a skrinky",            "bi-layers"),
    ]
    cid = 1
    cats: list[Category] = []
    for name, desc, icon in cat_data:
        c = Category(id=cid, name=name, description=desc, icon=icon)
        store.categories.save(c)
        cats.append(c)
        cid += 1

    stoly, skrine, postele, stolicky, pohovky, komody = cats

    # ── Products ───────────────────────────────────────────────────────────
    product_data = [
        (stoly.id,   "Dubový jedálenský stôl Oslo",    649.0,  "Masívny dub",         "160×90×75 cm",  5,  True,  True,  20.0,
         "Klasický jedálenský stôl z masívneho dubu. Ideálny pre 6 osôb."),
        (stoly.id,   "Písací stôl Birch",              299.0,  "Brezová dyha",         "120×60×75 cm",  8,  True,  True,  20.0,
         "Moderný písací stôl s káblovým managementom."),
        (stoly.id,   "Konferenčný stolík Miso",        189.0,  "MDF + kov",            "90×60×45 cm",  12,  True, False, 0.0,
         "Nízky konferenčný stolík v škandinávskom štýle."),
        (skrine.id,  "Šatníková skriňa Palazzo",       899.0,  "Masívna borovica",     "200×60×220 cm", 3,  True,  True,  25.0,
         "Priestranná trojdverová šatníková skriňa."),
        (skrine.id,  "Knižnica Open Shelf",            349.0,  "Bambus",               "80×30×180 cm",  6,  True, False, 0.0,
         "Otvorená knižnica z bambusu."),
        (postele.id, "Manželská posteľ Nordic",        799.0,  "Masívny buk",          "180×200 cm",    4,  True,  True,  20.0,
         "Posteľ s dreveným čelom a úložným priestorom pod matracom."),
        (postele.id, "Jednolôžková posteľ Slim",       399.0,  "MDF biela",            "90×200 cm",     7,  True, False, 0.0,
         "Minimalistická jednolôžková posteľ."),
        (stolicky.id,"Jedálenská stolička Bella",      129.0,  "Masívny buk + látka",  "45×50×90 cm",  20,  True,  True,  15.0,
         "Čalúnená stolička v rôznych farebných prevedeniach."),
        (stolicky.id,"Kancelárska stolička ErgoPlus",  449.0,  "Kov + mesh",           "60×65×120 cm", 10,  True, False, 0.0,
         "Ergonomická stolička s bedrovou oporou."),
        (pohovky.id, "Rohová sedačka Comfort L",      1299.0,  "Látka + pena HR",      "280×180×85 cm", 2,  True,  True,  30.0,
         "Ľavostranná rohová sedačka s rozkladacou funkciou."),
        (pohovky.id, "Dvojsedačka Loft",               699.0,  "Koža syntetická",      "160×85×80 cm",  5,  True, False, 0.0,
         "Moderná dvojsedačka v industriálnom štýle."),
        (komody.id,  "Nočný stolík Duo",               149.0,  "MDF + drevené nôžky",  "45×35×55 cm",  15,  True,  True,  15.0,
         "Nočný stolík s dvoma zásuvkami."),
        (komody.id,  "Komoda Havana 4+4",              549.0,  "Masívny orech",        "120×45×85 cm",  3,  True,  True,  20.0,
         "Komoda so štyrmi zásuvkami po oboch stranách."),
        # one unavailable product to demo UC01a exception
        (stoly.id,   "Retro stôl Vintage (vypredaný)", 450.0,  "Dubová dýha",         "140×80×75 cm",  0, False, False,  0.0,
         "Limitovaná edícia – momentálne nedostupné."),
    ]

    pid = 1
    prods: list[Product] = []
    for row in product_data:
        cat_id, name, price, material, dims, stock, avail, custom, surcharge, desc = row
        p = Product(
            id=pid, category_id=cat_id, name=name, price=price,
            material=material, dimensions=dims, stock=stock,
            is_available=avail, allows_custom=custom,
            custom_surcharge_pct=surcharge, description=desc,
        )
        store.products.save(p)
        prods.append(p)
        pid += 1

    # ── Suppliers ──────────────────────────────────────────────────────────
    sup1 = Supplier(id=1, name="WoodMaster s.r.o.",
                    contact_email="info@woodmaster.sk", phone="+421 2 555 0100")
    sup2 = Supplier(id=2, name="MetalForm a.s.",
                    contact_email="orders@metalform.sk", phone="+421 2 555 0200")
    store.suppliers.save(sup1)
    store.suppliers.save(sup2)

    # ── Supplier orders (UC04 demo) ─────────────────────────────────────────
    so1 = SupplierOrder(
        id=1, supplier_id=sup1.id, status="open",
        expected_delivery=(datetime.utcnow() + timedelta(days=3)).isoformat(),
        notes="Pravidelná mesačná objednávka dubového masívu",
    )
    store.supplier_orders.save(so1)
    store.supplier_order_items.save(SupplierOrderItem(
        id=1, supplier_order_id=1, product_id=prods[0].id,
        material_name="Dubový masív – dosky", ordered_qty=20, unit_price=85.0,
    ))
    store.supplier_order_items.save(SupplierOrderItem(
        id=2, supplier_order_id=1, product_id=prods[3].id,
        material_name="Borovicový masív – fošne", ordered_qty=30, unit_price=45.0,
    ))

    so2 = SupplierOrder(
        id=2, supplier_id=sup2.id, status="open",
        expected_delivery=(datetime.utcnow() + timedelta(days=5)).isoformat(),
        notes="Kovové komponenty pre stolové nôžky",
    )
    store.supplier_orders.save(so2)
    store.supplier_order_items.save(SupplierOrderItem(
        id=3, supplier_order_id=2, product_id=prods[8].id,
        material_name="Kovové nohy – sada 4 ks", ordered_qty=50, unit_price=12.0,
    ))

    # ── Demo paid order with delivery (UC06 demo) ──────────────────────────
    demo_order = Order(
        id=1, customer_id=user_map["customer"].id,
        status="paid",
        delivery_method="delivery",
        delivery_address="Mlynská 5, Bratislava",
        delivery_date=(datetime.utcnow() + timedelta(days=7)).isoformat(),
        notes="Prosím zavolajte pred príchodom",
        total_price=649.0,
    )
    store.orders.save(demo_order)
    store.order_items.save(OrderItem(
        id=1, order_id=1, product_id=prods[0].id,
        quantity=1, unit_price=649.0, is_custom=False,
    ))
    store.deliveries.save(Delivery(
        id=1, order_id=1, field_worker_id=user_map["field_worker"].id,
        status="scheduled",
        scheduled_date=(datetime.utcnow() + timedelta(days=7)).isoformat(),
        address="Mlynská 5, Bratislava",
        requires_assembly=False,
    ))

    print("Demo data seeded successfully.")


if __name__ == "__main__":
    store = DataStore()
    seed(store)

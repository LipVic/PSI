"""
FitForYou – Domain Models (pure Python OOP, no ORM).
Each class maps to a JSON file in the data/ directory.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash


def _now() -> str:
    return datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------
class DictMixin:
    """Mixin that adds to_dict / from_dict support."""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
@dataclass
class User(DictMixin):
    """
    Represents any system user.
    Roles: customer | designer | admin | warehouse | field_worker
    """
    id: int
    name: str
    email: str
    password_hash: str
    role: str = "customer"
    phone: str = ""
    address: str = ""
    created_at: str = field(default_factory=_now)

    # --- Flask-Login interface ---
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    # --- Password helpers ---
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def role_label(self) -> str:
        labels = {
            "customer": "Zákazník",
            "designer": "Dizajnér",
            "admin": "Administrátor",
            "warehouse": "Skladový manažér",
            "field_worker": "Terénny pracovník",
        }
        return labels.get(self.role, self.role)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
@dataclass
class Category(DictMixin):
    """Product category (e.g. Stoly, Skrine, Postele)."""
    id: int
    name: str
    description: str = ""
    icon: str = "bi-box"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
@dataclass
class Product(DictMixin):
    """
    A furniture item in the catalogue.
    Supports custom dimensions/colour via allows_custom flag.
    """
    id: int
    category_id: int
    name: str
    price: float
    description: str = ""
    material: str = ""
    dimensions: str = ""
    stock: int = 0
    is_available: bool = True
    allows_custom: bool = True
    custom_surcharge_pct: float = 20.0   # % price increase for custom order
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def custom_price(self) -> float:
        """UC01b – price surcharge for custom dimensions."""
        return round(self.price * (1 + self.custom_surcharge_pct / 100), 2)


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------
@dataclass
class OrderItem(DictMixin):
    """
    One line inside an Order.
    is_custom=True → UC01b (custom dimensions/colour).
    """
    id: int
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    is_custom: bool = False
    custom_width: Optional[float] = None
    custom_height: Optional[float] = None
    custom_depth: Optional[float] = None
    custom_color: str = ""
    special_requirements: str = ""

    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)

    def dimensions_str(self) -> str:
        if self.is_custom and self.custom_width:
            return f"{self.custom_width}×{self.custom_depth}×{self.custom_height} cm"
        return ""


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------
@dataclass
class Order(DictMixin):
    """
    Customer order.
    Lifecycle: draft → pending_payment → (awaiting_payment|paid)
               → processing → shipped → delivered | cancelled
    """
    id: int
    customer_id: int
    status: str = "draft"
    delivery_method: str = "pickup"     # pickup | delivery
    delivery_address: str = ""
    delivery_date: str = ""
    notes: str = ""
    total_price: float = 0.0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    _STATUS_LABELS = {
        "draft": "Rozpisaná",
        "pending_payment": "Čakajúca na platbu",
        "awaiting_payment": "Čaká sa na platbu",
        "paid": "Zaplatená",
        "processing": "Spracováva sa",
        "shipped": "Odoslaná",
        "delivered": "Doručená",
        "cancelled": "Zrušená",
    }

    def status_label(self) -> str:
        return self._STATUS_LABELS.get(self.status, self.status)


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------
@dataclass
class Payment(DictMixin):
    """
    Payment record linked to an Order.
    UC02 – card or bank_transfer.
    """
    id: int
    order_id: int
    amount: float
    method: str                          # card | bank_transfer
    status: str = "pending"              # pending | completed | failed
    transaction_id: str = ""
    bank_reference: str = ""
    created_at: str = field(default_factory=_now)
    completed_at: str = ""

    def method_label(self) -> str:
        return {"card": "Platobna karta", "bank_transfer": "Bankovy prevod"}.get(self.method, self.method)

    def status_label(self) -> str:
        return {"pending": "Caka", "completed": "Zaplatena", "failed": "Zamietnutá", "refunded": "Vratena"}.get(self.status, self.status)


# ---------------------------------------------------------------------------
# DesignRequest
# ---------------------------------------------------------------------------
@dataclass
class DesignRequest(DictMixin):
    """
    UC03 – Interior design request created by a customer.
    A designer picks it up, creates a design, and sends it back for approval.
    Statuses: pending → in_progress → sent_to_customer
              → revision_requested → approved | cancelled | rejected
    """
    id: int
    customer_id: int
    status: str = "pending"
    designer_id: Optional[int] = None
    order_item_id: Optional[int] = None
    room_type: str = ""
    style_preferences: str = ""
    room_dimensions: str = ""
    customer_notes: str = ""
    designer_notes: str = ""
    material_suggestion: str = ""
    estimated_price: Optional[float] = None
    customer_price_limit: Optional[float] = None
    final_price: Optional[float] = None
    revision_count: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    _STATUS_LABELS = {
        "pending": "Čakajúca",
        "in_progress": "Prebieha",
        "sent_to_customer": "Odoslaná zákazníkovi",
        "revision_requested": "Požiadavka na úpravu",
        "approved": "Schválená",
        "rejected": "Zamietnutá",
        "cancelled": "Zrušená",
    }

    def status_label(self) -> str:
        return self._STATUS_LABELS.get(self.status, self.status)

    def price_over_limit(self) -> bool:
        """UC03 exception: price exceeds customer limit by more than 40 %."""
        if self.customer_price_limit and self.estimated_price:
            return self.estimated_price > self.customer_price_limit * 1.4
        return False


# ---------------------------------------------------------------------------
# Supplier + SupplierOrder + SupplierOrderItem
# ---------------------------------------------------------------------------
@dataclass
class Supplier(DictMixin):
    id: int
    name: str
    contact_email: str = ""
    phone: str = ""


@dataclass
class SupplierOrder(DictMixin):
    """
    UC04 – An open purchase order from a supplier.
    Statuses: open | partial | delivered | closed
    """
    id: int
    supplier_id: int
    status: str = "open"
    expected_delivery: str = ""
    notes: str = ""
    created_at: str = field(default_factory=_now)

    _STATUS_LABELS = {
        "open": "Otvorená",
        "partial": "Čiastočne doručená",
        "delivered": "Doručená",
        "closed": "Uzavretá",
    }

    def status_label(self) -> str:
        return self._STATUS_LABELS.get(self.status, self.status)


@dataclass
class SupplierOrderItem(DictMixin):
    """
    One material line inside a SupplierOrder.
    UC04 – manager confirms receipt, sets actual quantity & warehouse location.
    """
    id: int
    supplier_order_id: int
    material_name: str
    ordered_qty: int
    unit_price: float
    product_id: Optional[int] = None
    received_qty: int = 0
    warehouse_location: str = ""
    status: str = "pending"             # pending | received | claimed | partial
    claim_reason: str = ""

    _STATUS_LABELS = {
        "pending": "Cakajuce",
        "received": "Prijate",
        "claimed": "Reklamovane",
        "partial": "Ciastocne",
    }

    def item_name(self) -> str:
        if self.material_name:
            return self.material_name
        if self.product_id:
            return f"Produkt #{self.product_id}"
        return "Neznamy material"

    def status_label(self) -> str:
        return self._STATUS_LABELS.get(self.status, self.status)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
@dataclass
class Delivery(DictMixin):
    """
    UC06 – Delivery task.
    UC07 – Assembly extension (requires_assembly=True).
    Statuses: scheduled | rescheduled | delivered | failed | cancelled
    Assembly statuses: "" | pending | in_progress | completed | damaged
    """
    id: int
    order_id: int
    status: str = "scheduled"
    field_worker_id: Optional[int] = None
    scheduled_date: str = ""
    address: str = ""
    notes: str = ""
    requires_assembly: bool = False
    completion_notes: str = ""
    # UC07 assembly fields
    assembly_status: str = ""        # "" | pending | in_progress | completed | damaged
    clearance_requested: bool = False
    clearance_fee: float = 0.0
    created_at: str = field(default_factory=_now)

    _STATUS_LABELS = {
        "scheduled": "Naplanovana",
        "rescheduled": "Prelozena",
        "delivered": "Dorucena",
        "failed": "Pracovnik sa nedostavi",
        "cancelled": "Zrusena",
    }

    _ASSEMBLY_LABELS = {
        "":           "—",
        "pending":    "Caka na montaz",
        "in_progress":"Prebieha montaz",
        "completed":  "Zmontovane",
        "damaged":    "Reklamacia – poskodeny tovar",
    }

    def status_label(self) -> str:
        return self._STATUS_LABELS.get(self.status, self.status)

    def assembly_label(self) -> str:
        return self._ASSEMBLY_LABELS.get(self.assembly_status, self.assembly_status)


# ---------------------------------------------------------------------------
# ClaimRecord
# ---------------------------------------------------------------------------
@dataclass
class ClaimRecord(DictMixin):
    """Complaint record – created during UC04 (damaged goods) or UC07."""
    id: int
    description: str
    delivery_id: Optional[int] = None
    supplier_order_item_id: Optional[int] = None
    status: str = "open"
    created_at: str = field(default_factory=_now)

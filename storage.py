"""
FitForYou – JSON File Storage Layer.

Each entity type is stored in a separate JSON file under data/.
The Repository class provides generic CRUD operations.
Specialised repositories add domain-specific finders.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable, Generic, List, Optional, Type, TypeVar

from models import (
    User, Category, Product, Order, OrderItem,
    Payment, DesignRequest,
    Supplier, SupplierOrder, SupplierOrderItem,
    Delivery, ClaimRecord,
)

T = TypeVar("T")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Generic repository
# ---------------------------------------------------------------------------
class Repository(Generic[T]):
    """
    Thread-safe JSON file-backed repository.
    Each instance manages one entity type stored in one .json file.
    """

    _lock = threading.Lock()

    def __init__(self, filename: str, model_class: Type[T]) -> None:
        _ensure_data_dir()
        self._path = os.path.join(DATA_DIR, filename)
        self._cls = model_class
        if not os.path.exists(self._path):
            self._write_raw([])

    # --- low-level I/O ---

    def _read_raw(self) -> list[dict]:
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_raw(self, records: list[dict]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    # --- public interface ---

    def all(self) -> List[T]:
        return [self._cls.from_dict(r) for r in self._read_raw()]

    def get(self, entity_id: int) -> Optional[T]:
        for r in self._read_raw():
            if r.get("id") == entity_id:
                return self._cls.from_dict(r)
        return None

    def filter(self, **kwargs) -> List[T]:
        results = []
        for r in self._read_raw():
            if all(r.get(k) == v for k, v in kwargs.items()):
                results.append(self._cls.from_dict(r))
        return results

    def filter_fn(self, predicate: Callable[[T], bool]) -> List[T]:
        return [obj for obj in self.all() if predicate(obj)]

    def next_id(self) -> int:
        records = self._read_raw()
        if not records:
            return 1
        return max(r["id"] for r in records) + 1

    def save(self, obj: T) -> T:
        """Insert or update (upsert) by id."""
        with self._lock:
            records = self._read_raw()
            d = obj.to_dict()
            for i, r in enumerate(records):
                if r.get("id") == d["id"]:
                    records[i] = d
                    self._write_raw(records)
                    return obj
            records.append(d)
            self._write_raw(records)
        return obj

    def delete(self, entity_id: int) -> bool:
        with self._lock:
            records = self._read_raw()
            new = [r for r in records if r.get("id") != entity_id]
            if len(new) == len(records):
                return False
            self._write_raw(new)
        return True


# ---------------------------------------------------------------------------
# Specialised repositories
# ---------------------------------------------------------------------------
class UserRepo(Repository[User]):
    def __init__(self):
        super().__init__("users.json", User)

    def by_email(self, email: str) -> Optional[User]:
        for u in self.all():
            if u.email.lower() == email.lower():
                return u
        return None

    def by_role(self, role: str) -> List[User]:
        return self.filter(role=role)


class CategoryRepo(Repository[Category]):
    def __init__(self):
        super().__init__("categories.json", Category)


class ProductRepo(Repository[Product]):
    def __init__(self):
        super().__init__("products.json", Product)

    def available(self) -> List[Product]:
        return self.filter(is_available=True)

    def by_category(self, category_id: int) -> List[Product]:
        return self.filter_fn(lambda p: p.category_id == category_id and p.is_available)


class OrderRepo(Repository[Order]):
    def __init__(self):
        super().__init__("orders.json", Order)

    def by_customer(self, customer_id: int) -> List[Order]:
        return self.filter(customer_id=customer_id)

    def draft_for(self, customer_id: int) -> Optional[Order]:
        results = self.filter_fn(
            lambda o: o.customer_id == customer_id and o.status == "draft"
        )
        return results[0] if results else None

    def non_draft(self) -> List[Order]:
        return self.filter_fn(lambda o: o.status != "draft")


class OrderItemRepo(Repository[OrderItem]):
    def __init__(self):
        super().__init__("order_items.json", OrderItem)

    def by_order(self, order_id: int) -> List[OrderItem]:
        return self.filter(order_id=order_id)


class PaymentRepo(Repository[Payment]):
    def __init__(self):
        super().__init__("payments.json", Payment)

    def by_order(self, order_id: int) -> Optional[Payment]:
        results = self.filter(order_id=order_id)
        return results[0] if results else None


class DesignRequestRepo(Repository[DesignRequest]):
    def __init__(self):
        super().__init__("design_requests.json", DesignRequest)

    def by_customer(self, customer_id: int) -> List[DesignRequest]:
        return self.filter(customer_id=customer_id)

    def pending(self) -> List[DesignRequest]:
        return self.filter_fn(lambda d: d.status in ("pending", "revision_requested"))

    def by_designer(self, designer_id: int) -> List[DesignRequest]:
        return self.filter_fn(
            lambda d: d.designer_id == designer_id and d.status == "in_progress"
        )


class SupplierRepo(Repository[Supplier]):
    def __init__(self):
        super().__init__("suppliers.json", Supplier)


class SupplierOrderRepo(Repository[SupplierOrder]):
    def __init__(self):
        super().__init__("supplier_orders.json", SupplierOrder)

    def open_orders(self) -> List[SupplierOrder]:
        return self.filter_fn(lambda o: o.status in ("open", "partial"))

    def completed_orders(self) -> List[SupplierOrder]:
        return self.filter_fn(lambda o: o.status in ("delivered", "closed"))


class SupplierOrderItemRepo(Repository[SupplierOrderItem]):
    def __init__(self):
        super().__init__("supplier_order_items.json", SupplierOrderItem)

    def by_order(self, supplier_order_id: int) -> List[SupplierOrderItem]:
        return self.filter(supplier_order_id=supplier_order_id)


class DeliveryRepo(Repository[Delivery]):
    def __init__(self):
        super().__init__("deliveries.json", Delivery)

    def by_order(self, order_id: int) -> Optional[Delivery]:
        results = self.filter(order_id=order_id)
        return results[0] if results else None

    def by_worker(self, worker_id: int) -> List[Delivery]:
        return self.filter_fn(
            lambda d: d.field_worker_id == worker_id
            and d.status in ("scheduled", "rescheduled", "failed")
        )

    def unassigned(self) -> List[Delivery]:
        return self.filter_fn(
            lambda d: d.field_worker_id is None and d.status == "scheduled"
        )

    def active(self) -> List[Delivery]:
        return self.filter_fn(lambda d: d.status in ("scheduled", "rescheduled", "failed"))

    def completed(self) -> List[Delivery]:
        return self.filter_fn(lambda d: d.status in ("delivered", "cancelled"))

    def completed_by_worker(self, worker_id: int) -> List[Delivery]:
        return self.filter_fn(
            lambda d: d.field_worker_id == worker_id
            and d.status in ("delivered", "cancelled")
        )


class ClaimRecordRepo(Repository[ClaimRecord]):
    def __init__(self):
        super().__init__("claim_records.json", ClaimRecord)


# ---------------------------------------------------------------------------
# Singleton store – import this in app.py
# ---------------------------------------------------------------------------
class DataStore:
    """Central access point for all repositories."""

    def __init__(self):
        self.users = UserRepo()
        self.categories = CategoryRepo()
        self.products = ProductRepo()
        self.orders = OrderRepo()
        self.order_items = OrderItemRepo()
        self.payments = PaymentRepo()
        self.design_requests = DesignRequestRepo()
        self.suppliers = SupplierRepo()
        self.supplier_orders = SupplierOrderRepo()
        self.supplier_order_items = SupplierOrderItemRepo()
        self.deliveries = DeliveryRepo()
        self.claims = ClaimRecordRepo()

    # --- cart helpers ---

    def get_cart_items(self, order: Order) -> List[OrderItem]:
        return self.order_items.by_order(order.id)

    def recalculate_order(self, order: Order) -> Order:
        items = self.order_items.by_order(order.id)
        order.total_price = round(sum(i.unit_price * i.quantity for i in items), 2)
        self.orders.save(order)
        return order

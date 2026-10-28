# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A small three-module Python service for the git fixture to commit.

``orders``, ``billing`` and ``accounts`` each have a few functions that
call within their module and a little across modules, so the indexer finds
a call graph with several communities to cluster, label and synthesise.
"""

from __future__ import annotations

_ORDERS_MODELS = """
class Order:
    def __init__(self, order_id, items):
        self.order_id = order_id
        self.items = items

    def total(self):
        return sum(item.price * item.quantity for item in self.items)


class OrderLine:
    def __init__(self, sku, price, quantity):
        self.sku = sku
        self.price = price
        self.quantity = quantity
"""

_ORDERS_SERVICE = """
from shop.orders.models import Order, OrderLine
from shop.billing.invoices import create_invoice


def build_order(order_id, lines):
    return Order(order_id, [OrderLine(*line) for line in lines])


def place_order(order_id, lines, account):
    order = build_order(order_id, lines)
    validate_order(order)
    return create_invoice(account, order)


def validate_order(order):
    if not order.items:
        raise ValueError("empty order")
    return order.total()


def cancel_order(order):
    order.items = []
    return order
"""

_ORDERS_ROUTES = """
from shop.orders.service import cancel_order, place_order


def post_order(request):
    return place_order(request["id"], request["lines"], request["account"])


def delete_order(order):
    return cancel_order(order)
"""

_BILLING_INVOICES = """
from shop.billing.tax import apply_tax


class Invoice:
    def __init__(self, account, amount):
        self.account = account
        self.amount = amount


def create_invoice(account, order):
    return Invoice(account, apply_tax(order.total()))


def void_invoice(invoice):
    invoice.amount = 0
    return invoice
"""

_BILLING_TAX = """
RATE = 0.2


def apply_tax(amount):
    return round(amount * (1 + RATE), 2)


def tax_due(amount):
    return round(amount * RATE, 2)
"""

_BILLING_PAYMENTS = """
from shop.billing.invoices import void_invoice


def charge(invoice, card):
    if not card:
        return refund(invoice)
    return {"invoice": invoice, "status": "paid"}


def refund(invoice):
    return void_invoice(invoice)
"""

_ACCOUNTS_USERS = """
class Account:
    def __init__(self, email, password_hash):
        self.email = email
        self.password_hash = password_hash


def register(email, password):
    return Account(email, hash_password(password))


def hash_password(password):
    return "".join(reversed(password))
"""

_ACCOUNTS_SESSIONS = """
from shop.accounts.users import hash_password


def sign_in(account, password):
    return account.password_hash == hash_password(password)


def sign_out(session):
    session.clear()
    return session
"""

SAMPLE_TREE: dict[str, str] = {
    "shop/__init__.py": "",
    "shop/orders/__init__.py": "",
    "shop/orders/models.py": _ORDERS_MODELS,
    "shop/orders/service.py": _ORDERS_SERVICE,
    "shop/orders/routes.py": _ORDERS_ROUTES,
    "shop/billing/__init__.py": "",
    "shop/billing/invoices.py": _BILLING_INVOICES,
    "shop/billing/tax.py": _BILLING_TAX,
    "shop/billing/payments.py": _BILLING_PAYMENTS,
    "shop/accounts/__init__.py": "",
    "shop/accounts/users.py": _ACCOUNTS_USERS,
    "shop/accounts/sessions.py": _ACCOUNTS_SESSIONS,
}

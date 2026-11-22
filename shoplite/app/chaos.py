"""Fault flags of the training stand.

Each flag breaks Shoplite in one specific way, so that the course's agents
have something real to find:

=================  =====================================================  ==============
flag               effect                                                 RCA class
=================  =====================================================  ==============
UI_VERSION=2       data-test names renamed, cart rendered as cards        ui_change
BUG_CART_TOTAL     the total ignores the promo discount                   product_bug
FLAKY_SEARCH=p     with probability p search waits 0–5 s                  flaky_test
DB_DOWN            pages and API answer 503                               infrastructure
FEATURE_WISHLIST   a new, untested feature appears                        (coverage gap)
=================  =====================================================  ==============

Flags start from the environment and can be changed at runtime through
``POST /__chaos``.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str) -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv(name, "0"))))
    except ValueError:
        return 0.0


@dataclass
class Chaos:
    ui_version: int = 1
    bug_cart_total: bool = False
    flaky_search: float = 0.0
    db_down: bool = False
    feature_wishlist: bool = False

    @classmethod
    def from_env(cls) -> "Chaos":
        ui = os.getenv("UI_VERSION", "1").strip()
        return cls(
            ui_version=2 if ui == "2" else 1,
            bug_cart_total=_env_bool("BUG_CART_TOTAL"),
            flaky_search=_env_float("FLAKY_SEARCH"),
            db_down=_env_bool("DB_DOWN"),
            feature_wishlist=_env_bool("FEATURE_WISHLIST"),
        )

    def update(self, changes: dict) -> None:
        known = {f.name for f in fields(self)}
        unknown = set(changes) - known
        if unknown:
            raise ValueError(f"Unknown flags: {', '.join(sorted(unknown))}")
        for key, value in changes.items():
            if key == "ui_version":
                if value not in (1, 2):
                    raise ValueError("ui_version must be 1 or 2")
            elif key == "flaky_search":
                value = float(value)
                if not 0.0 <= value <= 1.0:
                    raise ValueError("flaky_search must be between 0 and 1")
            elif not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            setattr(self, key, value)

    def as_dict(self) -> dict:
        return asdict(self)


state = Chaos.from_env()


# data-test names per UI version. UI_VERSION=2 is what a front-end refactoring
# looks like to autotests: same page, different hooks.
_V2_NAMES = {
    "nav-catalog": "menu-catalog",
    "nav-cart": "menu-cart",
    "nav-profile": "menu-account",
    "nav-logout": "menu-signout",
    "login-email": "signin-email",
    "login-password": "signin-password",
    "login-submit": "signin-button",
    "login-error": "signin-error",
    "search-input": "catalog-search",
    "search-submit": "catalog-search-button",
    "category-filter": "catalog-category",
    "product-card": "catalog-item",
    "product-title": "item-name",
    "product-price": "item-price",
    "add-to-cart": "buy-button",
    "cart-item": "basket-line",
    "cart-item-qty": "basket-line-qty",
    "cart-item-remove": "basket-line-delete",
    "cart-subtotal": "basket-subtotal",
    "cart-discount": "basket-discount",
    "cart-shipping": "basket-delivery",
    "cart-total": "order-sum",
    "promo-input": "coupon-code",
    "promo-apply": "coupon-apply",
    "checkout-button": "go-to-checkout",
    "checkout-address": "delivery-address",
    "checkout-submit": "place-order",
    "order-number": "order-id",
}


def dt(name: str) -> str:
    """The data-test value for ``name`` under the current UI version."""
    if state.ui_version == 2:
        return _V2_NAMES.get(name, name)
    return name

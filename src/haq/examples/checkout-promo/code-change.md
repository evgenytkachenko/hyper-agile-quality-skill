# Pull request #318 — SHOP-455 apply promo codes on the cart page

- State: merged
- Opened: 2026-02-24T09:00:00Z
- Merged: 2026-03-03T15:40:00Z
- Head commit: 4f2c1a9e
- Changed files: cart/promo.py (modified), cart/views.py (modified), cart/events.py (modified), tests/test_promo.py (added)

## Description

Adds a promo code field to the cart page. The discount is recalculated whenever the cart changes.

## Diff excerpt

```diff
+def apply_promo(cart, code):
+    subtotal = cart.total()  # total after discounts already applied
+    cart.discount += subtotal * code.percentage
+
+def on_quantity_changed(cart):
+    if cart.promo_code:
+        apply_promo(cart, cart.promo_code)
```

## Review

- 2026-03-03T15:30:00Z Approved by a reviewer: "Looks fine; tests cover valid and expired codes."

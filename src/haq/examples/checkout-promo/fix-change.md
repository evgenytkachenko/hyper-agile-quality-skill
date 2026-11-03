# Pull request #331 — SHOP-482 compute promo discount from the undiscounted subtotal

- State: merged
- Merged: 2026-03-14T17:20:00Z
- Changed files: cart/promo.py (modified), cart/events.py (modified), tests/test_promo.py (modified)

## Description

The quantity-change hook in cart/events.py re-applied the promo to a total that already included the
discount. The discount is now recalculated from the undiscounted subtotal on every cart change.
Adds test_promo_after_quantity_change.

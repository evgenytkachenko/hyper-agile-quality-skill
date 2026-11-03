# Test cases for promo codes (test-management export, fictional)

## TC-210 — Percentage promo code reduces the cart subtotal
- Precondition: Cart with one item priced 50.00, quantity 1.
- Steps: Apply code SPRING10.
- Expected: Subtotal 50.00, discount 5.00, total 45.00.
- Automation: automated as tests/test_promo.py::test_promo_applies_percentage

## TC-211 — Applied promo code is shown after reload
- Precondition: Cart with one item, code SPRING10 applied.
- Steps: Reload the cart page.
- Expected: The code SPRING10 is still shown as applied.
- Automation: manual

## TC-212 — Expired promo code is rejected
- Precondition: Code WINTER5 expired on 2026-02-01.
- Steps: Apply code WINTER5.
- Expected: Message "This code has expired"; no discount.
- Automation: automated as tests/test_promo.py::test_promo_rejects_expired

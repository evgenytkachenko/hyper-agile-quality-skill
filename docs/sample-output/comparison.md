# Comparison: `checkout-promo` vs `checkout-promo+missing-evidence`

- A answers: SCRIPTED RESPONSES (not a model)
- B answers: SCRIPTED RESPONSES (not a model)

Both runs used the same answer source, so every difference below comes from the evidence and the deterministic checks, not from different answers.

## Evidence files that differ

- `issues/SHOP-482.yaml`: changed
- `releases/4.2.0.yaml`: changed
- `test-results/ci-unit.xml`: only in A
- `tests.md`: only in A

## Checked results that differ

| Item | A | B |
| --- | --- | --- |
| Link SHOP-482 → SHOP-455 | DIRECT, CONFIRMED | INFERRED, STRONGLY SUPPORTED |
| Critical signal signal-002 | verified, CONFIRMED | not verified, UNKNOWN |
| Test TC-210 | RELATED BUT NOT DETECTING, STRONGLY SUPPORTED | RELATED BUT NOT DETECTING, UNKNOWN |
| Test TC-212 | RELATED BUT NOT DETECTING, CONFIRMED | RELATED BUT NOT DETECTING, UNKNOWN |
| Test tests.test_cart::test_quantity_update_changes_total | RELATED BUT NOT DETECTING, STRONGLY SUPPORTED | RELATED BUT NOT DETECTING, UNKNOWN |
| Hypothesis H2 | SUPPORTED, CONFIRMED | NOT ESTABLISHED, UNKNOWN |
| Hypothesis H3 | SUPPORTED, STRONGLY SUPPORTED | NOT ESTABLISHED, POSSIBLE CONTRIBUTING FACTOR |
| Hypothesis H5 | CONTRADICTED, UNKNOWN | NOT ESTABLISHED, UNKNOWN |
| Proposal C1 | 0 review flag(s) | 1 review flag(s) |
| Proposal C2 | 0 review flag(s) | 1 review flag(s) |
| Proposal C4 | 1 review flag(s) | 2 review flag(s) |

## Evidence limitations only in B

- No ci evidence artifact was provided in the case folder.
- No test evidence artifact was provided in the case folder.

## Evidence limitations only in A

- None.

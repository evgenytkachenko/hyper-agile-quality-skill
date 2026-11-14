# Verification record

Implementation date: 2026-11-14. Synthetic development fixtures only.

- Original HAQ Python suite: 272 passed after installing the environment-required SOCKS transport dependency. No original Python implementation changed.
- TypeScript suite: 51 tests passed (including 14 independent-agent acceptance cases and six tracing adapter/SDK checks); typecheck passed.
- Real HTTP demo: two incomplete benchmark tests passed; generated critical authorization test failed against vulnerable fixture; seven fixed API/targeted cases passed.
- Stryker: four mutants of the ownership predicate, four killed, zero survived/no-coverage/timeouts. Initial eight-mutant run had one equivalent mutant in a redundant guard; source simplified rather than excluding it or lowering the threshold.
- Actual native independent reviewer: identified missing isolation and partial authentication assertions; proposed 14 acceptance cases. After adapting imports/fixture selection, vulnerable benchmark had two failed isolation cases, secure implementation passed all 14. This is one development trial, not held-out accuracy.
- Deterministic eval set: 12 policy cases, four coverage cases and three synthetic trace cases. These are calibration cases, not agent quality metrics.
- Three Playwright browser cases written. Browser failed to launch under the current environment's socket restrictions before test bodies; no browser pass claimed locally.
- Codex CLI read-only review attempted twice, including approved elevated execution. Initialization failed with read-only app-server filesystem; no successful CLI model output.
- LangSmith adapter tests are offline/mocked. No credentials configured or real dashboard trace verified.
- GitHub Actions/rulesets: workflow prepared; hosted result must be checked for the pushed commit. Governance bootstrap intentionally requires owner review. No merge, release or branch protection change authorized/performed.

Raw reports are generated locally under ignored `evidence/` and `reports/`. Review them before sharing; they can include execution paths. A concise result is not a replacement for those records.

## Hosted-run follow-up

The first hosted run passed TypeScript tests, deterministic evals, the HTTP demo and mutation testing. Browser installation failed because `ubuntu-latest` resolved to Ubuntu 26.04, unsupported by the pinned Playwright release. The workflow now pins Ubuntu 24.04; browser results must still be verified on the new commit.

Dependency audit found vulnerable development dependencies. Vitest was updated to 4.1.12, tsx to 4.23.15, and a scoped typed-rest-client override selects qs 6.17.1. Current Stryker 10.1.1 still requests vulnerable minimatch 10.x, so a scoped override selects minimatch 11.0.8. Real selective Stryker execution validates this demo's compatibility; this does not establish every Stryker feature's compatibility. The updated lockfile audit reports zero known vulnerabilities; typecheck, 51 tests, the real HTTP demo and four-mutant run passed again. CI audits dependencies at moderate severity or above. No Vitest UI server is used.

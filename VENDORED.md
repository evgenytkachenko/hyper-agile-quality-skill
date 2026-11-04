# Vendored from hyper-agile-engine

The files below were copied from the hyper-agile-engine repository at commit `88b9b9f`
(branch `claude/six-rule-rebuild`) and are used unchanged, except where noted. They provide
the deterministic evidence checks, the methodology loader, the pass definitions for the two
engine passes this skill runs, and the Ollama provider.

Nothing else from the engine repository is included: not its connectors, collector, MCP/REST
transports, orchestrator, benchmark corpus, tests, fixtures, documentation, issue tracker data
or Git history.

`tests/test_vendored.py` fails if any file here changes without this table being updated.

| Vendored file | Engine source path | Changed? | SHA-256 here |
| --- | --- | --- | --- |
| `src/haq/_engine/errors.py` | `src/hyper_agile/errors.py` | no | `e93f18570e030f5d2aded8bf632a82d08933889115aee744efcf86e688b729bf` |
| `src/haq/_engine/network.py` | `src/hyper_agile/network.py` | no | `19170beff6f0fee282ae47cea6345bb7434bc5ec737da3bdfa82efdd08187c72` |
| `src/haq/_engine/masking.py` | `src/hyper_agile/masking.py` | no | `7ed6e075847db361d70498d00a6cff66cef0a631b9b1da42e68698ebbca4fd31` |
| `src/haq/_engine/claim_evidence.py` | `src/hyper_agile/claim_evidence.py` | no | `b8c89ce104251d24f5fe7f0bae471f90d16b9bcd9e0a83bd9e3d160d1759ab11` |
| `src/haq/_engine/evidence.py` | `src/hyper_agile/evidence.py` | yes (1) | `bf0c8b37ff2091745cf566d293b20c79647d7ae6a4255264811b51811d2fb3b5` |
| `src/haq/_engine/methodology.py` | `src/hyper_agile/methodology.py` | no | `9ed5f109ceb91c67741c89944f779cea60ad4b7afddf362ae7ae41272f3eeade` |
| `src/haq/_engine/passes.py` | `src/hyper_agile/passes.py` | no | `a7eeaeb72ff152008ef536d793ed3fb16ff95f48976cb7b9cf488926e29ab485` |
| `src/haq/_engine/guards.py` | `src/hyper_agile/guards.py` | no | `1cee94a2a4817e2771af4e04222fd0fc9e6142a4583a491baba0a85bcc9fdd44` |
| `src/haq/_engine/providers/base.py` | `src/hyper_agile/providers/base.py` | no | `7529f1ce4bf3eef8d0949e95bb6cc3fd9a2877670edcaf95ed4e39f0a6944f9f` |
| `src/haq/_engine/providers/ollama.py` | `src/hyper_agile/providers/ollama.py` | no | `6ab2962b5a80f989db392d3271c805f5f2e002508f33ce660d0d43ebe8208d90` |
| `src/haq/_methodology/SKILL.md` | `methodology/SKILL.md` | no | `788352b7bf4e7ece663c094e11f9dcfc28cc177ac30c33b664e61a7604f25318` |
| `src/haq/_methodology/references/causal-model.md` | `methodology/references/causal-model.md` | no | `f61e5353b4b8b0edabd48c1afe7e3725326cba90fed766a9c3d4acbdb2ee5f12` |
| `src/haq/_methodology/references/evaluation-harness.md` | `methodology/references/evaluation-harness.md` | no | `f945bad1b6124d85a1092418ca4102658a9b9895ab9032354d97f361741a4dbf` |
| `src/haq/_methodology/references/evidence-and-actions.md` | `methodology/references/evidence-and-actions.md` | no | `07f5538923d9f722043d2cffe6b873f4a89c2fd49a85d43db7bc7f36348a4c1d` |
| `src/haq/_methodology/references/quality-loop.md` | `methodology/references/quality-loop.md` | no | `276cb3af9a5c90432928480f15c25a51bb6909a33b93fd3a04ed826f909a9952` |
| `src/haq/_methodology/references/report-template.md` | `methodology/references/report-template.md` | no | `deae89f1688068f8c78b0212ba910e455de3529a80ec7000ab400db076c830c5` |
| `src/haq/_methodology/references/tool-mapping.md` | `methodology/references/tool-mapping.md` | no | `e1dceb5ce122e8df86deb51fc248cf54fb6629aa561c77d06d2ffdf776d2c048` |

(1) One example identifier in a code comment was replaced with a fictional `SHOP-` key.
No behavior changed.

Two package `__init__.py` files under `src/haq/_engine/` are new one-line docstrings; the
engine's own `providers/__init__.py` (which also registers a cloud provider) is not included.

## Licensing

The copyright holder licenses the files listed above, as included in this repository, under
the MIT License (see `LICENSE`), like the rest of this project. They are the author's own
work, copied from the author's own repository; no third-party code is vendored.

This applies to the copies in this repository only. The hyper-agile-engine repository has
no license file, and this project does not change its terms. Third-party dependencies are not
vendored and keep their own licenses.

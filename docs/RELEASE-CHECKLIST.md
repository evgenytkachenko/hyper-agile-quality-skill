# Before publishing

This candidate has not been published. These decisions belong to the copyright holder.

- [ ] **License.** None is chosen. Without one, the code is not open source. Choose a license
      for the code and decide whether the methodology files and documentation use the same one.
- [ ] **Vendored engine files** (`src/haq/_engine/`, `src/haq/_methodology/`). Confirm you own
      them outright and may publish them, including any work done for or with an employer or
      client, and that publishing them separately from the engine is intended.
- [ ] **Methodology and the book.** Confirm that the methodology files may be published under
      the chosen license and that the wording in `docs/book.md` and the README describes their
      relationship to the book correctly.
- [ ] **Project and package names.** `hyper-agile-quality-skill` and the `haq` command; check for
      conflicts on the package index and with any trademark you hold or know of.
- [ ] **Author identity in commit metadata.** Confirm the name and email address that should
      appear in public commits.
- [ ] **Engine references.** The README names hyper-agile-engine. Decide whether to link it, and
      whether it will be public.
- [ ] **Dependencies.** Runtime: pydantic (MIT), pydantic-core (MIT), httpx (BSD-3-Clause),
      httpcore (BSD-3-Clause), PyYAML (MIT), anyio (MIT), h11 (MIT), idna (BSD-3-Clause),
      certifi (MPL-2.0), typing-extensions (PSF). None is redistributed by this repository;
      confirm compatibility with the license you choose.
- [ ] **Fictional example.** Confirm "Example Shop", the `SHOP-` keys and the scenario do not
      resemble any real employer, customer or incident you know of.
- [ ] Run `python scripts/publication_check.py` and the tests on the exact commit to publish.

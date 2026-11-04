# Before publishing

The repository is public. Version 0.1.0-beta (package `0.1.0b0`) is prepared but not tagged or
released; tagging and a GitHub release need the copyright holder's approval of the exact commit
and of `docs/release-notes/v0.1.0-beta.md`. These decisions belong to the copyright holder.

- [x] **License.** MIT (`LICENSE`), chosen by the copyright holder. It covers the project's own
      code, documentation, agent skill, fictional example and sample output, and the methodology
      files, including the files copied from hyper-agile-engine (`VENDORED.md`). Dependencies are
      not included and keep their own licenses. The book is not included or licensed.
- [ ] **Vendored engine files** (`src/haq/_engine/`, `src/haq/_methodology/`). Confirm you own
      them outright and may publish and license them, including any work done for or with an
      employer or client, and that publishing them separately from the engine is intended.
- [ ] **Methodology and the book.** Confirm that the methodology files may be published under
      the MIT License and that the wording in `docs/book.md` and the README describes their
      relationship to the book correctly.
- [ ] **Project and package names.** `hyper-agile-quality-skill` and the `haq` command; check for
      conflicts on the package index and with any trademark you hold or know of.
- [ ] **Author identity in commit metadata.** Confirm the name and email address that should
      appear in public commits.
- [ ] **Engine references.** The README names hyper-agile-engine. Decide whether to link it, and
      whether it will be public.
- [x] **Dependencies.** Runtime: pydantic, pydantic-core, annotated-types, typing-inspection,
      PyYAML, anyio, h11 (MIT); httpx, httpcore, idna (BSD-3-Clause); certifi (MPL-2.0);
      typing-extensions (PSF-2.0). Tests only: pytest, pluggy, iniconfig (MIT), packaging
      (Apache-2.0 OR BSD-2-Clause), Pygments (BSD-2-Clause). Build only: hatchling. None is
      included in this repository or its packages, so no third-party notices are required here;
      all are compatible with MIT.
- [ ] **Fictional example.** Confirm "Example Shop", the `SHOP-` keys and the scenario do not
      resemble any real employer, customer or incident you know of.
- [ ] Run `python scripts/publication_check.py` and the tests on the exact commit to publish.
- [ ] Approve the release notes and the exact commit; then tag `v0.1.0-beta` and publish the
      GitHub release (marked as a pre-release).

# WI-016 PDF dependency decision — 2026-08-31

Engineering evidence, not policy or an outbound license decision. Authority is
the explicit WI-016 Owner instruction and separately evaluated Project Home
bounded_execute. Live rules include DEV-P05, DEV-P06, CPKS-POL-SW-SUPPLY,
CPKS-SPEC-SRC, CPKS-SPEC-SEC, CPKS-SPEC-OPS, CPKS-DEC-042 and CPKT-SPEC-ARCH.

Research Gate required: neutral models, capture, policy, storage and consumers
are reused, but HTML cannot parse PDF. Building font/stream/layout parsing would
add unjustified complexity and security maintenance. The Standard Operation
Registry has no PDF/reuse/WI operation; bounded static wheel inspection and
task-local assessment persistence are therefore used.

| Candidate | Evidence | Disposition |
| --- | --- | --- |
| pdfplumber 0.11.10, MIT | Official wheel/license/hash; static Git `4c64b92d5caccd71c645e98e0fabb0c4dba7ff45`; actual Python 3.14.6 text/page/line/2×2 table experiment | WRAP, accepted_with_conditions for local digital-PDF reference scope |
| pypdf 6.16.2, BSD-3-Clause | Official wheel/license/hash; static Git `2f3ed6b8952e2fbafd57ca51ec250f3d98e68b79`; same text experiment | LEARN; no required additional runtime benefit; isolated comparator/fixture generation only |
| Docling 2.123.1, MIT declaration | Official package metadata, docling-slim release/manifest/docs; Git acquisition failed | LEARN; no installation, model spike or product admission |

Git HEAD inspection is research evidence, not proof that those commits produced
the wheels. Core inspect_internal, research_gate, inspect_candidate (two acquired
repositories), validate_assessment and scoped integration_handover ran. Primary
generated JSON and external Docling comparison remain under
`artifacts/handovers/WI-016/implementation/`. No Docling snapshot was invented.

pdfplumber provides positioned text and tables behind one wrapper. pypdf's
smaller base would need additional geometry/table work or duplicate the parser.
Docling now depends on `docling-slim[standard]==2.123.1`; slim's modular backends
are useful prior art, but standard includes models/OCR/many formats. No remaining
material question in this limited reference scope justified a model/layout spike.
Complex multi-column/table PDF quality is not claimed generally solved.

## Reviewed wheel closure

Only pdfplumber is a new direct product dependency. Exact Darwin arm64 / Python
3.14 wheels are pinned with SHA-256 in `pdf-darwin-arm64-py314-requirements.txt`.

| Distribution | Version | License evidence |
| --- | --- | --- |
| pdfplumber | 0.11.10 | Full MIT LICENSE.txt despite absent modern license metadata |
| pdfminer.six | 20260107 | MIT |
| charset-normalizer | 3.5.1 | MIT |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause plus native/SBOM evidence |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |
| Pillow | 12.3.0 | MIT-CMU plus bundled native notices |
| pypdfium2 | 5.13.0 | Apache-2.0/BSD-3-Clause, PDFium and dependency notices |

All downloaded wheels matched official versioned PyPI hashes. Full license and
notice texts, requirements, native files and startup hooks were inspected before
installation. No new .pth hook or source build is used. pdfminer console scripts
are not invoked. Product installation followed a successful isolated experiment
and root-reviewed admission. Existing cffi 2.1.0 and cryptography 49.0.0 upgraded
to the reviewed versions; pycparser 3.0 already existed. The separate scanner
environment was not changed.

Native code remains in CFFI, charset-normalizer, cryptography, Pillow and PDFium.
PDFium is 153.0.7999.0. cryptography's SBOM reports OpenSSL 4.0.2 and 39 additional
Rust components including build components. PDFium/Pillow rendering is unused.
FreeType's FTL and self_cell's Apache alternatives preserve permissive use; GPL
mentions in Pillow notices do not license the entire wheel under GPL. Future
binary redistribution must preserve PDFium/FTL/IJG and other relevant notices;
documentation/examples may carry CC-BY-4.0. Redistribution is outside this task.

Official release advisory metadata was empty for the selected versions. Separate
read-only review found pdfminer GHSA-wf5f-4jwr-ppcp and GHSA-f83h-ghpp-7wcc fixed
before 20260107; the selected CMap loader uses JSON, not Pickle. These checks are
not a full native-component or vulnerability audit. Upstream unreleased
OOM/recursion hardening reinforces the controlled-input limitation: cooperative
limits are not a sandbox.

Conditions: exact reviewed pins/wheels; no source-build fallback, copying,
vendoring, OCR/render/repair/remote/credential paths or automatic updates. Preserve
installed third-party notices. Changed versions, platforms, privileges, source
exposure or distribution require delta/use-context review. Replacement/removal
must check other consumers; historical snapshots retain bytes and require the
recorded parser environment for exact rebuild. No new Owner microgate is added.

Sources: [pdfplumber](https://github.com/jsvine/pdfplumber),
[pypdf](https://github.com/py-pdf/pypdf),
[Docling Slim](https://pypi.org/project/docling-slim/2.123.1/),
[pdfminer advisory 1](https://github.com/pdfminer/pdfminer.six/security/advisories/GHSA-wf5f-4jwr-ppcp),
[pdfminer advisory 2](https://github.com/pdfminer/pdfminer.six/security/advisories/GHSA-f83h-ghpp-7wcc).

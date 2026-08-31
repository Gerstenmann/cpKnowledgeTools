# Local assurance development dependencies

Engineering evidence, not a policy or general distribution approval.
Owner authority: local enablement task of 2026-08-31. Live rule homes resolved:
DEV-P05, DEV-P06, CPKS-POL-SW-SUPPLY, CPKS-SPEC-SEC, CPKS-SPEC-OPS and
CPKS-DEC-042. Research gate required for the new execution/dependency boundary.

Decision: USE coverage 7.16.0, mypy 2.3.1 and Hypothesis 6.167.1 as pinned local
development tools. No production import, vendoring, modification of upstream
files, service exposure or distribution of these tools is introduced. Existing
pytest and Ruff remain in use. No second test runner or SAST framework is added.

Official PyPI project metadata and downloaded CPython 3.14 macOS ARM64 wheels
were inspected before installation. Wheel dependencies, license files, native
extensions and startup hooks were examined without importing candidate code.
Existing environment passed `pip check` before the change. Wheel inspection is
not supported by the existing Git-candidate inspector or Standard Operation
Registry, so bounded standard-library ZIP/metadata inspection was used.

| Component | License evidence | Local disposition |
| --- | --- | --- |
| coverage 7.16.0 | Apache-2.0, bundled LICENSE/NOTICE | accepted for explicit local coverage runs |
| mypy 2.3.1 | MIT; bundled typeshed Apache-2.0/MIT | accepted for local static analysis |
| Hypothesis 6.167.1 | MPL-2.0 bundled license | accepted for unmodified local test use |
| pathspec 1.1.1 | bundled MPL-2.0 LICENSE (metadata expression absent) | accepted as unmodified development transitive |
| mypy_extensions 1.1.0, librt 0.15.0, ast_serialize 0.8.0 | bundled MIT licenses | accepted development transitives |
| sortedcontainers 2.4.0 | bundled Apache-2.0 | accepted test transitive |
| typing_extensions 4.16.0 | PSF-2.0 metadata/license; existing environment dependency | retain existing dependency; no upstream copying |

The MPL review is limited to separate, unmodified internal development/test use;
no covered source is copied into CPKT files. License and notice files remain with
installed distributions. Any modification, vendoring, bundling or external
distribution requires a new use-context/obligation review before that action.
This decision does not select an outbound CPKT license.

Native wheels are used without compiling or running installation hooks. Coverage
ships `a1_coverage.pth`, whose inspected code invokes coverage startup only when
`COVERAGE_PROCESS_START` or `COVERAGE_PROCESS_CONFIG` is set. Assurance subprocesses
clear inherited coverage startup settings; subprocess patching is not enabled.
Tools run in the host's existing sandbox on authorized repository inputs, with
no provider credentials or intentional network access. Tools cannot enforce the
host sandbox themselves.

Conditions: preserve pins and environment provenance, run local compatibility
checks, do not auto-update, and reassess changed license/privilege/transitive
scope. Full vulnerability/maintainer/signature review is not claimed. The lack
of a completed vulnerability scan remains an assurance gap, not a clean result.
Rollback removes only these newly admitted tools/dependencies after checking
other consumers; no global Python environment is changed.

Sources: [coverage](https://pypi.org/project/coverage/),
[mypy](https://pypi.org/project/mypy/),
[Hypothesis](https://pypi.org/project/hypothesis/),
[MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

## Separate scanner stack (2026-08-31)

DEV-P06 decision, before installation: WRAP CycloneDX Python 7.3.1
(Apache-2.0), pip-audit 2.10.1 (Apache-2.0), Gitleaks 8.30.1 (MIT), and
Grant 0.6.8 (Apache-2.0), accepted_with_conditions for unmodified local tool
execution only. The Owner's bounded scanner-stack task supplies execution
authority; this record and scanner findings do not supply authority themselves.
Rule homes: DEV-P05, DEV-P06, CPKS-POL-SW-SUPPLY, CPKS-SPEC-OPS,
CPKS-SPEC-SEC, CPKS-SPEC-TST, CPKT-SPEC-ARCH and CPKS-DEC-042, resolved live.

The existing four adapters fit the requested scope. Building replacement
scanners would duplicate maintained upstream inventories, rules and advisory
clients. Additional scanners are excluded by the task. The boundary remains
fixed CLI arguments and safe normalized evidence, with no imported scanner
library in the project and no copied upstream implementation.

Official versioned PyPI metadata and all 49 resolved wheels were inspected
without executing them; their SHA-256 hashes match PyPI. No source distribution,
build hook, `.pth`, sitecustomize or usercustomize is installed. Entry points are
ordinary console scripts, except Lark's optional PyInstaller hook (not loaded).
The admitted execution form uses the separate Venv's absolute Python executable
with `-I -B -m`, avoiding location-dependent console-script shebangs. Both the
interpreter and installed site-packages are fingerprinted. The manifest and
hash-locked wheel requirements are technical evidence for this stack only.

Material Python transitives include requests/urllib3/CacheControl/certifi for
PyPI transport, pip-api/pip (startup queries `python -m pip --version`, not an
installation), CycloneDX's library and JSON validation stack, and native wheels
for lxml, rpds-py, msgpack, tomli and charset-normalizer. Pip's bundled Windows
launchers are not executed on Darwin. The full resolved graph is retained in
the machine-readable admission, rather than added to project dependencies.

Specific license review for this unmodified internal tool environment:
chardet is LGPL-2.1-or-later; certifi and fqdn are MPL-2.0. They remain separate
upstream distributions; no covered code is copied into CPKT, modified, bundled
or externally distributed. lxml has BSD-3-Clause/PSF components and bundled
MIT/zlib/LGPL-2.1 iconv libraries. Its LICENSES also identifies GPL test tooling
and incompletely licensed XML transformation resources; these are outside the
admitted JSON-only scanner path. This is not an approval to reuse or distribute
those files. License-expression includes attributed CC-BY-4.0 license data;
its notices remain installed. packageurl-python's wheel omits its license file,
but the exact upstream v0.17.6 `mit.LICENSE` resolves MIT. rfc3987-syntax's
Apache classifier conflicts with its MIT expression; the v1.1.0 full LICENSE
and pyproject resolve MIT. Defusedxml uses PSF-2.0. These findings are retained,
not converted into claims of flawless package metadata.

Native tools use only official Darwin arm64 release archives, checked against
published checksums and GitHub artifact digests. They link OS libraries and
contain Go dependencies. Grant's official SBOM inventories 271 packages,
including embedded Syft; no standalone Syft CLI is introduced. Grant's checksum
signature verifies against its supplied certificate, whose workflow identity
was inspected. Fulcio-chain/Rekor validation is not claimed. Gitleaks has no
equivalent signature verified here. Hashes prove byte integrity, not safety.

Conditions: separate ignored tool environment; exact pins and fingerprints;
no automatic updates, privileged installer, global installation, target package
resolution, remediation or distribution; temporary clean HOME/XDG/CWD and no
inherited credentials; bounded output/runtime/cache; only explicit local SBOM
input for Grant list, never Grant check; Gitleaks directory scans only. Ordinary
offline runs make no intentional network request. Only explicitly authorized
pip-audit PyPI queries disclose public distribution names/versions; no source
content is submitted. Host filesystem/network isolation remains required.
Changing inputs, versions, platform, license or privileges requires delta review.

Replacement removes only this isolated stack and its invocation paths, leaving
project dependencies unchanged. Rebuilding uses hash-locked wheels and official
archives; no source build is approved. External distribution, XML processing,
untrusted project execution and sensitive Owner-data scanning require separate
review. Unknown transitive license/health or signature details outside this
use-context remain assurance gaps; this is not a universal supply-chain approval.

Primary sources and concrete artifact/provenance hashes are in
`scanner-admission.json`; generated research, real runs and review evidence
remain under `artifacts/assurance/` and `artifacts/handovers/`.

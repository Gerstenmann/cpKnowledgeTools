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

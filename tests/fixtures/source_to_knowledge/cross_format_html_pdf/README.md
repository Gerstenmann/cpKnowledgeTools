# WI-017 HTML/PDF equivalent content

Scenario role: **adapter_conformance**, version 1. These independently authored,
synthetic inputs are separate from the existing Minecraft regression baseline.
They contain no real personal, operational or confidential data.

| Case | Known deterministic interpretation | Technical differences |
| --- | --- | --- |
| open | Pilot capacity and training date | HTML paragraph/inline emphasis/list/time; PDF wraps statements across lines and uses two pages |
| restricted | Provisional pilot budget | HTML paragraph/inline emphasis; PDF one page with different line boundaries |

`scenario.v1.json` describes inputs and synthetic source policy anchors only.
`tests/golden/source_to_knowledge/cross_format_html_pdf/expected.v1.json` is an
independent test oracle, read after interpretation. Extraction patterns and
semantic mappings in the test contain no expected material values. Both sides
use `RuleBasedSemanticInterpreter` through original `NormalizedRecord` and
resolved `EvidenceAddress` objects. No runtime cross-format canonicalizer exists.

The assertion-only content projection compares **all** normalized text, preserving
words, punctuation, order and repetition. It collapses whitespace and ignores a
space before terminal `.`, `!` or `?` followed by whitespace/end of text: HTML
inline nodes may separate sentence punctuation. It never joins words or digits,
drops punctuation, or accepts partial coverage as complete equivalence. This is a
bounded scenario comparison, not a universal definition of semantic equivalence.

Candidate comparison retains the full payload and multiplicity, including roles,
time, epistemics, qualifiers, applicability, profiles, conflicts, gaps, extraction
values and producer/mapping strategy. Every original source/evidence binding is
resolved and checked against its own claim before concrete provenance references
are abstracted in a comparison copy. IDs, selectors, raw bytes and segment trees
remain separate. One PDF page may ground a statement carried by an HTML paragraph.
The two-page example tests N:1 page lineage inside one SourceRecord, not merging
separate documents into a common Source identity.

Protection uses `PA-WI017-RESTRICTED` on the **source snapshot**, with real synthetic
PolicyEvaluator decisions for each exact Evidence/Snapshot subject, consumer,
purpose and operation. It does not equate the HTML-only `internal-note` marker or
the `restricted` boolean with a universal policy verdict. Trusted local processing
is distinct from the gated public `resolve_content` operation. Open permits must
not unlock a protected counterpart in either direction.

PDF bytes were generated once using the existing first-party
`tests.sources.pdf_fixture.digital_pdf`, with no new library or generator:

```python
digital_pdf((
    "The pilot is limited to\n16 students, rather than the initial estimate of 20.",
    "Team training starts on\n26 September 2024.",
), title="Cross-format pilot")

digital_pdf((
    "For internal budgeting only, the initial pilot has a\n"
    "provisional cost ceiling of EUR\n3,200.\n"
    "A public-facing description may state only that the pilot\n"
    "has an approved internal budget.",
), title="Cross-format budget")
```

`tests/sources/test_cross_format_conformance.py` names CF-01 through CF-12 in its
contract tests. Additional negative tests challenge loss/addition/duplication,
changed values, gaps, ambiguous passages, forged provenance, format routing,
Golden access and literal-expected runtime substitution. Existing HTML-specific
Minecraft/Post-R5 runners remain regression evidence; this checkpoint does not
claim those runners accept PDF inputs or cover every semantic candidate category.

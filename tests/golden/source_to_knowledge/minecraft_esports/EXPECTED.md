# Mini-Dossier – Expected semantic test points

This file is **test design**, not a source document.

## Source documents

1. `01-program-proposal.html`
2. `02-school-response.html`
3. `03-pilot-status.html`

The HTML files are synthetic adaptations inspired by a real email dialogue.
Names, organization names, dates, quantities and the final status have been
modified deliberately. Embedded images from the RTFD source are excluded.

## Required semantic coverage

### Shared entities
- Rhein-Main International School
- CodeLab Rhine-Main
- Chris Berger
- Vera Anders
- Alex Bryant
- James Stone
- Minecraft Education esports pilot

### Time / state progression
- 12 Sep concept workshop: proposed in document 1, confirmed in document 3.
- Team training: 19 Sep proposed in document 1, replaced by 26 Sep in document 3.
- Capacity: about 20 estimated in document 1, limited to 16 in document 3.
- Adviser: not selected in document 2, James Stone selected in document 3.
- Initial scope: academic + extracurricular still open in document 2, after-school only in document 3.
- External competition: proposed as a later phase in document 1, explicitly not approved yet in document 3.

### Epistemic distinctions
- Statements about general benefits of Minecraft Education in document 1 are reported/general claims and must not become `confirmed` solely from this source.
- The school response in document 2 records that previous Minecraft use was described as successful; this is a reported statement, not an independently verified outcome.
- Confirmed pilot decisions in document 3 can be treated as authoritative for the synthetic pilot status within the fixture context.

### Evidence
- Multiple evidence addresses should contribute to the same pilot subject.
- Earlier source states must remain resolvable after later updates.
- The later source must not overwrite or erase earlier proposed states.

### Conflict / qualification / supersession behavior
- 19 Sep versus 26 Sep is a controlled plan change.
- About 20 students versus a maximum of 16 is an estimate-to-decision change.
- Academic integration is considered in document 2 but deferred in document 3.
- External competition remains a future possibility, not an approved current state.

### Event coverage
At minimum:
- concept workshop
- team training start
- internal pilot

### Policy boundary
The restricted internal note in document 3 provides a test for:
- claim read: "The pilot has an approved internal budget."
- evidence resolution: exact amount EUR 3,200.
A test consumer may be permitted to read the abstract claim while being denied
resolution of the exact amount.

### Publication / derived-state coverage
The E2E test should produce an unpublished Knowledge Object Publication Unit,
then a deterministic retrieval projection, delete that derived projection, and
rebuild it semantically equivalently from the canonical test inputs.

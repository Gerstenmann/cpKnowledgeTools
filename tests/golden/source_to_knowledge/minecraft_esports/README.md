# Minecraft Education Esports – Synthetic Mini-Dossier

## Purpose

This directory is a candidate fixture set for the source-neutral
Source-to-Knowledge Core MVP.

It was derived from a real RTFD-exported email dialogue, but the fixture content
has been deliberately rewritten and anonymized. The fixture is therefore
synthetic and should be safe to version in a test repository after normal
project review.

## Why the dialogue is suitable

The source dialogue naturally contains:
- multiple participants,
- a proposal and a school response,
- an evolving project scope,
- planned versus not-yet-decided states,
- dates and scheduling,
- educational objectives,
- a multi-phase program concept.

The synthetic third document adds a controlled confirmed state so the fixture
also exercises:
- temporal updates,
- changed quantities,
- role resolution,
- scope decisions,
- postponed versus approved actions,
- a restricted-evidence case.

## Files

- `01-program-proposal.html` — proposed program and initial assumptions.
- `02-school-response.html` — school response with unresolved decisions.
- `03-pilot-status.html` — synthetic later confirmation and controlled changes.
- `EXPECTED.md` — test-design expectations; it is not source evidence.

Embedded images from the original RTFD package are intentionally excluded.

## Important boundary

The expected semantic model must not be encoded into the source adapter.
The adapter should only recover source structure/content and materialize the
source/evidence contracts. `EXPECTED.md` belongs to the test harness, not to
the source-processing path.

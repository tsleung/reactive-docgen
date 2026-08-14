# Fixture: missing-last-updated

**Category:** doctrine-stale
**Gates:** `content-doctrine.rdg` Pass 2 (doctrine-health)
**Expected verdict:** STALE / CONCERN — "Content Freshness / Doctrine Metadata"

## What this fixture demonstrates

CLAUDE.md §8 mandates that every doctrine doc carry `**Last Updated:**` and `**Status:**` headers. This fixture plants a doc that omits them. The `content-doctrine.rdg` pipeline must flag it.

The check is trivial — a regex on the first ten lines would catch it. But the value of the fixture is that it pins the trivial-check behavior down: if a future prompt revision relaxes this, RDG silently loses its freshness immune system.

## Why a regression here matters

Most doctrine drift happens via doc edits that don't bump `Last Updated:`. If RDG accepts missing metadata, it cannot detect the broader pattern of doctrine staleness — the trivial case is the canary.

## How to extend

Add fixtures for:
- `Last Updated:` present but >90 days old (Claim-freshness STALE per Convention 6).
- `Status:` missing while `Last Updated:` is fresh.
- Doctrine doc whose body contradicts CLAUDE.md (substantive drift, not metadata drift).

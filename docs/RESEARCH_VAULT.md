# Research Vault v0.1

## Purpose

The Research Vault is the studio's provenance-aware knowledge workspace. It separates source records, captured evidence and project-level claims so that creative work can distinguish sourced facts from interpretation and invention.

## First implementation slice

- Register URL, document, note, transcript, dataset and other source records.
- Link one source to multiple projects without duplicating its identity.
- Associate an existing content-addressed Asset with a source. When the source is project-linked, the asset must already be attached to that same project.
- Preserve author, publisher, publication date, retrieval date, language, summary, URL and flexible metadata.
- Capture evidence excerpts with locators such as page, section, timestamp or dataset row.
- Deduplicate identical evidence for the same source using SHA-256 content identity.
- Create project claims and connect evidence as supporting, contradicting or contextualizing.
- Keep claims in draft/reviewed/accepted/rejected states. Accepting a claim requires supporting evidence; rejecting it requires contradicting evidence.
- Append provenance events for source, evidence, project-link and claim changes.

## Explicit boundaries

- URL records are metadata only. This milestone does not fetch or crawl external URLs.
- No automatic scraping, browser access, PDF extraction, OCR, transcription, embeddings or AI claim extraction is enabled.
- No source is automatically treated as authoritative. Trust assessment remains a future explicit review dimension.
- Evidence excerpts preserve supplied text and locator; they are not silently paraphrased.
- Removing a project link does not delete the source, evidence or underlying asset. A source cannot be detached from a project while one of that project's claims still cites its evidence.
- The current API has no authentication. Keep it bound to localhost or a trusted private environment.

## API

All routes are under /api/v1:

- POST /research/sources
- GET /research/sources?project_id=...&limit=...&offset=...
- GET /research/search?q=...&project_id=...&limit=... (read-only search across source metadata, exact evidence excerpts/locators and claims)
- GET /research/sources/{source_id}
- POST /research/sources/{source_id}/projects/{project_id}
- DELETE /research/sources/{source_id}/projects/{project_id}
- POST /research/sources/{source_id}/evidence
- GET /research/sources/{source_id}/evidence
- POST /research/claims
- GET /research/claims?project_id=...
- GET /research/claims/{claim_id}
- PATCH /research/claims/{claim_id}
- POST /research/claims/{claim_id}/evidence/{evidence_id}

## Data integrity

- Sources may exist in the universal vault without a project association.
- Project-source links are unique and idempotent.
- Evidence identity is scoped to a source and based on source ID, evidence type, excerpt and locator.
- A claim can only cite evidence from a source linked to that claim's project.
- Claim/evidence links are unique per pair; changing the relationship updates the existing link and appends an event. An accepted claim cannot lose its last supporting relation, and a rejected claim cannot lose its last contradicting relation.
- Research events store entity IDs and action metadata, not full source excerpts or secrets.
- Search is read-only, case-insensitive, project-scoped when requested, escapes SQL LIKE wildcard characters and returns bounded results separately for sources, evidence and claims.

## Later milestones

- Safe local file ingestion and extraction pipeline with quarantine and MIME-aware parsers.
- Browser-assisted/manual capture with explicit user action; no background URL fetch without a dedicated SSRF-safe fetch subsystem.
- OCR, audio/video transcription, document chunking and page/timecode provenance.
- AI-assisted claim extraction with model/prompt/version provenance and mandatory human review.
- Source credibility assessment, cross-source corroboration, contradiction graphs and evidence confidence.
- Semantic search and embeddings behind a local-first index abstraction.


## Verification

- Service-level tests cover URL validation/canonicalization, project association, source-link idempotency, evidence deduplication, claim review requirements and provenance events.
- HTTP integration tests cover the source → evidence → claim → review flow and verify that a source cannot be detached while a project claim still cites its evidence.
- Asset-link validation tests ensure a source cannot attach a file from a different project.
- The complete backend suite and Alembic migration to revision 0012 passed in GitHub Actions run 44510598517 (86 tests, one non-failing warning).


## Research search v0.2

The workspace now provides one read-only search across source title/URL/author/publisher/summary, exact evidence excerpt/locator and claim statement/rationale. Results can be scoped to a project or searched across the vault. Search does not rewrite evidence, create embeddings, fetch remote URLs or change provenance. Each result group has an independent bounded limit and reports the full matching count.

## Verification

- Backend CI run [44515790910](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44515790910): 88 tests passed, 1 warning; migration to head succeeded.
- Frontend build run [44515790960](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44515790960): successful.

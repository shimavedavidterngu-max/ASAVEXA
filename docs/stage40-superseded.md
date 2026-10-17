# Stage 40 — Superseded state for proof links

A proof link can now be marked **Superseded** when a newer link replaces it.

- A person who can prepare records picks an active or disputed link, chooses a newer active link that starts from the same record, and gives a reason.
- The old link keeps its full history, points to its replacement (`superseded_by`), loses any confirmation, and leaves the live picture. The newer link records what it replaced (`supersedes`).
- A link cannot replace itself, a replacement must be active and start from the same record, and a retired or already superseded link cannot be superseded.
- Audit: `GRAPH_LINK_SUPERSEDED` (references and outcome only, no free text).
- Route: `POST /proof-links/{id}/supersede` (`grc:prepare`). Other organisations get 404.

Status: VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.

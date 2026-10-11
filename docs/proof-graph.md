# Proof-to-Report Graph and architecture check

## What it does
- **Proof Graph** (menu: Proof Graph, needs `reporting:read`): choose a period and a report (balance sheet or income statement). Each figure is shown with the journals it is built from, and each journal with the evidence behind it.
- **Is every layer connected?** A live check on the server: each of the 10 layers in the architecture diagram must load, and its API routes must be mounted. Anything missing is listed with the reason.
- **Connection & Self-Test** now includes two checks for these (group "Proof-to-Report Graph").

## What the result means
| Result | Meaning |
|---|---|
| Proven | Every figure ties to its journals, and every journal has verified evidence. |
| Partly proven | Figures tie, but some journals have no evidence, or evidence not yet verified. They are listed. |
| Does not tie | A figure differs from what its journals add up to. Do not rely on the report until explained. |
| Nothing to prove yet | No posted journals in that period. |

## Honest limits
- It proves a figure is **traceable** and **ties to the ledger**. It does not judge whether a document is the *right* document; that is the Evidence Vault's verify step.
- Drafts are never counted. Reversed journals stay in (the books keep history), as in the ledger.
- Very large periods draw only the first 400 journals and say so; such a graph is never marked Proven.
- The architecture check shows the layers load and routes are mounted. It does not run your data; the Self-Test does that.
- Read-only: building the graph never changes the books. It does write the normal "report generated" audit event.

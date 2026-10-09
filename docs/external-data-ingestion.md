# External Data Ingestion

Page: **Data Import** (sidebar). API: `/ingestion/levels`, `/ingestion/preview`, `/ingestion/commit`.

## Safety flow
1. **Preview** reads the file and shows every line, every problem and every check. It writes nothing.
2. **Confirm**: errors block the import; warnings need a tick-box.
3. **Import** re-reads the same file with the same options and refuses unless it still matches the preview (fingerprint).
Nothing is ever posted. Journals arrive as DRAFT; bank lines go into a DRAFT reconciliation; documents and payroll go to the Evidence Vault as UNVERIFIED.

## Levels (honest status)
| Level | What | Status |
|---|---|---|
| 1 | CSV | Working |
| 2 | Excel (.xlsx) | Working (.xls must be re-saved) |
| 3 | Bank statements (CSV/Excel/OFX/QFX/MT940) | Working, with balance and duplicate checks |
| 4 | PDF documents | Partly: PDFs with text only (no OCR) |
| 5 | Receipts/invoices | Partly: vendor, number, dates, totals with confidence and source line |
| 6 | Accounting software | Files only: Xero/QuickBooks/Sage-style chart of accounts and journal exports |
| 7 | Bank APIs | Saved JSON only (Plaid, UK Open Banking); not verified live |
| 8 | Payroll/payment platforms | Saved JSON only (Paystack, Flutterwave, Stripe) and payroll registers; not verified live |

## Conventions
- Money **in** = a ledger debit to cash; money **out** = credit. In a file, a "Debit" column means money out.
- Amounts are never rounded silently (more than 2 decimals is an error).
- Identical lines inside one file are kept and flagged; lines already imported are skipped.

## Permissions
Bank: `reconciliation:import`; documents and payroll: evidence upload; chart of accounts: account manage; journals: journal create. Checked on preview and import.

## Limits
No OCR; PDF statement layouts vary; document reading is rule-based and always needs a human check; no live connections to any bank, accounting product or payment platform; webhook signature checking exists but is not wired to an endpoint; provider payload shapes follow public documentation and are unverified against live accounts; payroll files contain personal pay data; PAYE/pension rates are not checked.

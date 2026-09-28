"""Repository interface and SQLite implementation for the one thing
this module persists: PeriodCloseProcess (the maker-checker workflow
record). CloseReadinessReport is never persisted — it is recomputed
fresh on every call, exactly like every Financial Reporting report."""

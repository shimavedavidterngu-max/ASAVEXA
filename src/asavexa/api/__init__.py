"""FastAPI adapter layer for the Accounting Engine.

Everything under api/ requires `fastapi`, `sqlalchemy` and `pydantic`
(see requirements.txt) and was NOT executed inside the sandbox that
produced this starter codebase (no network access to install
dependencies there). Run the test suite in tests/ — which exercises the
same AccountingEngine against the stdlib SQLite repository — for proof
the underlying logic is correct, then install requirements.txt in your
own environment to run this API layer against PostgreSQL.
"""

"""External data ingestion: files and provider payloads become *staged, checkable* records.

Nothing in this package writes to the books. Parsers are pure functions over bytes; the API layer
decides what a person-confirmed batch is allowed to become (bank lines, evidence, draft journals).
"""

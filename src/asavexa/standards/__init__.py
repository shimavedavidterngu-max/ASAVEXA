"""Standards Configuration Engine.

Organisation -> Entity Type -> Jurisdiction -> Reporting Framework ->
Accounting Policies -> Reporting Requirements.

Pure domain logic: no web framework, no database. The catalog is data
(catalog.py); the engine (engine.py) resolves a configuration from it.
"""

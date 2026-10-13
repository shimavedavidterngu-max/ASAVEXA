-- DESTRUCTIVE. Drops the six tables and every row in them (MFA state, audit-chain links, passport shares, profiles...).
-- The revision's downgrade() refuses to run this unless ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE=1 is set deliberately.
-- Take a verified backup first (docs/stage1-migrations.md).
DROP TABLE IF EXISTS passport_share_sessions;
DROP TABLE IF EXISTS passport_shares;
DROP TABLE IF EXISTS security_docs;
DROP TABLE IF EXISTS organisation_structures;
DROP TABLE IF EXISTS organisation_standards;
DROP TABLE IF EXISTS organisation_profiles;

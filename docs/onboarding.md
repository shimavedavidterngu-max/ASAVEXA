# Sign-up and organisation onboarding (Stage 3)

Status: IMPLEMENTED, TESTED WITH TEST DATA. Not yet verified on the live site.

## The journey
1. Account: register or sign in (existing).
2. Organisation: create one (you become its Owner), pick from the ones you belong to, or see how to join. Eight categories offered.
3. Settings (`/setup`): legal name, kind, country, reporting currency (filled from the server's country list), financial year start month.
4. First period: a suggested financial year, editable.
5. Workspaces: suggestions for the kind of organisation. Only workspaces your role may open are linked.

Progress is shown at every step. Each step saves as it goes; resume works from what the server holds. Existing users are not asked to register again: they see an "Complete the organisation details" item on the dashboard checklist.

## Security
Roles are set only on the server. Nothing chosen in the forms can raise anyone's permissions. A user cannot select an organisation they do not belong to. Read-only members are denied the setup page and the server returns 403.

## Not built (the server has no support)
Invitations, email verification at sign-up, switching workspaces on or off. (Password recovery has since been built: see docs/password-recovery.md. It needs an email provider to be configured.) "Join" tells the person to ask an administrator to add them. The login page now has Forgot password?

## Tests
`frontend/tests/onboarding.test.js` (55), `tests/test_onboarding_journey.py` (6), plus a real-browser pass (65 checks: desktop, phone, dark mode, keyboard, tenant isolation).

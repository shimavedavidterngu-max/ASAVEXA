/**
 * The public landing page: what it says, and when it is shown.
 *
 * Everything here is plain data and pure functions so it can be tested without a browser.
 * Rules this content follows (from the interface spec):
 *  - Only claims the product really backs. No customer logos, testimonials, certifications, performance figures or partnerships.
 *  - No absolute claims such as "100% secure".
 *  - Each capability names the app route that proves it exists; a test checks every route is real.
 *  - Anything not published yet (privacy policy, terms, contact address) is shown as "not published yet", never invented.
 */

/** Paths a signed-out visitor sees the landing page on. Any other signed-out address goes to sign-in, so deep links still work. */
export const LANDING_PATHS = ["/", "/welcome"];

export function isLandingPath(path) {
  const p = String(path || "/").split("?")[0].replace(/\/+$/, "") || "/";
  return LANDING_PATHS.includes(p);
}

/**
 * Which screen a signed-out visitor gets.
 * "landing" until they choose Sign in or Get started, and only on the home address; anything else is sign-in.
 */
export function signedOutScreen({ path, enteredAuth }) {
  if (enteredAuth) return "auth";
  return isLandingPath(path) ? "landing" : "auth";
}

/** Header links. Each jumps to the section with this id on the same page (no route change). */
export const NAV = [
  { id: "product", label: "Product" },
  { id: "solutions", label: "Solutions" },
  { id: "how", label: "How it works" },
  { id: "security", label: "Security" },
  { id: "about", label: "About" },
];

export const HERO = {
  eyebrow: "Financial trust infrastructure",
  headline: "Financial Truth. Backed by Evidence.",
  message: "Connect financial records, supporting evidence, controls and reporting in one traceable workspace.",
  primary: "Get Started",
  secondary: "Explore the Platform",
  tagline: "Don't just report the number. Prove it.",
};

/** What is built today. `route` is the app page that exists for it. */
export const CAPABILITIES = [
  { id: "accounting", title: "Accounting and journals", route: "/accounting",
    text: "Double-entry journals against your own chart of accounts, with periods. Posted journals are never edited: a correction is a reversal, and both stay on record." },
  { id: "evidence", title: "Evidence Vault", route: "/evidence",
    text: "Upload supporting documents, fingerprint them, catch duplicates, and link them to the entries they support. When nothing is linked, the record says MISSING." },
  { id: "reconciliation", title: "Reconciliation", route: "/reconciliation",
    text: "Import bank transactions and match them to the ledger with rules you can read. An unclear match is shown as unclear, never guessed." },
  { id: "close", title: "Period close", route: "/period-close",
    text: "Five named checks before a period is locked: trial balance, unposted journals, reconciliation exceptions, required evidence and period integrity." },
  { id: "reporting", title: "Financial reporting", route: "/reporting",
    text: "Trial balance, income statement, balance sheet and general ledger, computed from the ledger, with every line traceable back to its journals." },
  { id: "controls", title: "Controls and findings", route: "/compliance",
    text: "Built-in controls that test the records, open findings when they fail, and keep fixing and verifying as separate steps done by separate people." },
  { id: "proof", title: "Proof Graph", route: "/proof",
    text: "Follow a figure back through its journal, evidence and approvals, and see exactly which links are missing." },
  { id: "ai", title: "ASAVEXA AI", route: "/ai",
    text: "Rule-based and read-only. It answers only from your organisation's own records, shows its chain of proof, and says so when it cannot. It uses no outside AI model." },
];

/** The eight professional workspaces. */
export const WORKSPACES = [
  { id: "analysis", title: "Financial Analysis", route: "/analysis", text: "Ratios, variance, budgets, cash-flow forecasts and break-even, with reports a second person approves." },
  { id: "tax", title: "Tax Compliance", route: "/tax", text: "A country rules register you fill from official sources, a calculator and a filing calendar. ASAVEXA ships no tax rates." },
  { id: "forensic", title: "Forensic Accounting and Investigation", route: "/forensic", text: "Confidential cases, a tamper-evident chain of custody and read-only fraud-indicator tests. Flags are indicators, never accusations." },
  { id: "grc", title: "Governance, Risk and Compliance", route: "/grc", text: "A risk register on a 5x5 matrix, treatment actions a second person verifies, and a register of compliance obligations." },
  { id: "pubfin", title: "Public Finance", route: "/pubfin", text: "Approved budgets controlled against the ledger, commitments, virements, procurement and grants." },
  { id: "bizdev", title: "Business Development", route: "/bizdev", text: "Accounts, a deal pipeline, proposals whose large discounts a second person approves, and targets with a forecast." },
  { id: "cyber", title: "Cybersecurity", route: "/cyber", text: "Defensive record-keeping: assets, vulnerabilities, incidents and access reviews. It does not scan or monitor any system." },
  { id: "health", title: "Health Centre Administration", route: "/health", text: "Facility budgets, procurement, medical-supply stock, claims totals and staffing costs. Finance and administration only: no patient records." },
];

/** Who it is designed for. Design intent, not a customer list. */
export const ORG_TYPES = [
  "Small and medium businesses", "Non-profits and NGOs", "Schools and colleges", "Government bodies and public finance teams",
  "Health centres and clinics", "Accounting, audit and advisory firms",
];

export const STEPS = [
  { n: 1, title: "Set up or join an organisation", text: "Create your organisation, or join one you are invited to." },
  { n: 2, title: "Open a workspace you are allowed to use", text: "Your role decides what you can see and do." },
  { n: 3, title: "Record the activity", text: "Post financial entries or manage professional work." },
  { n: 4, title: "Attach the evidence", text: "Link the supporting documents to the records." },
  { n: 5, title: "Review, reconcile and approve", text: "Checks and approvals are done by the people permitted to do them." },
  { n: 6, title: "Produce traceable reports", text: "Reports and follow-up actions that trace back to their sources." },
];

/** Security statements, each one a thing the product does today. No guarantees. */
export const TRUST = [
  { title: "Permission-based access", text: "Every action checks the person's role. Roles are separated so that one person cannot do every step alone." },
  { title: "Organisations are kept apart", text: "A record belongs to one organisation. Asking for another organisation's record returns nothing." },
  { title: "An audit trail", text: "Important actions are written to a shared audit trail with who did them and when." },
  { title: "Evidence you can trace", text: "Documents are fingerprinted when stored, so a changed file is detectable." },
  { title: "Second-person approval", text: "Sensitive steps need a different person to approve, in the workspaces that handle them." },
  { title: "Sign-in protection", text: "Long passwords are required, and organisations can ask for two-step sign-in." },
];

/** What ASAVEXA says plainly about its own status. */
export const STATUS = {
  title: "Where ASAVEXA stands today",
  lines: [
    "The platform has been built and tested with synthetic data.",
    "It has not yet been independently audited, penetration-tested or certified.",
    "The workspaces have not yet been reviewed by licensed tax, audit, legal or health-sector professionals.",
    "It supports professional judgement. It does not replace it, and it makes no claim of legal or regulatory compliance.",
  ],
};

export const ABOUT = {
  title: "About ASAVEXA",
  text: "ASAVEXA is built on one idea: AI may suggest; evidence must prove. Every number should be able to show where it came from, who approved it, and what is still missing.",
};

/** Footer. Items that are not published yet say so; nothing here is invented. */
export const FOOTER = {
  product: [{ id: "product", label: "Product" }, { id: "solutions", label: "Solutions" }, { id: "how", label: "How it works" }, { id: "security", label: "Security" }],
  notPublished: [
    { label: "Privacy policy", note: "not published yet" },
    { label: "Terms of use", note: "not published yet" },
    { label: "Contact address", note: "to be added by the ASAVEXA team" },
  ],
  disclosure: "ASAVEXA provides software. It does not give legal, tax, audit or medical advice.",
};

/** Words the page must never use (checked by a test). Substantiated claims only. */
export const FORBIDDEN_CLAIMS = [
  /100\s*%/i, /\bguarantee/i, /\bunhackable\b/i, /\bbank-grade\b/i, /\bmilitary/i, /\bcertified\b(?!\.)/i,
  /\bISO\s*\d/i, /\bSOC\s*2/i, /\bGDPR[- ]compliant/i, /\btrusted by\b/i, /\btestimonial/i, /\bcustomers? love/i,
];

/** All visible copy as one string, for the claims test. */
export function allCopy() {
  const parts = [HERO.eyebrow, HERO.headline, HERO.message, HERO.primary, HERO.secondary, HERO.tagline, ABOUT.title, ABOUT.text, STATUS.title, FOOTER.disclosure];
  CAPABILITIES.forEach((c) => parts.push(c.title, c.text));
  WORKSPACES.forEach((c) => parts.push(c.title, c.text));
  ORG_TYPES.forEach((t) => parts.push(t));
  STEPS.forEach((s) => parts.push(s.title, s.text));
  TRUST.forEach((t) => parts.push(t.title, t.text));
  STATUS.lines.forEach((l) => parts.push(l));
  NAV.forEach((n) => parts.push(n.label));
  FOOTER.notPublished.forEach((n) => parts.push(n.label, n.note));
  return parts.join("\n");
}

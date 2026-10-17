/**
 * Which sector the signed-in organisation belongs to, for the one thing sectors change in the shell: the accent colour pair (data-sector).
 * Colour is only a "where am I" cue. It never carries meaning, and it never changes what a person can see or do (that is role and the server).
 * The sector comes from the organisation's saved type (entity configuration). Unknown, unconfigured or not-yet-loaded gives null: no accent, no label.
 */
export const SECTOR_OF_TYPE = {
  INDIVIDUAL: "accounting", BUSINESS: "accounting", PROFESSIONAL_FIRM: "accounting", ASSURANCE_PROVIDER: "accounting", INDUSTRY: "accounting", FINANCIAL: "accounting", FUNDER: "accounting",
  GOVERNMENT: "government", ESSENTIAL_SERVICES: "government",
  NONPROFIT: "ngo", FAITH: "church", EDUCATION: "school", HEALTH: "health",
};
export const SECTOR_LABEL = {
  accounting: "Accounting and business", government: "Government and public bodies", ngo: "Nonprofit", church: "Faith-based", school: "Education", university: "Education", health: "Health and care",
};
/** Colleges and universities get their own accent inside the education type. */
const UNIVERSITY_SUBTYPES = ["COLLEGE"];

/** `cfg` is the server's entity configuration for the organisation (or null). Returns { id, label } or null. */
export function sectorOf(cfg) {
  if (!cfg || !cfg.configured || typeof cfg.entity_type !== "string") return null;
  let id = SECTOR_OF_TYPE[cfg.entity_type];
  if (!id) return null;
  if (id === "school" && UNIVERSITY_SUBTYPES.includes(cfg.subtype)) id = "university";
  return { id, label: SECTOR_LABEL[id] };
}

# Stage 6: Procurement Trace (first specialist workspace)

Status: VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.

## What changed
- New "Trace an order" tab in Procurement, and a "Trace this order" button on every order. For one purchase order it shows the whole chain: supplier, contract, purchase order and approvals, delivery, invoice (three-way match), payment record, supplier review. A statement (exact total, ordered / received / invoiced / still to come, invoices with the server's flags, deliveries) sits beside the Proof Rail for that order (procurement accent).
- It only restates what the server recorded. It adds, compares and recalculates nothing; a test bans arithmetic in the trace code. A step it could not look up says "Not checked"; a gap says so in words and in shape (hollow dashed). An order with no contract is never called complete.
- Each step says what it means: a delivery is recorded by a person and ASAVEXA has not confirmed anything arrived; a payment is a record and ASAVEXA did not make it; a review is a person's judgement.
- The trace is a read view: it has no approve, reject or pay buttons. Existing approval rules (two-person rule, approvers differ from creators) are untouched.
- Proof Rail: a step can now carry its own words (for example "Suspended") while the shape still shows the coarse state.

## Measured here
- Frontend suite 1430/1430 (16 new Procurement Trace tests).
- New real-backend browser journey (supplier, order, approval, delivery, invoice, payment, review built by different people): all checks pass, including phone width (no sideways overflow) and no browser errors.
- The existing Procurement journey still passes with the new tab.

## Not checked
Real devices, screen readers, other browsers, performance, the live site. The trace shows ids for people (as the existing Procurement page does) rather than names. A full re-run of every journey on this code had not finished at the time of writing.

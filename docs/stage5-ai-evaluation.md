# Stage 5 and Stage 14: AI evaluation harness

Status: **VERIFIED IN TEST ENVIRONMENT** (14 tests). The assistant is still rule-based; no outside model is used. This measures it.

- `src/asavexa/ai/evaluation.py`: precision and recall per detection rule against labels a person wrote in advance; checks that answers are grounded (every item passes the grounding contract), that unanswerable questions are refused, and that the same question gives the same fingerprint.
- `scripts/ai_eval.py`: `PYTHONPATH=src:tests python3 scripts/ai_eval.py` prints the report; exit code 1 if the criteria are not met.
- Criteria (changeable): precision and recall at least 0.9, at least 2 labelled cases per rule, all answers grounded, all refusals correct, all answers stable.
- A rule with too few labels does not pass. Rules with no labels are listed as unmeasured, not ignored.

## Result on the built-in sample (after Stage 14)
All 17 rules now have labelled cases, and all meet the targets on this sample (precision 1.0, recall 1.0, 2 to 5 labelled cases each). Stage 5 measured 8 of 17; Stage 14 added labelled cases for the other nine: BACKDATED_POSTING, BANK_AMOUNT_OUTLIER, BANK_LINE_NEEDS_REVIEW, BANK_LINE_REJECTED, BANK_LINE_UNMATCHED, FUTURE_DATED, PERIOD_MISMATCH, REVERSAL, WEEKEND_DATE.

How the Stage 14 cases were made: `tests/test_ai_evaluation.py::build_sample` plants them on purpose (a journal posted 60 days late, a date moved outside its period, a bank line left unmatched, two bank lines rejected, one 9,000,000 bank line among lines of about 12,000, and so on). `new_labels` says what each rule SHOULD do, written from how each case was built, not from what the engine printed. One of my own construction mistakes was found and fixed on the way (a bank line dated too far from its candidate entries, so it was unmatched instead of left for review): the label was right and the sample was wrong.

A defect in the measuring tool was fixed too: a matched bank line carries its journal as a source, and the harness used to credit the bank line's flags to that journal. Bank lines are now identified by their own id, and a test pins this.

## What this does NOT show
- The sample is small and was built by us. A perfect score here is not an accuracy claim about any organisation's books.
- WEEKEND_DATE and REVERSAL (and the other rules that cannot flag alone) only appear beside another signal, so they are labelled on journals that also carry one. A weekend journal with no other signal is never shown by the assistant, by design.
- Before any accuracy claim: label real (consented, anonymised) cases and have someone independent write the labels.

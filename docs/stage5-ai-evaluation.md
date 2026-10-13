# Stage 5: AI evaluation harness

Status: **VERIFIED IN TEST ENVIRONMENT** (10 tests). The assistant is still rule-based; no outside model is used. This stage adds the way to measure it.

- `src/asavexa/ai/evaluation.py`: precision and recall per detection rule against labels a person wrote in advance; checks that answers are grounded (every item passes the grounding contract), that unanswerable questions are refused, and that the same question gives the same fingerprint.
- `scripts/ai_eval.py`: `PYTHONPATH=src:tests python3 scripts/ai_eval.py` prints the report; exit code 1 if the criteria are not met.
- Criteria (changeable): precision and recall at least 0.9, at least 2 labelled cases per rule, all answers grounded, all refusals correct, all answers stable.
- A rule with too few labels does not pass. Rules with no labels are listed as unmeasured, not ignored.

## Result on the built-in sample
8 of 17 rules have labelled cases and all meet the targets (precision 1.0, recall 1.0). **9 rules are unmeasured**: BACKDATED_POSTING, BANK_AMOUNT_OUTLIER, BANK_LINE_NEEDS_REVIEW, BANK_LINE_REJECTED, BANK_LINE_UNMATCHED, FUTURE_DATED, PERIOD_MISMATCH, REVERSAL, WEEKEND_DATE.

## What this does NOT show
The sample is small and was built by us. A perfect score here is not an accuracy claim about any organisation's books. Before any accuracy claim: label real (consented, anonymised) cases, cover the unmeasured rules, and have someone independent write the labels.

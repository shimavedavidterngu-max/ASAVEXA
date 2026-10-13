# AI strategy decision (Stage 1): stay rule-based

**Decision (2026-10-12, owner):** the AI stays rule-based for now. Priorities: deterministic calculations, explicit business rules, evidence traceability, permissions, reproducible outputs.

- Today's engine (`src/asavexa/ai/engine.py`) uses **no outside model**. It says so in every answer (`disclosure`). Same records in, same answer out (fingerprint).
- `src/asavexa/ai/provider.py` fixes the *shape* a future provider must have (`AnswerProvider`) and the acceptance check every answer must pass (`check_answer`: full evidence chain, grounded, fingerprint, disclosure, review required when not high confidence; an honest refusal is allowed only if it asserts nothing).
- `select_provider()` returns only the rule-based provider. Asking for any other raises `ProviderNotApprovedError`, which lists the gate. **No outside model is integrated, and none can be selected.**

## Gate before any outside model is connected (all five, recorded)
1. A validated use case that rules cannot serve.
2. A security assessment (data sent out, prompt injection, tenant separation, logging, provider terms).
3. A cost analysis with a monthly ceiling.
4. Human oversight: who reviews, what they can override, how it is recorded.
5. Measurable acceptance criteria on held-out cases (accuracy, refusal behaviour, grounding rate) that the provider meets.

Tests: `tests/test_ai_provider_seam.py`.

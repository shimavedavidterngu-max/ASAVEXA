"""The seam where an outside AI model could be attached LATER. Nothing is attached today.

ASAVEXA's AI is rule-based (engine.py): deterministic, no outside model, no data leaves the platform. Stage 1 decision:
it stays that way. This file only fixes the shape a future provider must have, and the gate it must pass, so that adding
one later cannot quietly bypass the grounding contract or the review rules.

Rules any provider must obey (enforced by `check_answer`, for rule-based answers too):
  * every item carries the whole chain (grounding.validate_item): conclusion, source records, evidence, journal, treatment,
    framework, confidence, human review;
  * the answer says it was grounded and carries a fingerprint and a disclosure of how it was produced;
  * an answer that is not high confidence must require human review.
`select_provider` will not return anything other than the rule-based provider until the written gate below is met and a
provider implementation exists; asking for one raises ProviderNotApprovedError naming what is missing."""
from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from .engine import AiEngine
from .errors import AsavexaAiError
from .grounding import UngroundedAnswerError, validate_item

MODES = ("explain", "detect", "recommend", "prove", "ask")

# Everything below must be true, and recorded, before any outside model is connected.
EXTERNAL_MODEL_GATE = (
    "a validated use case that rules cannot serve",
    "a security assessment (data sent out, prompt injection, tenant separation, logging, provider terms)",
    "a cost analysis with a monthly ceiling",
    "human oversight: who reviews, what they can override, how it is recorded",
    "measurable acceptance criteria on held-out cases (accuracy, refusal behaviour, grounding rate) that the provider meets",
)


class ProviderNotApprovedError(AsavexaAiError):
    pass


@runtime_checkable
class AnswerProvider(Protocol):
    name: str
    uses_external_model: bool

    def answer(self, mode: str, **params: Any) -> Dict[str, Any]: ...


class RuleBasedProvider:
    """Today's provider: the deterministic AiEngine. Same answers as before; this only gives them a common entry point."""
    name = "rule_based"
    uses_external_model = False

    def __init__(self, engine: AiEngine):
        self.engine = engine

    def answer(self, mode: str, **params: Any) -> Dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        return check_answer(getattr(self.engine, mode)(**params))


def check_answer(result: Dict[str, Any]) -> Dict[str, Any]:
    """The acceptance check every provider's output must pass before it is returned to anyone."""
    for key in ("grounded", "fingerprint", "disclosure"):
        if key not in result:
            raise UngroundedAnswerError(f"answer is missing {key!r}")
    if result["grounded"] is not True:
        # An honest refusal ("I cannot answer that from your records") is allowed. It must assert nothing: no items, and a stated refusal.
        if result.get("items") or not result.get("refusal"):
            raise UngroundedAnswerError("an answer that is not grounded must be a plain refusal with no items")
        return result
    for item in result.get("items") or []:
        validate_item(item)
    return result


def select_provider(name: str, engine: AiEngine) -> AnswerProvider:
    if name == "rule_based":
        return RuleBasedProvider(engine)
    raise ProviderNotApprovedError(
        f"No provider named {name!r} is approved. ASAVEXA's AI is rule-based. Before an outside model is connected, all of these "
        "must be met and recorded: " + "; ".join(EXTERNAL_MODEL_GATE) + ".")

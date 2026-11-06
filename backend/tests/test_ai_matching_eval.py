"""DeepEval evaluation of retailer-specific product understanding, end to end: real API,
real database history (earlier AI orders and Order Desk corrections), LangGraph pipeline.

OpenAI is faked at the HTTP layer with a deliberately *neutral* reading: it always proposes
both glucose biscuit packs with the same middling confidence, so the expected answers can only
come from the retailer evidence. A deterministic DeepEval metric checks the outcome (the SKU
chosen, or CLARIFY when the line must be confirmed). Runs offline: no DeepEval cloud, no LLM judge.
"""

from decimal import Decimal

import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
from sqlalchemy import update

from app.models import CreditAccount
from app.modules.ai_orders import service as ai_orders
from app.modules.ai_orders.schemas import ConfirmExtractionInput, ConfirmedItemInput, ExtractedItemInput, RecordExtractionInput
from app.modules.orders import service as orders
from app.modules.orders.schemas import CorrectOrderItemInput
from seed.run_seed import seed_id
from tests.conftest import seed_user
from tests.test_ai_orders_api import as_user, line, openai  # noqa: F401  (fixtures)

BS075, BS150 = seed_id("product", "SKU-BS-075"), seed_id("product", "SKU-BS-150")
CLARIFY = "CLARIFY"
# Who captures orders for each shop: the retailer's own login, or the assigned salesman.
CAPTURED_BY = {"sharma": "retailer_sharma", "gupta": "retailer_gupta", "jain": "salesman_sunil", "patel": "salesman_deepak"}


def capture(as_user, retailer, message):
    body = {"message": message}
    if CAPTURED_BY[retailer].startswith("salesman"):
        body["retailer_id"] = str(seed_id("retailer", retailer))
    response = as_user(CAPTURED_BY[retailer], "POST", "/ai-orders/extract", json=body)
    assert response.status_code == 200, response.json()
    return response.json()["data"]


class OutcomeMatch(BaseMetric):
    """1.0 when the pipeline chose the expected SKU (or asked for clarification when expected)."""

    threshold = 1.0

    def __init__(self):
        self.score, self.success, self.reason = 0.0, False, None
        self.async_mode, self.strict_mode, self.include_reason, self.evaluation_model = False, True, True, None

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        self.score = 1.0 if test_case.actual_output == test_case.expected_output else 0.0
        self.success = self.score >= self.threshold
        self.reason = f"got {test_case.actual_output}, expected {test_case.expected_output}"
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Retailer-specific SKU match"


@pytest.fixture
def history(tx):
    """Earlier AI orders of each retailer: (retailer, words) -> what they became."""
    tx.execute(update(CreditAccount).values(credit_limit=Decimal("10000000")))
    tx.commit()

    def past(retailer_key, words, product, corrected_to=None):
        user = seed_user(tx, CAPTURED_BY[retailer_key])
        extraction = ai_orders.record_extraction(tx, user, RecordExtractionInput(
            retailer_id=seed_id("retailer", retailer_key), original_message=f"1 peti {words}", items=[ExtractedItemInput(
                original_text=f"1 peti {words}", extracted_name=words, quantity=Decimal(1), unit="case",
                matched_product_id=product, confidence=Decimal("0.8"))]))
        order = ai_orders.confirm_extraction(tx, user, extraction.id, ConfirmExtractionInput(items=[ConfirmedItemInput(
            extraction_item_id=extraction.items[0].id, product_id=product, quantity=Decimal(1), unit="case")]))
        if corrected_to is not None:  # the order desk fixes the AI's mapping
            orders.correct_order_item(tx, seed_user(tx, "order_desk"), order.id, order.items[0].id,
                                      CorrectOrderItemInput(new_product_id=corrected_to, reason="Retailer meant the other pack"))

    # R1 (Sharma): "chhota biscuit" has meant the 75 g pack.
    past("sharma", "chhota biscuit", BS075)
    past("sharma", "biscuit chhota", BS075)
    # R2 (Gupta): the same words have meant the 150 g pack.
    past("gupta", "chhota biscuit", BS150)
    past("gupta", "chhota biscuit", BS150)
    # Conflicting history (Jain): the same words for both packs.
    past("jain", "chhota biscuit", BS075)
    past("jain", "chhota biscuit", BS150)
    # Wrong earlier mapping corrected by the order desk (Patel): 150 g -> 75 g.
    past("patel", "chhota biscuit", BS150, corrected_to=BS075)
    return past


def neutral(text, qty=5, unit="case", skus=("SKU-BS-075", "SKU-BS-150"), conf=0.6, desc="glucose biscuit"):
    """What a model reading the words alone would say: either pack, not sure."""
    return [line(text, desc, qty, unit, list(skus), conf)]


CASES = [
    # (name, retailer, message, fake extraction, fake comparison answers, expected)
    ("R1 phrase means 75g", "sharma", "5 peti chhota biscuit", neutral("5 peti chhota biscuit"), [], "SKU-BS-075"),
    ("R2 same phrase means 150g", "gupta", "5 peti chhota biscuit", neutral("5 peti chhota biscuit"), [], "SKU-BS-150"),
    ("R1 reworded phrase", "sharma", "bhaiya 5 peti chhota packet biscuit bhej do",
     neutral("5 peti chhota packet biscuit"), [], "SKU-BS-075"),
    ("conflicting history", "jain", "5 peti chhota biscuit", neutral("5 peti chhota biscuit"), [], CLARIFY),
    ("order desk correction learned", "patel", "5 peti chhota biscuit", neutral("5 peti chhota biscuit"), [], "SKU-BS-075"),
    ("unknown phrase", "sharma", "2 peti xyz tikki masala",
     neutral("2 peti xyz tikki masala", qty=2, skus=(), conf=0.0, desc="xyz tikki masala"), [], CLARIFY),
    ("low confidence, no history", "gupta", "3 peti cream wala",
     neutral("3 peti cream wala", qty=3, skus=("SKU-CB-100",), conf=0.4, desc="cream"), [], CLARIFY),
    ("multiple candidates, LLM unsure", "sharma", "2 peti glucose",
     neutral("2 peti glucose", qty=2, conf=0.7), [{"line": 0, "sku": None, "confidence": 0.4,
                                                     "needs_clarification": True, "reason": "Both packs fit"}], CLARIFY),
    ("missing unit", "sharma", "chhota biscuit 5", neutral("chhota biscuit 5", unit=None), [], CLARIFY),
    ("explicit pack beats history", "sharma", "5 peti glucose biscuit 150",
     neutral("5 peti glucose biscuit 150", skus=("SKU-BS-150", "SKU-BS-075"), conf=0.9), [], "SKU-BS-150"),
]


@pytest.mark.parametrize("name,retailer,message,lines,matches,expected", CASES, ids=[c[0] for c in CASES])
def test_retailer_specific_understanding(as_user, openai, history, name, retailer, message, lines, matches, expected):
    openai.lines, openai.matches = lines, matches
    [item] = capture(as_user, retailer, message)["items"]
    actual = CLARIFY if item["requires_clarification"] else item["product"]["sku"]
    assert_test(LLMTestCase(input=f"[{retailer}] {message}", actual_output=actual, expected_output=expected,
                            context=item["evidence"]), [OutcomeMatch()], run_async=False)
    # Whatever the outcome, the evidence is business facts, and alternatives are real products.
    assert all(isinstance(e, str) and e for e in item["evidence"])
    assert all(a["sku"].startswith("SKU-") for a in item["alternatives"])


def test_correction_is_used_as_evidence_and_saved_as_retailer_wording(as_user, openai, history):
    openai.lines = neutral("5 peti chhota biscuit")
    [item] = capture(as_user, "patel", "5 peti chhota biscuit")["items"]
    assert item["product"]["sku"] == "SKU-BS-075" and Decimal(item["confidence"]) >= Decimal("0.95")
    assert any("saved wording" in e for e in item["evidence"])
    assert any("order desk corrected" in e for e in item["evidence"])


def test_comparison_gets_candidates_with_retailer_evidence_and_no_prices(as_user, openai, history):
    openai.lines = neutral("2 peti glucose", qty=2, conf=0.7)
    openai.matches = [{"line": 0, "sku": "SKU-BS-150", "confidence": 0.8, "needs_clarification": False,
                       "reason": "Closest match by name"}]
    [item] = capture(as_user, "sharma", "2 peti glucose")["items"]
    [request] = openai.comparison_requests
    content = request["messages"][1]["content"]
    assert "SKU-BS-075" in content and "SKU-BS-150" in content and "evidence" in content
    assert "8.10" not in content and "dealer" not in content.lower()
    assert item["product"]["sku"] == "SKU-BS-150"
    assert "AI comparison: Closest match by name" in item["evidence"]

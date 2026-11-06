"""Retailer-specific product matching (app/modules/ai_orders/matcher.py), without a database
or an LLM: the same words can mean different products for different retailers."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.ai_orders.llm import ExtractedLine
from app.modules.ai_orders.matcher import (
    CatalogueProduct,
    PastLine,
    RetailerContext,
    decide,
    find_candidates,
    needs_llm_comparison,
    same_words,
    wording_for_alias,
)


def product(sku, name, pack, brand="Sunrise Foods", category="Biscuits"):
    return CatalogueProduct(uuid.uuid5(uuid.NAMESPACE_URL, sku), sku, name, brand, pack, "case", category)


BS075 = product("SKU-BS-075", "Glucose Biscuit 75g", "75g")
BS050 = product("SKU-BS-050", "Glucose Biscuit 50g", "50g")
MR075 = product("SKU-MR-075", "Marie Biscuit 75g", "75g", brand="Crispo")
DT1KG = product("SKU-DT-1KG", "Detergent Powder 1kg", "1kg", brand="Dhavala", category="Home Care")
CATALOGUE = [BS075, BS050, MR075, DT1KG]
NOW = datetime.now(UTC)


def line(text, qty=Decimal(5), unit="case", skus=("SKU-BS-075", "SKU-BS-050"), conf=0.6, desc="glucose biscuit"):
    return ExtractedLine(text, desc, qty, unit, tuple(skus), conf)


def history(*entries):
    """entries: (wording, product, corrected?) newest first."""
    return [PastLine(w, p.id, c, NOW - timedelta(days=i)) for i, (w, p, c) in enumerate(entries)]


def match(text, ctx, **kw):
    return decide(find_candidates(line(text, **kw), CATALOGUE, ctx))


def test_retailer_wording_strips_quantity_unit_and_filler():
    assert wording_for_alias("bhaiya 5 peti chhota packet biscuit", Decimal(5)) == "chhota biscuit"
    assert wording_for_alias("chai patti 250 wala 1 peti", Decimal(1)) == "chai patti 250 wala"


def test_same_words_ignores_order_but_not_generic_single_words():
    assert same_words("chhota biscuit", "biscuit chhota")
    assert same_words("chhota biscuit", "chota biscuit")  # spelling
    assert not same_words("biscuit", "chhota biscuit")  # a generic word is not the same phrase


def test_same_phrase_means_different_products_for_different_retailers():
    r1 = RetailerContext(past_lines=history(("chhota biscuit", BS075, False), ("chhota biscuit", BS075, False),
                                            ("biscuit chhota", BS075, False)), frequency={BS075.id: 18, BS050.id: 2})
    r2 = RetailerContext(past_lines=history(("chhota biscuit", BS050, False), ("chhota biscuit", BS050, False)))
    m1 = match("5 peti chhota packet biscuit", r1)
    m2 = match("5 peti chhota packet biscuit", r2)
    assert m1.product == BS075 and m2.product == BS050
    assert m1.confidence >= 0.9 and m1.clarification is None
    assert any("used “chhota biscuit” for this product 3 times" in e for e in m1.evidence)
    assert any("Ordered 18 times" in e for e in m1.evidence)
    assert {a["sku"] for a in m1.alternatives} >= {"SKU-BS-050"}


def test_no_global_meaning_for_size_words():
    # Without retailer evidence "chhota" does not decide the pack: the AI's uncertain
    # reading stays uncertain and the line needs confirmation.
    m = match("5 peti chhota biscuit", RetailerContext())
    assert m.clarification == "Not sure about this product. Please confirm it or pick another."
    assert m.confidence < 0.75


def test_conflicting_history_asks_instead_of_guessing():
    ctx = RetailerContext(past_lines=history(("chhota biscuit", BS075, False), ("chhota biscuit", BS050, False)))
    m = match("5 peti chhota biscuit", ctx)
    assert m.clarification.startswith("This retailer has used these words for different products")
    assert m.confidence <= 0.6
    assert any("different products" in e for e in m.evidence)


def test_latest_order_desk_correction_resolves_a_wrong_earlier_mapping():
    # The AI once mapped "chhota biscuit" to 50g; the order desk corrected the latest one to 75g.
    ctx = RetailerContext(past_lines=history(("chhota biscuit", BS075, True), ("chhota biscuit", BS050, False)))
    m = match("5 peti chhota biscuit", ctx)
    assert m.product == BS075 and m.clarification is None
    assert any("order desk corrected" in e for e in m.evidence)


def test_saved_wording_is_strongest_evidence():
    ctx = RetailerContext(aliases={"chhota biscuit": BS050.id})
    m = match("5 peti chhota biscuit", ctx, skus=("SKU-BS-075",), conf=0.9)
    assert m.product == BS050 and m.confidence >= 0.97


def test_explicit_pack_size_beats_a_partial_saved_wording():
    ctx = RetailerContext(aliases={"biscuit": BS075.id})
    m = match("5 peti glucose biscuit 50", ctx, skus=("SKU-BS-050",), conf=0.9)
    assert m.product == BS050
    assert any("Pack size 50g matches" in e for e in m.evidence)


def test_missing_unit_or_quantity_is_never_assumed():
    ctx = RetailerContext(past_lines=history(("biscuit", BS075, False), ("biscuit", BS075, False)))
    no_unit = match("biscuit 5", ctx, unit=None)
    assert no_unit.unit is None and no_unit.clarification == "Unit not mentioned. Is it cases?"
    no_qty = match("thoda biscuit bhejo", ctx, qty=None, unit=None)
    assert no_qty.clarification == "Quantity not mentioned."


def test_pieces_are_not_converted_to_cases():
    m = match("20 packet glucose biscuit 75g", RetailerContext(), unit="piece", skus=("SKU-BS-075",), conf=0.95)
    assert m.unit == "piece" and "ordered in cases" in m.clarification


def test_unknown_sku_from_the_llm_is_ignored_and_unknown_words_are_not_matched():
    m = match("2 peti xyz tikki masala", RetailerContext(), skus=("SKU-FAKE-1",), conf=0.99, desc="xyz tikki")
    assert m.product is None and m.clarification.startswith("Product not recognised")


def test_close_calls_go_to_the_llm_and_its_choice_must_be_a_candidate():
    lc = find_candidates(line("2 peti glucose biscuit", qty=Decimal(2), conf=0.7), CATALOGUE, RetailerContext())
    assert needs_llm_comparison(lc)
    chosen = decide(lc, {"sku": "SKU-BS-050", "confidence": 0.82, "needs_clarification": False,
                         "reason": "Retailer usually orders the 50g pack"})
    assert chosen.product == BS050 and chosen.confidence == 0.82
    assert "AI comparison: Retailer usually orders the 50g pack" in chosen.evidence
    invented = decide(lc, {"sku": "SKU-NOPE", "confidence": 1, "needs_clarification": False, "reason": "x"})
    assert invented.product == lc.candidates[0].product  # an SKU outside the candidates is ignored
    unsure = decide(lc, {"sku": "SKU-BS-050", "confidence": 0.9, "needs_clarification": True, "reason": "both fit"})
    assert unsure.clarification.startswith("Not sure")


def test_decisive_retailer_evidence_does_not_need_the_llm():
    ctx = RetailerContext(past_lines=history(("glucose biscuit", BS075, False), ("glucose biscuit", BS075, False)))
    assert not needs_llm_comparison(find_candidates(line("2 peti glucose biscuit", qty=Decimal(2), conf=0.7), CATALOGUE, ctx))

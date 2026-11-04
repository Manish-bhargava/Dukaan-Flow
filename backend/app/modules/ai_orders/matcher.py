"""Deterministic product matching for AI-extracted lines (the LLM's suggestions are checked,
never trusted). Order of evidence:

1. The retailer's own saved wording (retailer_aliases), learned from earlier corrections,
   when it is exactly the line's product wording ("biscuit chhota"). An alias that is only
   part of the line ("washing powder" in "washing powder 1 kilo") does not override the more
   specific text; it only supports a candidate and is offered as an alternative.
2. The LLM's candidate SKUs, accepted only if they exist in this retailer's catalogue.
3. RapidFuzz similarity between the line and product names, for alternatives and as a
   fallback when the LLM proposed nothing usable.

A line needs clarification when the product is not found or not confident, when the
quantity or unit is missing, or when the unit is not the product's order unit (e.g. pieces
for a product ordered in cases); the system never converts or guesses.
"""

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz, process

from app.modules.ai_orders.llm import ExtractedLine
from app.modules.ai_orders.schemas import ExtractedItemInput
from app.utils.text import normalize_text

CONFIDENT = 0.75  # below this the retailer must confirm the product
ALIAS_CONFIDENCE = Decimal("0.970")
RECENT_BONUS = 0.05
FUZZY_FALLBACK_MIN = 80  # fuzzy-only match needs this score and a clear lead
FUZZY_ALTERNATIVE_MIN = 50
MAX_ALTERNATIVES = 3

# Words that are not part of a product's name, removed when saving the retailer's wording.
_NOISE = {
    "peti", "petti", "pethi", "carton", "cartons", "case", "cases", "cs", "box",
    "piece", "pieces", "pcs", "pc", "packet", "packets", "pkt", "nag",
    "bhaiya", "bhai", "bhej", "bhejo", "dena", "do", "aur", "and", "please", "pls", "ji",
}


@dataclass(frozen=True)
class CatalogueProduct:
    id: uuid.UUID
    sku: str
    name: str
    brand: str
    pack_size: str
    order_unit: str

    @property
    def label(self) -> str:
        return f"{self.name} {self.pack_size} {self.brand}"


def wording_for_alias(original_text: str, quantity: Decimal | None) -> str:
    """The retailer's words for the product: the line without quantity, unit and filler words
    ("5 peti biscuit chhota" -> "biscuit chhota"; "chai patti 250 wala 1 peti" -> "chai patti 250 wala")."""
    tokens = normalize_text(original_text).split()
    if quantity is not None:
        qty = f"{quantity.normalize():f}"
        for i, token in enumerate(tokens):
            if token == qty:
                del tokens[i]
                break
    return " ".join(t for t in tokens if t not in _NOISE)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and re.search(rf"(?<!\S){re.escape(phrase)}(?!\S)", text) is not None


def _confidence(value: float) -> Decimal:
    return Decimal(str(round(min(max(value, 0.0), 1.0), 3)))


def match_line(
    line: ExtractedLine,
    catalogue: list[CatalogueProduct],
    aliases: dict[str, uuid.UUID],  # normalized alias -> product id (this retailer only)
    recent_product_ids: set[uuid.UUID],
) -> ExtractedItemInput:
    by_id = {p.id: p for p in catalogue}
    by_sku = {p.sku.casefold(): p for p in catalogue}
    text = normalize_text(line.original_text)
    description = normalize_text(line.product_description)

    scores: dict[uuid.UUID, float] = {}
    if catalogue:
        for _, score, product_id in process.extract(
            description or text, {p.id: normalize_text(p.label) for p in catalogue},
            scorer=fuzz.token_set_ratio, limit=5,
        ):
            scores[product_id] = score
    fuzzy_ranked = sorted(scores, key=scores.get, reverse=True)

    llm_candidates: list[CatalogueProduct] = []
    for sku in line.candidate_skus:
        product = by_sku.get(sku.casefold())
        if product is not None and product not in llm_candidates:
            llm_candidates.append(product)

    matched: CatalogueProduct | None = None
    confidence = 0.0
    wording = wording_for_alias(line.original_text, line.quantity)
    exact_alias = aliases.get(wording) if wording else None
    partial_alias_ids = [pid for alias, pid in sorted(aliases.items(), key=lambda a: -len(a[0]))
                         if pid in by_id and pid != exact_alias and _contains_phrase(text, alias)]
    if exact_alias in by_id:
        matched = by_id[exact_alias]
        confidence = float(ALIAS_CONFIDENCE)
    elif llm_candidates:
        matched = llm_candidates[0]
        confidence = line.confidence
    elif fuzzy_ranked:
        top = scores[fuzzy_ranked[0]]
        runner_up = scores[fuzzy_ranked[1]] if len(fuzzy_ranked) > 1 else 0
        if top >= FUZZY_FALLBACK_MIN and top - runner_up >= 10:
            matched = by_id[fuzzy_ranked[0]]
            confidence = top / 100 * 0.9
    if matched is not None and matched.id in recent_product_ids:
        confidence += RECENT_BONUS
    if matched is not None and matched.id in partial_alias_ids:
        confidence += RECENT_BONUS

    alternatives = []
    for product in (llm_candidates[1:] + [by_id[pid] for pid in partial_alias_ids]
                    + [by_id[pid] for pid in fuzzy_ranked if scores[pid] >= FUZZY_ALTERNATIVE_MIN]):
        if product is matched or any(a["product_id"] == str(product.id) for a in alternatives):
            continue
        alternatives.append({
            "product_id": str(product.id), "sku": product.sku, "name": product.name,
            "pack_size": product.pack_size, "confidence": round(scores.get(product.id, 0) / 100, 2),
        })
        if len(alternatives) == MAX_ALTERNATIVES:
            break

    unit = line.unit
    if unit == "case" and matched is not None:
        unit = matched.order_unit
    requires_clarification = (
        matched is None
        or confidence < CONFIDENT
        or line.quantity is None
        or unit is None
        or unit != matched.order_unit
    )
    return ExtractedItemInput(
        original_text=line.original_text,
        extracted_name=line.product_description or line.original_text[:200],
        quantity=line.quantity,
        unit=unit,
        matched_product_id=matched.id if matched else None,
        confidence=_confidence(confidence),
        alternatives=alternatives or None,
        requires_clarification=requires_clarification,
    )


def clarification_reason(item, matched_order_unit: str | None) -> str | None:
    """Why a stored extraction item needs the retailer's input (None if it does not)."""
    if item.matched_product_id is None:
        return "Product not recognised. Please choose it from the list."
    if item.quantity is None:
        return "Quantity not mentioned."
    if item.unit is None:
        return f"Unit not mentioned. Is it {matched_order_unit or 'case'}s?"
    if matched_order_unit and item.unit != matched_order_unit:
        return f"This product is ordered in {matched_order_unit}s; the message says {item.unit}s."
    if item.requires_clarification or item.confidence < Decimal(str(CONFIDENT)):
        return "Not sure about this product. Please confirm it or pick another."
    return None

"""Retailer-specific product matching for AI-extracted lines. Deterministic and testable; the
LLM's suggestions are checked against the retailer's catalogue, never trusted.

For one line ("5 peti chhota packet biscuit") the retailer's words ("chhota biscuit") are
compared with evidence about THIS retailer:

  retailer wording   the retailer's saved alias for exactly these words (learned when the
                     retailer or the Order Desk corrected a match): strongest
  past AI lines      what earlier AI lines with the same / very similar words finally became
                     (the order line's product, including Order Desk corrections)
  frequency          how often the retailer ordered each product recently
  catalogue          name / brand / pack similarity, and pack-size numbers in the words
  AI reading         the SKUs the LLM proposed when reading the message

There is no global meaning for words like "chhota": the same words can mean different
products for different retailers, and without retailer evidence such words do not decide the
pack. Conflicting history (the same words used for different products) lowers confidence and
asks for clarification instead of guessing. Quantities and units are never converted.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from rapidfuzz import fuzz, process

from app.modules.ai_orders.llm import ExtractedLine
from app.utils.text import normalize_text

CONFIDENT = 0.75  # below this the line needs confirmation
MAX_CANDIDATES = 5
MAX_ALTERNATIVES = 2  # each line shows two alternative SKUs
FUZZY_CANDIDATE_MIN = 45
CONFLICT_CAP = 0.6
CLOSE_CALL = 0.3  # top two candidates closer than this: ask the LLM to compare them

# Words that are not part of a product's name: removed from the retailer's wording.
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
    category: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} {self.pack_size} {self.brand}"


@dataclass(frozen=True)
class PastLine:
    """An earlier AI line of this retailer and the product it finally became."""

    wording: str
    product_id: uuid.UUID
    corrected: bool  # the Order Desk changed the product
    at: datetime


@dataclass
class RetailerContext:
    """Only the evidence needed for matching (kept small)."""

    aliases: dict[str, uuid.UUID] = field(default_factory=dict)  # normalized wording -> product
    past_lines: list[PastLine] = field(default_factory=list)  # newest first
    frequency: dict[uuid.UUID, int] = field(default_factory=dict)  # order lines in the last 90 days


@dataclass
class Candidate:
    product: CatalogueProduct
    score: float = 0.0  # ranking only (not a probability)
    name_similarity: float = 0.0  # 0..1
    llm_rank: int | None = None  # position in the LLM's candidate list (0 = first)
    alias: bool = False
    history_count: int = 0
    history_share: float = 0.0
    corrected: bool = False
    pack_match: bool | None = None  # None: the words state no number
    evidence: list[str] = field(default_factory=list)


@dataclass
class LineCandidates:
    line: ExtractedLine
    wording: str
    candidates: list[Candidate]  # best first
    conflict: str | None = None  # same words used for different products before


@dataclass
class Match:
    product: CatalogueProduct | None
    confidence: float
    evidence: list[str]
    alternatives: list[dict]
    clarification: str | None
    unit: str | None


def wording_for_alias(original_text: str, quantity: Decimal | None) -> str:
    """The retailer's words for the product: the line without quantity, unit and filler words
    ("5 peti chhota packet biscuit" -> "chhota biscuit"; "chai patti 250 wala 1 peti" -> "chai patti 250 wala")."""
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


def same_words(a: str, b: str) -> bool:
    """The retailer used the same words (order-insensitive, small spelling differences). A
    single generic word ("biscuit") does not count as the same as a longer phrase."""
    if not a or not b:
        return False
    if a == b or fuzz.token_sort_ratio(a, b) >= 88:
        return True
    shorter = min(a, b, key=lambda s: len(s.split()))
    return len(shorter.split()) >= 2 and fuzz.token_set_ratio(a, b) == 100


def _numbers(text: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text)}


def _pack_numbers(product: CatalogueProduct) -> set[str]:
    return _numbers(f"{product.pack_size} {product.name}")


def _quote(text: str) -> str:
    return f"“{text}”"


def find_candidates(line: ExtractedLine, catalogue: list[CatalogueProduct], ctx: RetailerContext) -> LineCandidates:
    """Collect and score the products this line may mean, with business evidence for each."""
    by_id = {p.id: p for p in catalogue}
    by_sku = {p.sku.casefold(): p for p in catalogue}
    text = normalize_text(line.original_text)
    wording = wording_for_alias(line.original_text, line.quantity)
    description = normalize_text(line.product_description)
    found: dict[uuid.UUID, Candidate] = {}

    def candidate(product: CatalogueProduct) -> Candidate:
        return found.setdefault(product.id, Candidate(product))

    # Catalogue: name / brand / pack similarity of the retailer's words and the AI description.
    labels = {p.id: normalize_text(p.label) for p in catalogue}
    for query in {q for q in (wording, description) if q}:
        for _, score, product_id in process.extract(query, labels, scorer=fuzz.token_set_ratio, limit=6):
            if score >= FUZZY_CANDIDATE_MIN:
                c = candidate(by_id[product_id])
                c.name_similarity = max(c.name_similarity, score / 100)

    # The LLM's reading of the message (only SKUs that exist in this retailer's catalogue).
    for rank, sku in enumerate(line.candidate_skus):
        product = by_sku.get(sku.casefold())
        if product is not None and candidate(product).llm_rank is None:
            found[product.id].llm_rank = rank

    # The retailer's saved wording.
    exact_alias = ctx.aliases.get(wording) if wording else None
    if exact_alias in by_id:
        c = candidate(by_id[exact_alias])
        c.alias = True
        c.evidence.append(f"This retailer’s saved wording {_quote(wording)} means this product")
    partial = [pid for alias, pid in ctx.aliases.items()
               if pid in by_id and pid != exact_alias and alias != wording and _contains_phrase(text, alias)]

    # Earlier AI lines with the same words, and what they became.
    similar = [p for p in ctx.past_lines if p.product_id in by_id and same_words(wording, p.wording)]
    counts = Counter(p.product_id for p in similar)
    conflict = None
    if similar:
        for product_id, n in counts.items():
            c = candidate(by_id[product_id])
            c.history_count, c.history_share = n, n / len(similar)
            c.corrected = any(p.corrected and p.product_id == product_id for p in similar)
            c.evidence.append(f"Retailer used {_quote(wording)} for this product {n} time{'s' if n != 1 else ''} before")
            if c.corrected:
                c.evidence.append(f"The order desk corrected {_quote(wording)} to this product")
        if len(counts) > 1:
            latest = similar[0]  # newest first
            top_share = counts.most_common(1)[0][1] / len(similar)
            resolved = latest.corrected and counts[latest.product_id] == counts.most_common(1)[0][1]
            if top_share < 0.75 and not resolved:
                conflict = "This retailer has used these words for different products: " + ", ".join(
                    f"{by_id[pid].name} {by_id[pid].pack_size} ({n})" for pid, n in counts.most_common())

    numbers = _numbers(wording) if wording else set()
    for c in found.values():
        p = c.product
        if numbers:
            c.pack_match = bool(numbers & _pack_numbers(p))
            if c.pack_match:
                c.evidence.append(f"Pack size {p.pack_size} matches the message")
        freq = ctx.frequency.get(p.id, 0)
        if freq:
            c.evidence.append(f"Ordered {freq} time{'s' if freq != 1 else ''} by this retailer in the last 90 days")
        if p.id in partial:
            c.evidence.append("Part of this retailer’s saved wording points to this product")
        if c.llm_rank == 0:
            c.evidence.append("Suggested by the AI reading of the message")
        if c.name_similarity >= 0.6:
            c.evidence.append(f"Name similarity {round(c.name_similarity * 100)}%")
        c.score = (
            (line.confidence * (1.0, 0.7, 0.5)[min(c.llm_rank, 2)] if c.llm_rank is not None else 0)
            + 0.5 * c.name_similarity
            + (1.0 if c.alias else 0)
            + (0.8 * c.history_share + 0.1 * min(c.history_count, 3) if c.history_count else 0)
            + (0.3 if c.corrected else 0)
            + min(0.15, 0.03 * freq)
            + (0.15 if p.id in partial else 0)
            + (0.3 if c.pack_match else -0.5 if c.pack_match is False else 0)
        )
    ranked = sorted(found.values(), key=lambda c: (-c.score, c.product.sku))[:MAX_CANDIDATES]
    return LineCandidates(line=line, wording=wording, candidates=ranked, conflict=conflict)


def needs_llm_comparison(lc: LineCandidates) -> bool:
    """A close call between candidates without decisive retailer evidence."""
    if len(lc.candidates) < 2 or lc.conflict:
        return False
    top, second = lc.candidates[0], lc.candidates[1]
    decisive = top.alias or (top.history_count >= 2 and top.history_share >= 0.75)
    return not decisive and top.score - second.score < CLOSE_CALL


def confidence_for(c: Candidate, line: ExtractedLine, llm_confidence: float | None = None) -> float:
    """How sure we are that `c` is the product meant: the AI's own confidence, raised by
    retailer evidence and lowered by a pack-size mismatch."""
    if llm_confidence is not None:
        base = llm_confidence
    elif c.llm_rank is not None:
        base = line.confidence * (1.0, 0.8, 0.6)[min(c.llm_rank, 2)]
    else:
        base = c.name_similarity * 0.9
    if c.alias:
        base = max(base, 0.97)
    if c.corrected:
        base = max(base, 0.95)
    if c.history_count:
        if c.history_share >= 0.75:
            base = max(base, min(0.98, 0.86 + 0.03 * c.history_count))
        else:
            base = max(base, 0.7)
    if c.pack_match is False:
        base *= 0.6
    elif c.evidence and any(e.startswith("Ordered ") for e in c.evidence):
        base += 0.05
    return round(min(max(base, 0.0), 1.0), 3)


def decide(lc: LineCandidates, llm_choice: dict | None = None) -> Match:
    """The best candidate, its confidence, evidence and alternatives, and whether the
    retailer / order desk must clarify. `llm_choice` is the LLM's comparison of the
    candidates ({"sku", "confidence", "needs_clarification", "reason"}), if it was asked."""
    line = lc.line
    chosen = lc.candidates[0] if lc.candidates else None
    llm_confidence = None
    llm_reason = None
    llm_unsure = False
    if llm_choice:
        by_sku = {c.product.sku.casefold(): c for c in lc.candidates}
        picked = by_sku.get(str(llm_choice.get("sku") or "").casefold())
        if picked is not None:  # an SKU outside the candidates is ignored
            chosen = picked
            llm_confidence = float(llm_choice.get("confidence") or 0)
            llm_reason = (llm_choice.get("reason") or "").strip()[:160] or None
        llm_unsure = bool(llm_choice.get("needs_clarification"))

    confidence = confidence_for(chosen, line, llm_confidence) if chosen else 0.0
    if lc.conflict:
        confidence = min(confidence, CONFLICT_CAP)
    evidence = list(chosen.evidence) if chosen else []
    if llm_reason:
        evidence.append(f"AI comparison: {llm_reason}")
    if lc.conflict:
        evidence.append(lc.conflict)

    alternatives = [{
        "product_id": str(c.product.id), "sku": c.product.sku, "name": c.product.name,
        "pack_size": c.product.pack_size, "confidence": confidence_for(c, line),
        "evidence": c.evidence[:3],
    } for c in lc.candidates if c is not chosen][:MAX_ALTERNATIVES]

    product = chosen.product if chosen else None
    unit = line.unit
    if unit == "case" and product is not None:
        unit = product.order_unit
    clarification = None
    if product is None:
        clarification = "Product not recognised. Please choose it from the list."
    elif lc.conflict:
        clarification = "This retailer has used these words for different products. Please confirm which one."
    elif line.quantity is None:
        clarification = "Quantity not mentioned."
    elif unit is None:
        clarification = f"Unit not mentioned. Is it {product.order_unit}s?"
    elif unit != product.order_unit:
        clarification = f"This product is ordered in {product.order_unit}s; the message says {unit}s."
    elif llm_unsure or confidence < CONFIDENT:
        clarification = "Not sure about this product. Please confirm it or pick another."
    return Match(product=product, confidence=confidence, evidence=evidence[:6], alternatives=alternatives,
                 clarification=clarification, unit=unit)


def clarification_reason(item, matched_order_unit: str | None) -> str | None:
    """Why a stored extraction item needs the user's input (None if it does not)."""
    if getattr(item, "clarification_reason", None):
        return item.clarification_reason
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

"""AI order capture as a small LangGraph pipeline (one graph, no agents):

    load_retailer_context -> extract_order -> find_product_candidates
        -> match_products -> validate_units -> build_draft_order

The retailer's context is loaded first because extraction needs the retailer's catalogue (the
model may only propose SKUs from it). The database session is passed in the run config
(never in the state); the read transaction is ended before any LLM call. The result is a
stored draft (AiExtraction) for the retailer to review; it never creates or confirms an order.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.constants import AiInputType
from app.models import AiExtraction, Retailer, User
from app.modules.ai_orders import llm, matcher, repository
from app.modules.pricing import repository as pricing_repository

HISTORY_DAYS = 365
FREQUENCY_DAYS = 90


class OrderState(TypedDict, total=False):
    retailer_id: uuid.UUID
    input_type: str  # TEXT / IMAGE / VOICE
    original_input: str  # the message, the voice transcript, or (after reading) the photo text
    image_data_url: str | None
    catalogue: list[matcher.CatalogueProduct]
    retailer_context: matcher.RetailerContext
    extracted_items: list[llm.ExtractedLine]
    model_name: str
    raw_response: dict[str, Any]
    product_candidates: list[matcher.LineCandidates]
    llm_choices: dict[int, dict]
    matched_items: list[matcher.Match]
    clarification_required: bool
    draft_order: AiExtraction


def _db(config) -> Session:
    return config["configurable"]["db"]


def load_retailer_context(state: OrderState, config) -> OrderState:
    """The retailer's catalogue (products priced for them) and only the evidence matching
    needs: saved wordings, earlier AI lines (last year, newest 300) and recent frequency."""
    db = _db(config)
    retailer_id = state["retailer_id"]
    now = datetime.now(UTC)
    prices = pricing_repository.get_effective_prices(db, retailer_id, now)
    rows = repository.get_catalogue(db, list(prices.keys()))
    catalogue = [matcher.CatalogueProduct(p.id, p.sku, p.name, p.brand, p.pack_size, p.order_unit, category)
                 for p, category in rows]
    past = [matcher.PastLine(matcher.wording_for_alias(text, qty), product_id, bool(corrected), at)
            for text, qty, product_id, corrected, at in
            repository.get_phrase_history(db, retailer_id, now - timedelta(days=HISTORY_DAYS))]
    context = matcher.RetailerContext(
        aliases={a.normalized_alias: a.product_id for a in repository.get_aliases(db, retailer_id)},
        past_lines=[p for p in past if p.wording],
        frequency=repository.get_product_frequency(db, retailer_id, now - timedelta(days=FREQUENCY_DAYS)),
    )
    db.commit()  # end the read transaction: no connection is held during the LLM calls
    return {"catalogue": catalogue, "retailer_context": context}


def extract_order(state: OrderState, config) -> OrderState:
    catalogue, ctx = state["catalogue"], state["retailer_context"]
    words: dict[uuid.UUID, list[str]] = {}
    for alias, product_id in ctx.aliases.items():
        words.setdefault(product_id, []).append(alias)
    frequent = sorted(ctx.frequency, key=ctx.frequency.get, reverse=True)[:15]
    by_id = {p.id: p for p in catalogue}
    result = llm.extract_lines(
        state["original_input"],
        [llm.CatalogueEntry(p.sku, p.name, p.brand, p.category, p.pack_size, p.order_unit, tuple(words.get(p.id, ())))
         for p in catalogue],
        [by_id[pid].sku for pid in frequent if pid in by_id],
        image_data_url=state.get("image_data_url"),
    )
    update: OrderState = {"extracted_items": result.lines, "model_name": result.model, "raw_response": result.raw}
    if state.get("input_type") == AiInputType.IMAGE:
        update["original_input"] = (result.raw.get("read_text") or "").strip() or "Photo of an order list"
    return update


def find_product_candidates(state: OrderState, config) -> OrderState:
    return {"product_candidates": [matcher.find_candidates(line, state["catalogue"], state["retailer_context"])
                                   for line in state["extracted_items"]]}


def match_products(state: OrderState, config) -> OrderState:
    """Only close calls go to the LLM, with the candidates and their evidence."""
    close = [(i, lc) for i, lc in enumerate(state["product_candidates"]) if matcher.needs_llm_comparison(lc)]
    choices: dict[int, dict] = {}
    if close:
        choices = llm.compare_candidates([{
            "line": i, "words": lc.line.original_text, "retailer_words": lc.wording,
            "candidates": [{"sku": c.product.sku, "product": f"{c.product.name} {c.product.pack_size}",
                            "brand": c.product.brand, "category": c.product.category, "evidence": c.evidence}
                           for c in lc.candidates],
        } for i, lc in close])
    return {"llm_choices": choices}


def validate_units(state: OrderState, config) -> OrderState:
    """Final product, confidence, evidence and clarification per line (quantity and unit are
    never assumed or converted)."""
    matches = [matcher.decide(lc, state["llm_choices"].get(i)) for i, lc in enumerate(state["product_candidates"])]
    return {"matched_items": matches, "clarification_required": any(m.clarification for m in matches)}


def build_draft_order(state: OrderState, config) -> OrderState:
    from app.modules.ai_orders.schemas import ExtractedItemInput, RecordExtractionInput
    from app.modules.ai_orders.service import record_extraction

    items = [ExtractedItemInput(
        original_text=lc.line.original_text,
        extracted_name=lc.line.product_description or lc.line.original_text[:200],
        quantity=lc.line.quantity,
        unit=m.unit,
        matched_product_id=m.product.id if m.product else None,
        confidence=m.confidence,
        alternatives=m.alternatives or None,
        evidence=m.evidence or None,
        clarification_reason=m.clarification,
        requires_clarification=m.clarification is not None,
    ) for lc, m in zip(state["product_candidates"], state["matched_items"])]
    extraction = record_extraction(_db(config), config["configurable"]["actor"], RecordExtractionInput(
        retailer_id=state["retailer_id"], original_message=state["original_input"],
        input_type=state.get("input_type") or AiInputType.TEXT, model_name=state.get("model_name"),
        raw_response=state.get("raw_response"), items=items,
    ))
    return {"draft_order": extraction}


def _build():
    graph = StateGraph(OrderState)
    steps = [load_retailer_context, extract_order, find_product_candidates, match_products, validate_units,
             build_draft_order]
    for step in steps:
        graph.add_node(step.__name__, step)
    graph.add_edge(START, steps[0].__name__)
    for a, b in zip(steps, steps[1:]):
        graph.add_edge(a.__name__, b.__name__)
    graph.add_edge(steps[-1].__name__, END)
    return graph.compile()


ORDER_GRAPH = _build()


def run(db: Session, actor: User, retailer: Retailer, *, input_type: str, text: str,
        image_data_url: str | None = None) -> AiExtraction:
    state = ORDER_GRAPH.invoke(
        {"retailer_id": retailer.id, "input_type": input_type, "original_input": text, "image_data_url": image_data_url},
        config={"configurable": {"db": db, "actor": actor}},
    )
    return state["draft_order"]

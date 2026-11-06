"""AI text order capture: LLM call (faked at the HTTP layer), backend SKU matching,
clarification of ambiguous lines, draft -> order confirmation and alias learning."""

import json
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.security import create_access_token
from app.models import CreditAccount, Order, RetailerAlias
from app.modules.ai_orders import llm
from seed.run_seed import seed_id
from tests.conftest import seed_user

SAMPLE = "bhaiya 5 peti biscuit chhota, 2 peti washing powder 1 kilo, chai patti 250 wala 1 peti"
BS075, BS150, DT1KG, TE250 = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-BS-150", "SKU-DT-1KG", "SKU-TE-250"))


def line(text, desc, qty, unit, skus, conf):
    return {"original_text": text, "product_description": desc, "quantity": qty, "unit": unit,
            "candidate_skus": skus, "confidence": conf}


SAMPLE_OUTPUT = [
    line("5 peti biscuit chhota", "glucose biscuit small", 5, "case", ["SKU-BS-075", "SKU-BS-150"], 0.9),
    line("2 peti washing powder 1 kilo", "detergent powder 1kg", 2, "case", ["SKU-DT-1KG"], 0.93),
    line("chai patti 250 wala 1 peti", "tea leaf 250g", 1, "case", ["SKU-TE-250"], 0.95),
]


class FakeOpenAI:
    """Stands in for api.openai.com; records requests and returns a structured output."""

    def __init__(self):
        self.lines: list[dict] = []
        self.matches: list[dict] = []  # answers to the candidate comparison (close calls)
        self.read_text = ""  # what the model "reads" from a photo
        self.transcript = ""  # what a voice note "says"
        self.status = 200
        self.requests: list[dict] = []

    @property
    def extraction_requests(self) -> list[dict]:
        return [r for r in self.requests if r.get("response_format", {}).get("json_schema", {}).get("name") == "order_lines"]

    @property
    def comparison_requests(self) -> list[dict]:
        return [r for r in self.requests if r.get("response_format", {}).get("json_schema", {}).get("name") == "product_matches"]

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-openai-key"
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"type": "server_error"}})
        if str(request.url) == "https://api.openai.com/v1/audio/transcriptions":
            self.requests.append({"transcription": True, "size": len(request.content)})
            return httpx.Response(200, json={"text": self.transcript})
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        body = json.loads(request.content)
        self.requests.append(body)
        if body["response_format"]["json_schema"]["name"] == "product_matches":
            content = json.dumps({"matches": self.matches})
        else:
            output = {"lines": self.lines}
            if "read_text" in body["response_format"]["json_schema"]["schema"]["properties"]:
                output["read_text"] = self.read_text
            content = json.dumps(output)
        return httpx.Response(200, json={"model": "gpt-test", "choices": [{"message": {"content": content}}]})


@pytest.fixture
def openai(monkeypatch):
    fake = FakeOpenAI()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(llm, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return fake


@pytest.fixture
def as_user(tx_client, tx):
    def call(key, method, url, **kw):
        token, _ = create_access_token(seed_user(tx, key))
        return tx_client.request(method, f"/api/v1{url}", headers={"Authorization": f"Bearer {token}"}, **kw)
    return call


def extract(as_user, message, key="retailer_sharma"):
    response = as_user(key, "POST", "/ai-orders/extract", json={"message": message})
    assert response.status_code == 200, response.json()
    return response.json()["data"]


# ---------------------------------------------------------------- the supplied example


def test_hinglish_sample_message_becomes_a_reviewable_draft(as_user, openai, tx):
    openai.lines = SAMPLE_OUTPUT
    orders_before = tx.scalar(select(func.count()).select_from(Order))

    draft = extract(as_user, SAMPLE)

    got = [(i["product"]["sku"], Decimal(i["quantity"]), i["unit"], i["requires_clarification"]) for i in draft["items"]]
    assert got == [("SKU-BS-075", 5, "case", False), ("SKU-DT-1KG", 2, "case", False), ("SKU-TE-250", 1, "case", False)]
    assert [i["original_text"] for i in draft["items"]] == [l["original_text"] for l in SAMPLE_OUTPUT]
    assert all(Decimal(i["confidence"]) >= Decimal("0.75") and i["clarification"] is None for i in draft["items"])
    # The other biscuit pack is offered as an alternative.
    assert "SKU-BS-150" in [a["sku"] for a in draft["items"][0]["alternatives"]]
    assert draft["original_message"] == SAMPLE and draft["status"] == "PENDING"
    # Nothing is ordered automatically.
    assert tx.scalar(select(func.count()).select_from(Order)) == orders_before


def test_prompt_contains_message_and_retailers_catalogue_but_no_prices(as_user, openai):
    openai.lines = SAMPLE_OUTPUT
    extract(as_user, SAMPLE)
    [request] = openai.extraction_requests
    assert request["temperature"] == 0
    assert request["response_format"]["json_schema"]["strict"] is True
    prompt = request["messages"][1]["content"]
    assert SAMPLE in prompt and "SKU-BS-075 | Glucose Biscuit" in prompt
    assert "8.10" not in prompt and "dealer" not in prompt.lower()  # AI never sees prices


def test_partial_alias_does_not_override_explicit_pack_size(as_user, openai):
    # Gupta's saved alias "washing powder" means the 500g pack, but the message says 1 kilo.
    openai.lines = SAMPLE_OUTPUT
    items = extract(as_user, SAMPLE, key="retailer_gupta")["items"]
    assert items[1]["product"]["sku"] == "SKU-DT-1KG"
    assert "SKU-DT-500" in [a["sku"] for a in items[1]["alternatives"]]


def test_exact_saved_wording_matches_directly(as_user, openai):
    # Gupta's alias "chai patti 250" is the whole product wording of this line.
    openai.lines = [line("chai patti 250 2 peti", "tea leaf", 2, "case", [], 0.3)]
    [item] = extract(as_user, "chai patti 250 2 peti", key="retailer_gupta")["items"]
    assert item["product"]["sku"] == "SKU-TE-250" and item["requires_clarification"] is False


# ---------------------------------------------------------------- ambiguity


def test_missing_unit_requires_clarification(as_user, openai):
    openai.lines = [line("5 biscuit bhej dena", "glucose biscuit", 5, None, ["SKU-BS-075", "SKU-BS-150"], 0.6)]
    [item] = extract(as_user, "5 biscuit bhej dena")["items"]
    assert item["requires_clarification"] is True and item["unit"] is None
    assert item["clarification"] == "Unit not mentioned. Is it cases?"


def test_pieces_for_a_case_product_require_clarification_not_conversion(as_user, openai):
    openai.lines = [line("20 packet biscuit 75g", "glucose biscuit 75g", 20, "piece", ["SKU-BS-075"], 0.95)]
    [item] = extract(as_user, "20 packet biscuit 75g")["items"]
    assert item["requires_clarification"] is True and item["unit"] == "piece" and Decimal(item["quantity"]) == 20
    assert "ordered in cases" in item["clarification"]


def test_missing_quantity_requires_clarification(as_user, openai):
    openai.lines = [line("thoda chai patti bhejo", "tea leaf", None, None, ["SKU-TE-500"], 0.5)]
    [item] = extract(as_user, "thoda chai patti bhejo")["items"]
    assert item["requires_clarification"] is True and item["quantity"] is None
    assert item["clarification"] == "Quantity not mentioned."


def test_low_confidence_match_requires_confirmation(as_user, openai):
    openai.lines = [line("2 peti biscuit", "biscuit", 2, "case", ["SKU-BS-075", "SKU-BS-150", "SKU-CB-100"], 0.45)]
    [item] = extract(as_user, "2 peti biscuit")["items"]
    assert item["requires_clarification"] is True and len(item["alternatives"]) >= 2
    assert item["clarification"].startswith("Not sure about this product")


def test_unknown_sku_from_llm_is_ignored(as_user, openai):
    openai.lines = [line("2 peti maggi", "instant noodles 70g", 2, "case", ["SKU-FAKE-1"], 0.99)]
    [item] = extract(as_user, "2 peti maggi")["items"]
    # The invented SKU is dropped; fuzzy matching on the description finds the real product.
    assert item["product"]["sku"] == "SKU-NS-070"


def test_unrecognised_product_asks_user_to_choose(as_user, openai):
    openai.lines = [line("1 peti sabun", "bath soap", 1, "case", [], 0.0)]
    [item] = extract(as_user, "1 peti sabun")["items"]
    assert item["product"] is None and item["requires_clarification"] is True
    assert item["clarification"] == "Product not recognised. Please choose it from the list."


# ---------------------------------------------------------------- failures and access


def test_not_configured_returns_503_without_mock_results(as_user):
    response = as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": SAMPLE})
    assert (response.status_code, response.json()["error_code"]) == (503, "AI_NOT_CONFIGURED")
    assert "OPENAI_API_KEY" in response.json()["message"]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_errors_return_503(as_user, openai, status):
    openai.status = status
    response = as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": SAMPLE})
    assert (response.status_code, response.json()["error_code"]) == (503, "AI_SERVICE_UNAVAILABLE")
    assert "test-openai-key" not in response.text


def test_order_desk_cannot_capture_orders(as_user, openai):
    response = as_user("order_desk", "POST", "/ai-orders/extract", json={"message": SAMPLE})
    assert response.status_code == 403 and openai.requests == []


def test_message_length_is_limited(as_user, openai):
    assert as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "x" * 2001}).status_code == 422


def test_other_retailer_cannot_read_or_confirm_a_draft(as_user, openai):
    openai.lines = SAMPLE_OUTPUT
    draft = extract(as_user, SAMPLE)
    assert as_user("retailer_gupta", "GET", f"/ai-orders/{draft['extraction_id']}").status_code == 403
    body = {"items": [{"product_id": str(BS075), "quantity": 1, "unit": "case"}]}
    assert as_user("retailer_gupta", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body).status_code == 403


# ---------------------------------------------------------------- draft -> order, alias learning


def test_reviewed_draft_is_placed_as_ai_order_and_learns_corrections(as_user, openai, tx):
    openai.lines = SAMPLE_OUTPUT
    before = {(a.normalized_alias, a.product_id) for a in tx.scalars(select(RetailerAlias))}
    draft = extract(as_user, SAMPLE)
    biscuit, detergent, tea = draft["items"]

    # The retailer switches the biscuit to the 150g pack, drops tea (out of stock) and adds a product.
    body = {"items": [
        {"extraction_item_id": biscuit["id"], "product_id": str(BS150), "quantity": 5, "unit": "case"},
        {"extraction_item_id": detergent["id"], "product_id": str(DT1KG), "quantity": 2, "unit": "case"},
        {"product_id": str(seed_id("product", "SKU-NS-070")), "quantity": 1, "unit": "case"},
    ]}
    response = as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body)
    assert response.status_code == 201, response.json()
    order = response.json()["data"]
    assert order["source"] == "AI" and order["ai"]["original_message"] == SAMPLE
    assert {i["sku"] for i in order["items"]} == {"SKU-BS-150", "SKU-DT-1KG", "SKU-NS-070"}

    # Priced by the backend like any order.
    quote = as_user("retailer_sharma", "POST", "/orders/quote", json={"items": [
        {"product_id": i["product_id"], "quantity": i["paid_quantity"], "unit": "case"} for i in order["items"]]})
    assert quote.json()["data"]["totals"]["grand_total"] == order["grand_total"]

    # Only the changed line taught Sharma's wording.
    aliases = tx.scalars(select(RetailerAlias).where(RetailerAlias.retailer_id == seed_id("retailer", "sharma"))).all()
    assert {(a.normalized_alias, a.product_id) for a in aliases} - before == {("biscuit chhota", BS150)}

    # A confirmed draft cannot be placed twice.
    again = as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body)
    assert (again.status_code, again.json()["error_code"]) == (409, "INVALID_EXTRACTION_STATUS")

    # Next time the same words match the learned product, even if the LLM suggests another.
    openai.lines = [line("3 peti biscuit chhota", "glucose biscuit small", 3, "case", ["SKU-BS-075"], 0.9)]
    [item] = extract(as_user, "3 peti biscuit chhota")["items"]
    assert item["product"]["sku"] == "SKU-BS-150" and Decimal(item["confidence"]) >= Decimal("0.97")
    prompt_row = next(r for r in openai.requests[-1]["messages"][1]["content"].splitlines() if r.startswith("SKU-BS-150"))
    assert "retailer calls it:" in prompt_row and "biscuit chhota" in prompt_row

    # ...but only for Sharma: Gupta's draft is not affected by Sharma's alias.
    [gupta_item] = extract(as_user, "3 peti biscuit chhota", key="retailer_gupta")["items"]
    assert gupta_item["product"]["sku"] == "SKU-BS-075"


# ---------------------------------------------------------------- photo and voice input


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def upload(as_user, kind, content, content_type, key="retailer_sharma"):
    return as_user(key, "POST", "/ai-orders/extract-media", data={"kind": kind},
                   files={"file": (f"order.{content_type.split('/')[1]}", content, content_type)})


def test_photo_of_order_list_becomes_a_draft(as_user, openai):
    openai.lines = SAMPLE_OUTPUT[:1]
    openai.read_text = "Biscuit chhota - 5 peti"
    response = upload(as_user, "image", PNG, "image/png")
    assert response.status_code == 200, response.json()
    draft = response.json()["data"]
    assert draft["input_type"] == "IMAGE" and draft["original_message"] == "Biscuit chhota - 5 peti"
    [request] = openai.extraction_requests
    image_part = request["messages"][1]["content"][1]
    assert image_part["type"] == "image_url" and image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert draft["items"][0]["product"]["sku"] == "SKU-BS-075"


def test_voice_note_is_transcribed_then_read(as_user, openai):
    openai.transcript = "bhaiya 2 peti washing powder 1 kilo bhej do"
    openai.lines = [SAMPLE_OUTPUT[1]]
    response = upload(as_user, "voice", b"webm-audio" * 20, "audio/webm")
    assert response.status_code == 200, response.json()
    draft = response.json()["data"]
    assert draft["input_type"] == "VOICE" and draft["original_message"] == openai.transcript
    assert openai.requests[0] == {"transcription": True, "size": openai.requests[0]["size"]}
    assert draft["items"][0]["product"]["sku"] == "SKU-DT-1KG"


@pytest.mark.parametrize("kind,content_type", [("image", "application/pdf"), ("voice", "image/png")])
def test_media_type_is_checked(as_user, openai, kind, content_type):
    assert upload(as_user, kind, b"x" * 10, content_type).status_code == 422
    assert openai.requests == []


def test_order_desk_cannot_capture_media(as_user, openai):
    assert upload(as_user, "image", PNG, "image/png", key="order_desk").status_code == 403


# ---------------------------------------------------------------- learning loop


def test_ai_lines_link_to_order_lines_and_desk_corrections_teach_the_retailers_words(as_user, openai, tx):
    from app.models import AiExtractionItem

    tx.execute(update(CreditAccount).values(credit_limit=Decimal("10000000")))
    tx.commit()
    openai.lines = [line("3 peti chhota wala biscuit", "glucose biscuit", 3, "case", ["SKU-BS-150"], 0.9)]
    draft = extract(as_user, "3 peti chhota wala biscuit")
    item = draft["items"][0]
    assert item["product"]["sku"] == "SKU-BS-150" and item["evidence"]
    order = as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json={"items": [
        {"extraction_item_id": item["id"], "product_id": str(BS150), "quantity": 3, "unit": "case"}]}).json()["data"]
    ai_line = tx.get(AiExtractionItem, uuid.UUID(item["id"]))
    tx.refresh(ai_line)
    assert str(ai_line.order_item_id) == order["items"][0]["id"]

    # The order desk sees the AI interpretation, and corrects 150 g -> 75 g.
    review = as_user("order_desk", "GET", f"/order-desk/orders/{order['id']}").json()["data"]
    [ai] = review["ai_lines"]
    assert ai["product"]["sku"] == "SKU-BS-150" and ai["evidence"] and ai["original_text"] == "3 peti chhota wala biscuit"
    as_user("order_desk", "PATCH", f"/orders/{order['id']}/items/{order['items'][0]['id']}",
            json={"new_product_id": str(BS075), "reason": "Retailer means the 75g pack"})
    saved = tx.scalar(select(RetailerAlias).where(RetailerAlias.retailer_id == seed_id("retailer", "sharma"),
                                                  RetailerAlias.normalized_alias == "chhota wala biscuit"))
    assert saved is not None and saved.product_id == BS075

    # Next time the same words go straight to the corrected product, with the evidence.
    openai.lines = [line("4 peti chhota wala biscuit", "glucose biscuit", 4, "case", ["SKU-BS-150"], 0.9)]
    [again] = extract(as_user, "4 peti chhota wala biscuit")["items"]
    assert again["product"]["sku"] == "SKU-BS-075" and again["requires_clarification"] is False
    assert any("order desk corrected" in e for e in again["evidence"])

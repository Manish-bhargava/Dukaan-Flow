"""LLM integration point for AI order capture: OpenAI Chat Completions with Structured
Outputs, called with httpx (no SDK). The model only reads the message: it splits it into
lines and proposes quantity, unit and candidate SKUs from the catalogue it is given. It
never sees or decides prices, schemes, stock or credit, and its output is validated and
matched again by app/modules/ai_orders/matcher.py.
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import settings
from app.core.constants import ErrorCode
from app.exceptions.base import AppException

logger = logging.getLogger(__name__)



def completions_url() -> str:
    return f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"

SYSTEM_PROMPT = """You read order messages that kirana (Indian grocery) retailers send to their FMCG distributor.
Messages are informal Hindi, Hinglish or English, like WhatsApp chats.

Return one line per product mentioned:
- original_text: the exact words of the message for that product, copied, not translated.
- product_description: a short English description, e.g. "glucose biscuit 75g".
- quantity: the number stated for that product, or null if no number is stated.
- unit: "case" for cases/cartons (peti, petti, pethi, carton, case, cs), "piece" for pieces/packets
  (piece, pcs, pc, packet, pkt, nag), or null if the message does not say. Never assume a unit.
- candidate_skus: up to 3 SKUs from the catalogue that could be this product, best first. Only use
  SKUs from the catalogue. Empty list if nothing in the catalogue fits.
- confidence: 0 to 1, how sure you are that the first candidate is the product meant. Use less than
  0.7 when the pack size or variant is not clear from the message.

Hints: chhota/chota/small = the smallest pack of that product, bada/big = the largest; "250 wala" =
the 250 g/ml pack; chai patti = tea leaf; washing powder/surf = detergent powder; kilo = kg.
Ignore words like bhaiya, bhej do, bhej dena, aur, please. Products the retailer ordered recently are
more likely. Do not invent products. Do not mention prices or discounts."""

RESPONSE_SCHEMA = {
    "name": "order_lines",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lines"],
        "properties": {
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["original_text", "product_description", "quantity", "unit",
                                 "candidate_skus", "confidence"],
                    "properties": {
                        "original_text": {"type": "string"},
                        "product_description": {"type": "string"},
                        "quantity": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"], "enum": ["case", "piece", None]},
                        "candidate_skus": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                    },
                },
            }
        },
    },
}


@dataclass(frozen=True)
class CatalogueEntry:
    sku: str
    name: str
    brand: str
    category: str
    pack_size: str
    order_unit: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractedLine:
    original_text: str
    product_description: str
    quantity: Decimal | None
    unit: str | None  # "case", "piece" or None
    candidate_skus: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class LlmResult:
    lines: list[ExtractedLine]
    model: str
    raw: dict[str, Any]  # parsed model output, stored on the extraction for audit


def is_configured() -> bool:
    return bool(settings.OPENAI_API_KEY)


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=settings.OPENAI_TIMEOUT_SECONDS)


def _user_prompt(message: str, catalogue: list[CatalogueEntry], recent_skus: list[str]) -> str:
    rows = "\n".join(
        f"{c.sku} | {c.name} | {c.brand} | {c.category} | {c.pack_size} | {c.order_unit}"
        + (f" | retailer calls it: {', '.join(c.aliases)}" if c.aliases else "")
        for c in catalogue
    )
    recent = ", ".join(recent_skus) or "none"
    return (
        "Catalogue (SKU | product | brand | category | pack | order unit):\n"
        f"{rows}\n\nRecently ordered by this retailer: {recent}\n\nMessage:\n<<<\n{message}\n>>>"
    )


def _quantity(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        quantity = Decimal(str(value))
    except InvalidOperation:
        return None
    return quantity if quantity > 0 else None


def _parse(content: str) -> list[ExtractedLine]:
    data = json.loads(content)
    lines = []
    for raw in data.get("lines", []):
        text = str(raw.get("original_text") or "").strip()
        if not text:
            continue
        unit = raw.get("unit")
        lines.append(ExtractedLine(
            original_text=text,
            product_description=str(raw.get("product_description") or text).strip()[:200],
            quantity=_quantity(raw.get("quantity")),
            unit=unit if unit in ("case", "piece") else None,
            candidate_skus=tuple(str(s).strip() for s in raw.get("candidate_skus") or [])[:3],
            confidence=min(max(float(raw.get("confidence") or 0), 0.0), 1.0),
        ))
    return lines


def extract_lines(message: str, catalogue: list[CatalogueEntry], recent_skus: list[str]) -> LlmResult:
    if not is_configured():
        raise AppException(
            "AI order capture is not configured. Set OPENAI_API_KEY (and optionally OPENAI_MODEL) "
            "in backend/.env and restart the server.",
            ErrorCode.AI_NOT_CONFIGURED,
            503,
        )
    payload = {
        "model": settings.OPENAI_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(message, catalogue, recent_skus)},
        ],
        "response_format": {"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
    }
    unavailable = AppException(
        "AI order capture is temporarily unavailable. Please try again or add products from the catalogue.",
        ErrorCode.AI_SERVICE_UNAVAILABLE,
        503,
    )
    try:
        with _http_client() as client:
            response = client.post(
                completions_url(), json=payload, headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            )
    except httpx.HTTPError as exc:
        logger.warning("OpenAI request failed: %s", type(exc).__name__)
        raise unavailable from None
    if response.status_code != 200:
        # The body may echo request details but never the key; log only status and error type.
        error = (response.json().get("error") or {}) if response.headers.get("content-type", "").startswith("application/json") else {}
        logger.warning("OpenAI returned HTTP %s (%s)", response.status_code, error.get("type") or error.get("code"))
        raise unavailable
    try:
        body = response.json()
        choice = body["choices"][0]["message"]
        if choice.get("refusal"):
            raise ValueError("refusal")
        content = choice["content"]
        lines = _parse(content)
    except (KeyError, IndexError, ValueError, TypeError):
        logger.warning("OpenAI response could not be parsed")
        raise unavailable from None
    return LlmResult(lines=lines, model=body.get("model") or settings.OPENAI_MODEL, raw=json.loads(content))

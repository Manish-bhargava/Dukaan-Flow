"""The only OpenAI integration for AI order capture (httpx, no SDK):

- extract_lines: Chat Completions + Structured Outputs reads a text message or a photo of an
  order list into lines (words, quantity, unit, candidate SKUs from the catalogue given);
- transcribe: a voice note to text (audio transcriptions);
- compare_candidates: for close calls, picks among the candidate products the backend found,
  using the retailer evidence it is given.

The model never sees or decides prices, schemes, stock or credit, and everything it returns is
validated again by app/modules/ai_orders/matcher.py.
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

Hints: "250 wala" = the 250 g/ml pack; chai patti = tea leaf; washing powder/surf = detergent powder;
kilo = kg. Size words such as chhota, bada, small, big mean different packs for different retailers:
keep them in original_text, do not decide the pack from them alone, and use a lower confidence when the
pack is not clear. Ignore words like bhaiya, bhej do, bhej dena, aur, please. Do not invent products.
Do not mention prices or discounts."""

IMAGE_HINT = """The order is a photo (handwritten or printed list, or a screenshot). Read it line by line.
Put the full text you can read in read_text, and copy each product line's words into original_text."""

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


def _not_configured() -> AppException:
    return AppException(
        "AI order capture is not configured. Set OPENAI_API_KEY (and optionally OPENAI_MODEL) "
        "in backend/.env and restart the server.",
        ErrorCode.AI_NOT_CONFIGURED,
        503,
    )


def _unavailable() -> AppException:
    return AppException(
        "AI order capture is temporarily unavailable. Please try again or add products from the catalogue.",
        ErrorCode.AI_SERVICE_UNAVAILABLE,
        503,
    )


def _post(path: str, **kwargs) -> httpx.Response:
    """POST to the OpenAI API; network errors and non-200 answers become AI_SERVICE_UNAVAILABLE.
    Logs only the status and error type (never the key, the message or the output)."""
    if not is_configured():
        raise _not_configured()
    try:
        with _http_client() as client:
            response = client.post(f"{settings.OPENAI_BASE_URL.rstrip('/')}{path}",
                                   headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}, **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("OpenAI request failed: %s", type(exc).__name__)
        raise _unavailable() from None
    if response.status_code != 200:
        error = (response.json().get("error") or {}) if response.headers.get("content-type", "").startswith("application/json") else {}
        logger.warning("OpenAI returned HTTP %s (%s)", response.status_code, error.get("type") or error.get("code"))
        raise _unavailable()
    return response


def _structured(payload: dict) -> tuple[dict, str]:
    """Chat completion with a JSON schema; returns (parsed content, model)."""
    body = _post("/chat/completions", json=payload).json()
    try:
        choice = body["choices"][0]["message"]
        if choice.get("refusal"):
            raise ValueError("refusal")
        return json.loads(choice["content"]), body.get("model") or settings.OPENAI_MODEL
    except (KeyError, IndexError, ValueError, TypeError):
        logger.warning("OpenAI response could not be parsed")
        raise _unavailable() from None


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


def _schema(with_read_text: bool) -> dict:
    if not with_read_text:
        return RESPONSE_SCHEMA
    schema = json.loads(json.dumps(RESPONSE_SCHEMA))
    schema["schema"]["required"].append("read_text")
    schema["schema"]["properties"]["read_text"] = {"type": "string"}
    return schema


def extract_lines(message: str, catalogue: list[CatalogueEntry], recent_skus: list[str],
                  image_data_url: str | None = None) -> LlmResult:
    """Read a text message, or a photo of an order list (`image_data_url`), into lines."""
    prompt = _user_prompt(message if image_data_url is None else "(see the photo)", catalogue, recent_skus)
    user_content: str | list = prompt
    if image_data_url is not None:
        user_content = [{"type": "text", "text": f"{IMAGE_HINT}\n\n{prompt}"},
                        {"type": "image_url", "image_url": {"url": image_data_url}}]
    payload = {
        "model": settings.OPENAI_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        "response_format": {"type": "json_schema", "json_schema": _schema(image_data_url is not None)},
    }
    data, model = _structured(payload)
    try:
        lines = _parse(json.dumps(data))
    except (KeyError, IndexError, ValueError, TypeError):
        logger.warning("OpenAI response could not be parsed")
        raise _unavailable() from None
    return LlmResult(lines=lines, model=model, raw=data)


def transcribe(audio: bytes, filename: str, content_type: str) -> str:
    """Voice note -> text (Hindi / Hinglish / English kept as spoken)."""
    response = _post(
        "/audio/transcriptions",
        data={"model": settings.OPENAI_TRANSCRIBE_MODEL, "response_format": "json",
              "prompt": "Kirana order: product names, quantities in peti, cases, packets. Hindi and English."},
        files={"file": (filename, audio, content_type)},
    )
    try:
        text = str(response.json().get("text") or "").strip()
    except ValueError:
        raise _unavailable() from None
    if not text:
        raise AppException("The voice note could not be understood. Please record it again or type the order.",
                           ErrorCode.VALIDATION_ERROR, 422)
    return text


COMPARE_PROMPT = """You help an FMCG distributor understand which product a kirana retailer meant.
For each line you get the retailer's words and a few candidate products found in the catalogue, each with
evidence about THIS retailer (their saved wording, what the same words meant in their earlier orders,
Order Desk corrections, how often they order it, pack-size match).

Choose the candidate the retailer most likely meant. Retailer evidence (saved wording, earlier orders with the
same words, corrections) is stronger than name similarity. Never apply a general rule such as "chhota means the
smallest pack": the same words can mean different products for different retailers. Only choose a SKU from the
candidates. If two candidates fit equally or the evidence conflicts, set needs_clarification to true.
reason: one short business sentence (evidence), no step-by-step thinking."""

COMPARE_SCHEMA = {
    "name": "product_matches",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["matches"],
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["line", "sku", "confidence", "needs_clarification", "reason"],
                    "properties": {
                        "line": {"type": "integer"},
                        "sku": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "needs_clarification": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                },
            }
        },
    },
}


def compare_candidates(lines: list[dict]) -> dict[int, dict]:
    """`lines`: [{"line": i, "words": ..., "candidates": [{"sku", "product", "evidence": [...]}]}].
    Returns {line: {"sku", "confidence", "needs_clarification", "reason"}} (lines it skipped are missing)."""
    payload = {
        "model": settings.OPENAI_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": COMPARE_PROMPT},
                     {"role": "user", "content": json.dumps({"lines": lines}, ensure_ascii=False)}],
        "response_format": {"type": "json_schema", "json_schema": COMPARE_SCHEMA},
    }
    data, _ = _structured(payload)
    out: dict[int, dict] = {}
    for m in data.get("matches", []) if isinstance(data, dict) else []:
        try:
            out[int(m["line"])] = {
                "sku": m.get("sku"), "confidence": min(max(float(m.get("confidence") or 0), 0.0), 1.0),
                "needs_clarification": bool(m.get("needs_clarification")), "reason": str(m.get("reason") or ""),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return out

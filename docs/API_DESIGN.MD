# API Design — DukaanFlow

## 1. API Conventions

- Base URL: `/api/v1`
- API format: REST
- Request/response format: JSON
- Authentication: JWT Bearer Token
- Content-Type: `application/json`
- Use UUIDs for resource IDs.
- Use ISO 8601 timestamps.
- All protected endpoints require a valid JWT.
- All endpoints must enforce role-based access control.

### Standard Success Response

```json
{
  "success": true,
  "message": "Products fetched successfully",
  "data": {}
}
```

### Standard Error Response

```json
{
  "success": false,
  "message": "Insufficient stock",
  "error_code": "INSUFFICIENT_STOCK",
  "details": {}
}
```

## 2. User Roles

| Role | Access |
|---|---|
| RETAILER | Own catalogue, prices, cart, orders, credit and order history |
| SALESMAN | Assigned retailers and orders placed on their behalf |
| ORDER_DESK | Review, correct, approve and reject orders |
| ADMIN | Distributor-wide management and dashboard |

Never trust a retailer ID supplied by the frontend without checking the authenticated user's permissions.

## 3. Authentication APIs

Two login methods return the same token format, both identified by the 10-digit mobile number:

- Phone + OTP: RETAILER users only. The OTP is emailed to the email address registered on the account.
- Phone + password: SALESMAN, ORDER_DESK and ADMIN users only.

Temporary authentication state lives only in Upstash Redis; every check is an atomic Lua script.

| Rule | Value |
|---|---|
| OTP | 6 random digits (`secrets`), stored as a keyed hash (`otp:{phone}`) |
| OTP expiry | 120 seconds (Redis TTL) |
| Incorrect OTP attempts | 5 per OTP (`otp_attempts:{phone}`); then the OTP is deleted |
| Resend cooldown | 60 seconds per phone number (`otp_cooldown:{phone}`) |
| OTP requests | 5 per phone number per 15 minutes (`otp_requests:{phone}`); resending or logging in does not reset it |
| Password attempts | 5 per phone number per 15 minutes (`login_attempts:{phone}`), counted before the password is checked; a successful login clears it |

Requesting a new OTP replaces the previous one. A verified OTP is deleted and cannot be reused. OTPs are never stored in PostgreSQL. If Redis is unavailable, OTP and password login return `AUTH_SERVICE_UNAVAILABLE` (503) rather than skipping the limits.

Phone numbers are not revealed: rate limits apply to every number before any account lookup, and `send-otp` returns the same response for registered, unregistered, inactive and non-retailer numbers. The one exception: if the OTP email cannot be sent for a registered retailer, no usable OTP is left and `OTP_DELIVERY_FAILED` (503) is returned, so success is never reported falsely.

### POST `/auth/send-otp`
Request an OTP. One is generated and emailed to the account's registered email only if the number belongs to an active RETAILER.

Request:
```json
{
  "phone": "9876543210"
}
```

Response (same for every valid number):
```json
{
  "success": true,
  "message": "If this number is registered, an OTP will be sent to the email address on the account.",
  "data": {
    "phone": "9876543210",
    "channel": "email",
    "expires_in": 120,
    "resend_after": 60
  }
}
```

Errors: `VALIDATION_ERROR` (422, not a 10-digit Indian mobile number), `RATE_LIMIT_EXCEEDED` (429, `details.reason` is `RESEND_COOLDOWN` or `OTP_REQUEST_LIMIT`, `details.retry_after` and a `Retry-After` header give the seconds to wait), `OTP_DELIVERY_FAILED` (503, the retailer has no registered email, or Brevo did not accept the email; no usable OTP is left, try again later), `AUTH_SERVICE_UNAVAILABLE` (503). A 200 means Brevo accepted the email, not that it reached the inbox.

Email: subject "Your DukaanFlow Login OTP", from `BREVO_SENDER_NAME <BREVO_SENDER_EMAIL>`, plain text plus a simple branded HTML version: "Your DukaanFlow verification code is: {OTP}. This OTP is valid for 2 minutes. Do not share this code with anyone."

### POST `/auth/verify-otp`
Verify the OTP and issue a JWT.

Request:
```json
{
  "phone": "9876543210",
  "otp": "123456"
}
```

Response data (same for `/auth/login`):
```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "name": "Retailer Name",
    "phone": "9876543210",
    "email": null,
    "role": "RETAILER",
    "retailer_id": "uuid",
    "is_active": true
  }
}
```

Errors: `INVALID_OTP` (401, `details.remaining_attempts`), `OTP_EXPIRED` (401, expired, already used or never requested), `OTP_ATTEMPTS_EXCEEDED` (429, the OTP is deleted; request a new one), `ACCOUNT_DISABLED` (403), `AUTH_SERVICE_UNAVAILABLE` (503).

OTP delivery (`app/modules/auth/mailer.py`, selected with `EMAIL_PROVIDER`):

- `brevo`: Brevo transactional email, `POST https://api.brevo.com/v3/smtp/email` with header `api-key: <BREVO_API_KEY>` and JSON `{"sender": {"name", "email"}, "to": [{"email"}], "subject", "textContent", "htmlContent"}`; success is HTTP 201 `{"messageId": ...}`. Sent asynchronously with `httpx.AsyncClient` (20 s timeout).
- `mock`: development and tests only; writes the OTP to the backend log.

Outside development the app refuses to start with `EMAIL_PROVIDER=mock`, so there is no fallback to mock email. Delivery failures are logged without the OTP or API key; email addresses are masked in logs.

### POST `/auth/login`
Phone + password login for SALESMAN, ORDER_DESK and ADMIN. Passwords are stored as Argon2id hashes.

Request:
```json
{
  "phone": "9876543210",
  "password": "password"
}
```

Errors: `INVALID_CREDENTIALS` (401, same response for an unknown number, a wrong password or a retailer account), `ACCOUNT_DISABLED` (403), `RATE_LIMIT_EXCEEDED` (429, `details.reason` = `LOGIN_ATTEMPTS`, with `Retry-After`), `AUTH_SERVICE_UNAVAILABLE` (503).

### GET `/auth/me`
Return the authenticated user's profile and role.

### Access tokens
- JWT signed with `JWT_SECRET_KEY` / `JWT_ALGORITHM`, valid for `ACCESS_TOKEN_EXPIRE_MINUTES` (30). No refresh tokens in V1.
- Claims: `sub` (user UUID), `role`, `iat`, `exp`.
- Sent as `Authorization: Bearer <token>`.
- Every request reloads the user from PostgreSQL: the account must still be active (`ACCOUNT_DISABLED`, 403) and its role must match the token (`UNAUTHORIZED`, 401). Expired tokens return `TOKEN_EXPIRED` (401).

## 4. Product Catalogue APIs

### GET `/products`
Fetch a retailer's catalogue with their prices. RETAILER: always their own (`retailer_id` of another shop → `FORBIDDEN`). SALESMAN / ORDER_DESK / ADMIN: `retailer_id` is required (422 without it) and must be a retailer they may access. Only active products in active categories that have a current dealer price for the retailer are listed.

Query parameters:
- `search` (name, brand or SKU, case-insensitive; max 100 chars)
- `category_id`
- `page` (default 1)
- `limit` (default 20, max 100)
- `has_scheme` (`true`: only products with a scheme active now; used by the retailer's Offers & Schemes section)

Response data:
```json
{
  "items": [
    {
      "id": "uuid", "sku": "SKU-BS-075", "name": "Glucose Biscuit 75g", "brand": "Sunrise Foods",
      "category": {"id": "uuid", "name": "Biscuits"},
      "pack_size": "75g", "units_per_case": "96.000", "base_unit": "piece", "order_unit": "case",
      "gst_rate": "5.00", "image_url": null,
      "price": {"dealer_price": "7.94", "price_basis": "PIECE", "tax_inclusive": false, "case_price": "762.24"},
      "stock_cases": "340.000", "in_stock": true,
      "schemes": [{"id": "uuid", "scheme_type": "FREE_GOODS", "min_quantity": "10.000", "free_quantity": "1.000", "discount_percentage": "0.00"}]
    }
  ],
  "page": 1, "limit": 20, "total": 10
}
```
`case_price` is the dealer price for one order unit before GST and schemes, for display only; order totals are always calculated by the backend when an order is placed. `schemes` lists the schemes active now.

### GET `/products/categories`
Active categories (`[{"id", "name"}]`), for the catalogue filter. Any signed-in user.

Each scheme in `GET /products` also has a `description` (e.g. "Buy 10 get 1 free", "3% off on 5+").

### GET `/products/{product_id}`
Fetch one product with its retailer-specific price, stock and active schemes (same item shape and access rules as `GET /products`; staff pass `retailer_id`). `PRODUCT_NOT_FOUND` (404) if it is inactive or has no current price for the retailer.

Image fields on every product: `image_url` (800 px) and `thumbnail_url` (400 px) are Cloudinary delivery URLs with `f_auto,q_auto,c_pad,b_white` (automatic format and quality, whole pack padded on white, never cropped); both are `null` when no image is uploaded, and the frontend then shows a pack illustration.

### POST `/products/{product_id}/image`
ADMIN only. `multipart/form-data` with `file` (JPEG, PNG or WebP, checked by content; max 5 MB). The backend uploads it to Cloudinary with a signed request (public_id `CLOUDINARY_FOLDER/<sku>`, overwriting the previous image) and stores the returned `secure_url` in `products.image_url` and the `public_id` in `products.image_public_id`.

Response data: `{"product_id", "image_public_id", "image_url", "thumbnail_url"}`.

Errors: `FORBIDDEN` (403), `PRODUCT_NOT_FOUND` (404), `VALIDATION_ERROR` (422, wrong type or too large), `IMAGE_STORAGE_NOT_CONFIGURED` (503, Cloudinary settings missing), `IMAGE_UPLOAD_FAILED` (502, Cloudinary refused or unreachable; nothing is saved).

Rules:
- Retailers must only see their own dealer prices.
- Do not expose another retailer's pricing.
- Do not allow the frontend to determine final prices or discounts.

## 5. Retailer APIs

### GET `/retailers/me`
RETAILER only. The signed-in retailer's profile for the Profile page:

```json
{
  "id": "uuid", "shop_name": "Sharma Kirana Store", "owner_name": "Ramesh Sharma", "phone": "9000000101",
  "address": "12, Napier Town Main Road", "city": "Jabalpur", "gstin": "23AAAPS1234A1Z5",
  "assigned_salesman": {"name": "Sunil Yadav", "phone": "9000000003"},
  "credit": {"credit_limit": "50000.00", "current_outstanding": "35000.00", "reserved_for_review": "0", "available_credit": "15000.00"},
  "can_place_orders": true,
  "purchases": {"total_orders": 3, "confirmed_orders": 1, "total_purchased": "8164.80",
                "under_review_orders": 1, "under_review_amount": "4082.40", "rejected_orders": 1}
}
```

`total_purchased` is the sum of APPROVED (confirmed) orders only; open orders (PENDING, CREDIT_HOLD, ON_HOLD) are reported separately as under review; rejected orders never count. `available_credit` = `credit_limit - current_outstanding - reserved_for_review` (orders under review hold their amount until accepted or rejected). `can_place_orders` is false when no credit is available.

### GET `/retailers/me/credit`
Return:
- Credit limit
- Current outstanding
- Available credit

### GET `/retailers`
Order desk/admin can search and list retailers.
Salesmen can only access assigned retailers.

### GET `/retailers/{retailer_id}`
Return retailer details if the authenticated user has permission.

## 6. AI Order Capture APIs

Flow: text → LLM extraction (`app/modules/ai_orders/llm.py`) → backend SKU matching (`matcher.py`) → stored draft (`ai_extractions`) → user review → `confirm` places the order through the normal order path. AI never creates, prices or approves an order, and never sees prices, stock or credit.

### POST `/ai-orders/extract`
RETAILER (own shop) or SALESMAN (assigned shop, `retailer_id`). Reads a free-text order into a draft; creates no order.

Request: `{"message": "bhaiya 5 peti biscuit chhota, 2 peti washing powder 1 kilo, chai patti 250 wala 1 peti"}` (1–2000 chars).

Response data:
```json
{
  "extraction_id": "uuid",
  "status": "PENDING",
  "original_message": "...",
  "model_name": "gpt-4o-mini",
  "items": [
    {
      "id": "uuid",
      "original_text": "5 peti biscuit chhota",
      "extracted_name": "glucose biscuit small",
      "quantity": "5.000",
      "unit": "case",
      "product": {"product_id": "uuid", "sku": "SKU-BS-075", "name": "Glucose Biscuit 75g", "pack_size": "75g", "order_unit": "case"},
      "confidence": "0.900",
      "alternatives": [{"product_id": "uuid", "sku": "SKU-BS-150", "name": "Glucose Biscuit 150g", "pack_size": "150g", "confidence": 0.71}],
      "requires_clarification": false,
      "clarification": null
    }
  ]
}
```

Matching rules:
- The LLM (OpenAI Chat Completions, Structured Outputs, temperature 0) gets the message, the retailer's own catalogue (SKU, name, brand, category, pack, order unit, the retailer's saved wording) and recently ordered SKUs. It returns per line: original text, English description, quantity, unit (`case`/`piece`/null, never assumed) and up to 3 candidate SKUs with a confidence.
- The backend accepts only SKUs from that catalogue, applies the retailer's alias when it is exactly the line's product wording, and uses RapidFuzz for alternatives or as a fallback.
- `requires_clarification` (with a `clarification` message) when: no product, confidence < 0.75, no quantity, no unit, or a unit other than the product's order unit (pieces are never converted to cases).

Errors: `AI_NOT_CONFIGURED` (503, `OPENAI_API_KEY` is not set; there is no mock fallback), `AI_SERVICE_UNAVAILABLE` (503, provider error or unreadable response), `FORBIDDEN` (403, other roles), `VALIDATION_ERROR` (422).

### AI order capture V1 — retailer-specific product understanding

`app/modules/ai_orders/graph.py` runs one small LangGraph pipeline per message: `load_retailer_context` (the retailer's priced catalogue, saved wordings, earlier AI lines and what they became, product frequency over 90 days) → `extract_order` (OpenAI Structured Outputs reads text or a photo into lines: words, quantity, unit, candidate SKUs) → `find_product_candidates` (`matcher.find_candidates`: catalogue similarity, pack-size numbers, the retailer's saved wording, earlier AI lines with the same words, Order Desk corrections, frequency, the AI's reading) → `match_products` (only close calls go to a second OpenAI call that may pick among the candidates; an SKU outside them is ignored) → `validate_units` (`matcher.decide`: confidence, evidence, alternatives, clarification; quantities and units never assumed or converted) → `build_draft_order` (stored draft). There is no global meaning for words like "chhota": the same words can map to different products for different retailers; conflicting history caps confidence at 0.6 and asks for clarification. Each line stores `evidence` (business facts, never model reasoning), `alternatives`, `clarification_reason`, and, once placed, `order_item_id`; the order line's current product (after any Order Desk correction) is the learning signal for the next messages. An Order Desk product correction of an AI line also saves the retailer's words as their alias. The draft is reviewed by the retailer, then placed with `/confirm` (source AI) and reviewed by the Order Desk (Accept, Edit line, Request clarification, Reject); stock, price, scheme and credit are always the backend's.

### POST `/ai-orders/extract-media`
Multipart: `kind` (`image` | `voice`), `file`, optional `retailer_id` (salesmen). Image: JPEG/PNG/WebP ≤ 5 MB, read by the vision model (`original_message` = the text it read). Voice: webm/ogg/mp3/m4a/wav ≤ 10 MB, transcribed with `OPENAI_TRANSCRIBE_MODEL` (default `gpt-4o-mini-transcribe`), then read like a message. Returns the draft with `input_type` `IMAGE` / `VOICE`. Never creates an order.

### GET `/ai-orders`
The retailer's AI drafts that have not been placed as orders yet (newest 20; SALESMAN passes `retailer_id`): `[{extraction_id, created_at, original_message, item_count, needs_clarification}]`. A draft is not an order; once placed it becomes an order (source AI) that the Order Desk accepts or rejects.

### GET `/ai-orders/{extraction_id}`
The stored draft (same shape), for its retailer / assigned salesman only.

### POST `/ai-orders/{extraction_id}/confirm`
Place the reviewed draft as an order (`source` AI). Request: `{"items": [{"extraction_item_id": "uuid or null", "product_id": "uuid", "quantity": 5, "unit": "case"}], "remarks": null}`. Items without `extraction_item_id` were added by the user. Validated, priced and stock-checked exactly like `POST /orders`; returns the order (201). When the user chose a different product than the match, the line's wording (without quantity, unit and filler words) is saved as that retailer's alias. A confirmed draft cannot be confirmed again (`INVALID_EXTRACTION_STATUS`, 409).

## 7. Order APIs

Statuses: `PENDING` (under review), `CREDIT_HOLD` (above available credit), `ON_HOLD` (offline order whose data changed, or held by the Order Desk), `CLARIFICATION_REQUIRED` (the desk asked the retailer/salesman), `APPROVED` (confirmed), `REJECTED`. Every action checks role and retailer access in the service.

**Which orders the Order Desk reviews:** all of them. Catalogue orders (`POST /orders`, source MANUAL), salesman orders (source SALESMAN, online or synced offline) and AI-captured orders (`POST /ai-orders/{id}/confirm`, source AI) are created `PENDING` (or `CREDIT_HOLD` / `ON_HOLD`) and wait for the Order Desk to accept (`/approve`: stock deducted, credit debited, `APPROVED`) or reject (`/reject`, reason required). While waiting they hold their total from the retailer's available credit. Retailers still cannot place an order above their available credit; a salesman order above it arrives as `CREDIT_HOLD`.

**Available credit** = `credit_limit - current_outstanding - reserved_for_review`, where `reserved_for_review` is the total of the retailer's orders awaiting the Order Desk (PENDING, ON_HOLD, CLARIFICATION_REQUIRED). So an order uses credit as soon as it is placed: confirmed orders through `current_outstanding`, orders under review by holding their amount; rejecting one releases its hold immediately, confirming it moves the amount into `current_outstanding`. CREDIT_HOLD orders hold nothing (they are already above the credit).

### POST `/orders/quote`
Price a cart without placing it (RETAILER / SALESMAN). Same request as `POST /orders`. Uses the same pricing, scheme engine and stock data as order creation; stock shortages are reported per line instead of refusing.

Response data: `{"lines": [{product_id, sku, name, pack_size, order_unit, quantity, free_quantity, price_basis, unit_price, tax_inclusive, gst_rate, discount_percentage, discount_amount, taxable_amount, gst_amount, line_total, scheme: {scheme_type, description, min_quantity, free_quantity, discount_percentage} | null, available_stock, stock_ok}], "totals": {subtotal, discount_total, taxable_amount, gst_amount, grand_total}, "can_order": true, "available_credit": "15000.00", "within_credit": true}`. `can_order`: every line is in stock. `within_credit`: the total fits the retailer's available credit (a retailer cannot place the order otherwise).

### POST `/orders`
Create an order from the cart (RETAILER for their own shop; SALESMAN with `retailer_id`). Returns the order (201).

Request:
```json
{
  "items": [{"product_id": "uuid", "quantity": 10, "unit": "case"}],
  "remarks": "Deliver in the morning"
}
```

The backend calculates prices, schemes, GST and totals; any price, discount or total fields sent by the client are ignored. **Credit rule:** a RETAILER cannot place an order whose total is above their available credit (see above): it is refused with `CREDIT_LIMIT_EXCEEDED` (409, `details.grand_total`, `details.available_credit`, message tells them to contact their salesman or the order desk). This also applies to `POST /ai-orders/{id}/confirm`. A SALESMAN's order above the credit is created as `CREDIT_HOLD` for the Order Desk. Quantities must be > 0 and in the product's order unit (other units are refused, not converted); each product once per order; paid + free cases must be in stock (`INSUFFICIENT_STOCK`, 409). Orders above the retailer's available credit are created as `CREDIT_HOLD`.

### GET `/orders`
Orders visible to the user (RETAILER: own; SALESMAN: assigned retailers; ORDER_DESK/ADMIN: all), newest first.

Query: `status` (repeatable), `source` (MANUAL, AI, SALESMAN), `search` (order number or shop name), `page`, `limit` (max 100).
Response data: `{"items": [{id, order_number, status, source, retailer: {id, shop_name, city}, item_count, grand_total, created_at}], "page", "limit", "total"}`.

### GET `/orders/{order_id}`
Order with retailer details (shop, owner, phone, address, city, GSTIN), `remarks`, `hold_reason`, `rejection_reason`, `clarification_message`, `approved_by`, `tally_exported_at`, `ai` (`{extraction_id, original_message}` for AI orders), totals and items. Each item carries its snapshots: name, SKU, paid/free quantity, price basis, unit price, `tax_inclusive`, discount, GST, line total, `scheme` (from `scheme_snapshot`) and its `corrections`.

### PATCH `/orders/{order_id}/items/{item_id}`
ORDER_DESK/ADMIN correction of an open order's line: `{"new_product_id": "uuid?", "new_quantity": 5, "unit": "case?", "reason": "...", "save_alias": "retailer wording?"}`. `reason` is required. The line is re-priced with the prices and schemes effective when the order was placed and recorded in `order_corrections` and the order history (old and new product, quantity, line and order totals). A hold or clarification request stays in place. Returns the updated order.

### POST `/orders/{order_id}/hold`
ORDER_DESK/ADMIN: `{"reason": "..."}` (required). Open order → `ON_HOLD`. No stock or credit change.

### POST `/orders/{order_id}/approve`
ORDER_DESK/ADMIN confirmation: `{"credit_override_reason": null, "acknowledge_changes": false}`. Rechecks stock (paid + free) and credit under row locks, deducts stock, debits credit, sets `APPROVED` and records who confirmed it (`approved_by`, `approved_at`, history). Above available credit it is refused (`CREDIT_LIMIT_EXCEEDED`, 409) unless `credit_override_reason` is given (stored in the ledger entry). A product that is no longer active refuses it (`PRODUCT_NOT_FOUND`, 409). If a line's current dealer price or scheme benefit differs from the order's snapshot, it is refused with `ORDER_DATA_CHANGED` (409, `details.changes`) unless `acknowledge_changes` is true; the order then keeps its own prices (never changed silently).

### POST `/orders/{order_id}/clarification`
ORDER_DESK/ADMIN: `{"message": "..."}` (required). Open order → `CLARIFICATION_REQUIRED` with `clarification_message`, lines unchanged, credit still held. The retailer and salesman see the message on the order. It can then be corrected, confirmed, rejected or asked again.

### POST `/orders/{order_id}/reject`
ORDER_DESK/ADMIN, one click: body optional (`{"reason": "..."}`); without a reason "Rejected by the order desk" is stored and shown to the retailer and salesman. The user and time are in the order history. The Order Desk screen offers only Accept and Reject (no clarification or correction forms); the clarification and correction endpoints remain in the API, and clarification orders are listed under Incoming.

Rules:
- Only ORDER_DESK and ADMIN can correct, hold, ask for clarification, approve or reject (`FORBIDDEN`, 403 otherwise).
- Only open orders (PENDING, CREDIT_HOLD, ON_HOLD, CLARIFICATION_REQUIRED) can be changed (`INVALID_ORDER_STATUS`, 409).
- Retailers cannot see other retailers' orders (`FORBIDDEN`, 403).
- Approval atomically updates inventory, stock movements and credit; rejected or held orders never deduct stock.
- Orders keep their original price, scheme and tax snapshots.

## 8. Order Desk APIs

All ORDER_DESK/ADMIN only (`FORBIDDEN` otherwise). These endpoints only read; order actions are the `/orders/{id}/…` endpoints above. Module: `app/modules/order_desk/`.

### GET `/order-desk/summary`
Order counts per status, e.g. `{"PENDING": 3, "CREDIT_HOLD": 1, "ON_HOLD": 0, "CLARIFICATION_REQUIRED": 1, "APPROVED": 12, "REJECTED": 1}`.

### GET `/order-desk/overview`
`received_today`, `pending_review` (PENDING + CREDIT_HOLD + ON_HOLD), `awaiting_clarification`, `confirmed_today`, `confirmed_total`, `rejected_today`, `rejected_total`, `with_stock_or_credit_issues` (open orders), `not_exported` (confirmed, not yet in Tally). Today = IST day.

### GET `/order-desk/orders`
One section: `view` = `incoming` (PENDING, CREDIT_HOLD, ON_HOLD), `clarification`, `confirmed`, `rejected` or `all`. Query: `status` (repeatable, within the view), `source`, `search` (order number, shop name, owner name or mobile), `salesman_id` (orders the salesman placed, or placed by others for the salesman's shops), `from_date`/`to_date` (IST days of placement; of confirmation in `confirmed`), `exported` (true/false), `sort` (`newest`, `oldest`, `value_desc`, `value_asc`), `page`, `limit` (≤ 50).

Each row: order number, status, source, retailer (shop, owner, phone, city), `salesman` (who placed it, else the shop's salesman), `created_by`, item count, total, dates, `approved_by`, `created_offline`, `tally_exported_at`, `reason` (rejection reason / clarification message / hold reason), `warnings` and `last_action` (latest history entry).

**Warnings** (open orders only; `severity` `error` blocks confirmation as it is, `warning` needs a look): `INSUFFICIENT_STOCK`, `CREDIT_LIMIT_EXCEEDED`, `PRICE_CHANGED` / `SCHEME_CHANGED` (since placement), `PRODUCT_INACTIVE`, `PRICE_NOT_AVAILABLE`, `OFFLINE_DATA_CHANGED` (an offline order's `hold_reason`), `AI_MATCH_UNCERTAIN` (an AI line below 80% confidence or that needed clarification), `POSSIBLE_DUPLICATE` (same shop, same products and quantities within 24 hours, not rejected). Warnings never change an order.

### GET `/order-desk/orders/{order_id}`
Review data: `order` (as `GET /orders/{id}`), `salesman`, `credit` (limit, outstanding, reserved for review, available), `stock` per line (`needed` paid + free, `available`, `ok`), `warnings`, `ai_lines` (original text, extracted name, quantity, confidence, clarification flag) and `history` (all order events, oldest first).

### GET `/order-desk/salesmen`
Salesmen for the filters (`id`, `name`, `phone`).

### GET `/order-desk/dispatch`
Loading list of confirmed orders, by IST confirmation date (`from_date`, `to_date`; default today) and optional `salesman_id`: `products` (paid, free and total cases per product), and `beats` per salesman (V1 records no routes or vans) with their products and `stops`, one per shop (address, phone, its orders and combined quantities).

## 8a. Salesman APIs

SALESMAN only. Every retailer is checked against the salesman's assignments (`retailers.assigned_salesman_id`); unassigned or inactive retailers are refused (`FORBIDDEN`, 403) or left out. Salesman orders use the normal order APIs (`POST /orders/quote`, `POST /orders` with `retailer_id`; `GET /orders?created_by_me=true` for their history, `GET /orders?retailer_id=` for one shop).

### GET `/salesman/sync-bundle`
Everything the salesman app stores on the phone (IndexedDB) for offline work: `synced_at`, `retailers` (id, shop, owner, shop contact `phone`, `registered_mobiles` (the login mobile(s) of the retailer's account, `users.phone`), address, city, GSTIN, `last_order_at`, `credit` {limit, outstanding, reserved_for_review, available}, last 5 `recent_orders`), `categories`, `products` (facts, stock, active schemes with descriptions, image URLs) and `prices` (`retailer_id -> product_id -> {dealer_price, price_basis, tax_inclusive, case_price}`).

### GET `/salesman/home`
Today's work from the database (IST calendar day): `{date, assigned_retailers, visits_today, orders_today, todays_visits: [{id, retailer_id, shop_name, started_at, ended_at, outcome}]}`. The app adds visits/orders still waiting on the phone, and keeps the last copy for offline use.

### POST `/salesman/visits`
Create or update a shop visit; `id` is generated on the phone, so re-sending is safe. Body: `{id, retailer_id, started_at, ended_at, outcome: "ORDER_PLACED" | "NO_ORDER" | null, client_order_id}`. The order placed during the visit is linked by its `client_order_id` once it has synced.

### Offline order sync (`POST /orders`)
Extra fields for orders created on a phone: `client_order_id` (unique, 8–64 chars), `created_offline`, `client_created_at`, and per item `expected_unit_price` (the price the phone showed) and `expected_scheme_ids` (the product's active schemes the phone showed). Neither is ever used for pricing; they only detect changes.
- **Idempotent:** the same `client_order_id` from the same user returns the order already created (201, same id) instead of a duplicate; another user's id is refused (409). Concurrent duplicates are caught by the unique constraint.
- **Review rules:** a price that differs from `expected_unit_price`, a scheme benefit for that quantity that differs from what `expected_scheme_ids` would have given (a scheme that could not have applied to the quantity is ignored), or — for `created_offline` orders — a stock shortage does not refuse or change the order: it is created `ON_HOLD` with `hold_reason` listing each issue, for the Order Desk. Above the retailer's credit it goes to `CREDIT_HOLD` (existing rule). Products that are inactive or unpriced are refused (`PRODUCT_NOT_FOUND` / `PRICE_NOT_AVAILABLE`); the phone keeps the order as "Sync failed" for retry or discard.
- Otherwise the normal rules apply: within credit it waits for the Order Desk as `PENDING`; above credit it goes to `CREDIT_HOLD`.
- Orders now include `created_by` `{id, name, role}`, `created_offline`, `client_created_at`, `client_order_id`.

## 8b. Admin APIs

All under `/admin`, ADMIN only: the router requires the ADMIN role (checked against the database user) and every admin service checks it again, so other roles get `FORBIDDEN` (403). Module: `app/modules/admin/` (`people.py` retailers/credit/salesmen/assignments/users, `catalog.py` categories/brands/products/prices/schemes/stock, `monitoring.py` dashboard/order desk/AI/sync/audit/settings, `reports.py`). Money and quantities are decimal strings. Every change is written to `audit_logs` (who, action, entity, details with old/new values); order actions stay in `order_events`. The Admin does not replace the Order Desk workflow (order actions remain the `/orders/{id}/…` endpoints, which ADMIN may use to intervene) and cannot bypass the human confirmation of AI orders.

| Method & path | Purpose |
|---|---|
| GET `/admin/dashboard` | Counts (retailers, salesmen, products, orders today, pending, clarification, confirmed, rejected), confirmed value (today / 30 days / all), outstanding credit, low stock, retailers not ordering recently, recent orders / retailers / products / salesman visits |
| GET/POST `/admin/retailers`, GET/PATCH `/admin/retailers/{id}` | List (search shop/owner/mobile/city/ID; `status` active/inactive/restricted; `salesman_id` or `none`; `sort` name/newest/outstanding/last_order/purchased), create (retailer + credit account + RETAILER login with `email` for OTP codes), details (credit, purchases, logins, recent orders), edit / assign salesman / activate-deactivate (deactivation also disables the retailer's login) |
| PATCH `/admin/retailers/{id}/credit` | `{credit_limit?, ordering_restricted?, reason?}`: set the limit; pause ordering (reason required) or allow it again |
| GET `/admin/retailers/{id}/credit-history`, `/prices` | Ledger + limit/pause changes; every active product with default price, the retailer's own price and active schemes |
| GET `/admin/salesmen`, `/admin/salesmen/{id}` | 30-day visits/orders/value/offline orders, assigned shops, visits, sync status and sync failures |
| POST `/admin/assignments` | `{salesman_id \| null, retailer_ids}`: assign (moves from the previous salesman; only active salesmen) or unassign |
| GET/POST `/admin/users`, GET/PATCH `/admin/users/{id}`, POST `/admin/users/{id}/reset-password` | Staff accounts (SALESMAN/ORDER_DESK/ADMIN with password; retailer logins come with their retailer). Rules: no self role change/deactivation, at least one active admin, a salesman with shops must hand them over before deactivation/role change, retailer logins cannot become staff. Deactivation and role changes end sessions at once. Activity: last login, orders, desk actions, visits, admin changes |
| GET/POST `/admin/categories`, PATCH `/admin/categories/{id}`; same for `/admin/brands` | Create, rename, activate/deactivate. Inactive categories hide their products; renaming a brand cascades to products |
| GET/POST `/admin/products`, GET/PATCH `/admin/products/{id}` | List (search, category, brand, status, stock low/out), create (SKU upper-cased and unique, active brand, opening stock as a RESTOCK movement, optional default price), detail (stock, default price, price history, schemes, recent movements), edit/activate. Image: `POST /products/{id}/image` |
| PUT `/admin/prices`, DELETE `/admin/prices?product_id&retailer_id` | Set a default price (`retailer_id` null) or a retailer's own price from now on (the current row is closed, so rows are the price history); end a retailer's own price |
| GET/POST `/admin/schemes`, PATCH `/admin/schemes/{id}` | `state` active/upcoming/expired/inactive/all; create one scheme per product in `product_ids` (FREE_GOODS needs free_quantity, SLAB_DISCOUNT a discount); a product may have only one active scheme in overlapping dates (`SCHEME_CONFLICT`) |
| GET `/admin/stock`, POST `/admin/stock/{product_id}/adjust`, GET `/admin/stock/{product_id}/history` | `{mode: add\|remove\|set, quantity, reason}` (reason required, never below 0); history with stock before/after, user, reason, order |
| GET `/admin/order-desk` | Queue counts, stock/credit issues, corrected orders, Tally exported / not, actions per desk user (30 days), recent desk actions |
| GET `/admin/ai-orders` | Extractions with message, lines (confidence, alternatives, clarification), resulting order and status; stats |
| GET `/admin/sync` | Per-salesman sync status (from `POST /salesman/sync-status`), offline orders, conflicts (held offline orders), failed syncs (refused device orders) |
| GET `/admin/audit` | `source` all/master/orders, `entity_type`, `action`, `actor_id`, `search`, `from_date`, `to_date`; master-data audit and order history merged, newest first |
| GET/PUT `/admin/settings` | Business name/address/phone/GSTIN, `low_stock_cases`, `inactive_retailer_days`, `duplicate_window_hours`, `ai_low_confidence_percent` (used by the order desk warnings) |
| GET `/admin/reports`, `/admin/reports/{name}`, `/admin/reports/{name}/csv` | sales-by-date/-retailer/-salesman/-product/-category, source-breakdown, confirmed-vs-rejected, top-retailers, top-products, salesman-performance (with `from_date`/`to_date`, IST confirmation dates), low-stock, credit-outstanding, inactive-retailers |

Related changes: `POST /salesman/sync-status` (`{pending_orders, failed_orders, pending_visits, last_error}`, reported by the phone after each sync; `GET /salesman/sync-bundle` records `last_sync_at` and includes each retailer's `ordering_restricted_reason`). A salesman's device order the server refuses is logged as `SYNC_FAILED`. Orders for a retailer whose ordering is paused or who is inactive are refused with `ORDERING_RESTRICTED` (403) on every channel; `POST /orders/quote` and `GET /retailers/me` report `ordering_restricted_reason`. Products without a retailer-specific price use the default price.

## 9. Dashboard APIs

### GET `/dashboard/summary`
Return:
- Orders today
- Sales today
- Pending orders
- Credit-held orders
- Low-stock products
- Out-of-stock products
- Inactive retailers

### GET `/dashboard/inactive-retailers`
Return retailers who have not placed an order in the last 14 days.

ADMIN and authorized ORDER_DESK users only.

## 10. Tally Export APIs

### POST `/exports/tally`

ORDER_DESK/ADMIN. Body `{"order_ids": [..]?, "from_date"?, "to_date"?, "include_exported": false}`. Exports the chosen confirmed orders (by ids and/or IST confirmation dates) as the CSV below, sets `tally_exported_at` and adds an `EXPORTED` history entry to each. Orders already exported are skipped unless `include_exported` is true (an explicit re-export, recorded as such), so a repeated click never exports twice; nothing to export → `NOTHING_TO_EXPORT` (409). Header `X-Exported-Count`.

### GET `/exports/tally/orders.csv`

ORDER_DESK/ADMIN. Read-only download (does not mark orders exported). Confirmed (APPROVED) orders as a CSV download (UTF-8 with BOM), one row per order line, oldest first. Layout in `app/modules/exports/tally.py`.

Query: `from_date`, `to_date` (YYYY-MM-DD, inclusive, by confirmation date in IST).

Columns: Voucher Date (order date), Voucher Number, Confirmed On, Party Name, Party GSTIN, Party Address, Party City, Party Phone, SKU, Item Name, Billed Qty, Free Qty, Actual Qty, Unit, Rate, Rate Per (piece/case), Rate Includes GST (Yes/No; empty if not recorded), Discount %, Discount Amount, Taxable Value, GST Rate %, GST Amount, Line Amount, Scheme, Order Total.

All values come from the order snapshots. GST is not split into CGST/SGST/IGST (place of supply is not recorded). Text cells starting with `=`, `+`, `-` or `@` are prefixed with `'` so spreadsheets do not run them as formulas.

## 11. Important Business Rules

1. All money calculations happen on the backend using decimal/numeric values.
2. Product prices are retailer-specific.
3. Schemes are calculated by the backend.
4. Free quantities must be included in inventory deduction.
5. Stock is deducted only after successful approval.
6. Credit must be rechecked during approval.
7. Order items store immutable price, tax and product snapshots.
8. AI extraction always requires user review before order creation.
9. All sensitive resources require ownership or role checks.
10. Use database transactions for order approval.

## 12. Common Error Codes

| Error code | Meaning |
|---|---|
| UNAUTHORIZED | Missing or invalid token |
| TOKEN_EXPIRED | Access token has expired |
| INVALID_CREDENTIALS | Wrong phone number or password |
| ACCOUNT_DISABLED | User account is deactivated |
| INVALID_OTP | Incorrect OTP |
| OTP_EXPIRED | OTP expired, already used or not requested |
| OTP_ATTEMPTS_EXCEEDED | Too many incorrect OTP attempts |
| RATE_LIMIT_EXCEEDED | Too many requests; retry after `details.retry_after` seconds |
| AUTH_SERVICE_UNAVAILABLE | Redis (OTP and login limits) unavailable |
| OTP_DELIVERY_FAILED | The OTP email could not be sent (no registered email, or Brevo did not accept it) |
| FORBIDDEN | User lacks permission |
| VALIDATION_ERROR | Invalid request data |
| RESOURCE_NOT_FOUND | Requested resource does not exist |
| PRODUCT_NOT_FOUND | Product does not exist |
| AMBIGUOUS_PRODUCT | Product needs clarification |
| INSUFFICIENT_STOCK | Not enough stock |
| CREDIT_LIMIT_EXCEEDED | Order exceeds available credit |
| INVALID_ORDER_STATUS | Action not allowed for current status |
| ORDER_DATA_CHANGED | A price or scheme changed since the order was placed; confirm with `acknowledge_changes` or correct the lines |
| ORDERING_RESTRICTED | Retailer inactive or ordering paused by the Admin |
| CONFLICT | Value already used (mobile, email, SKU, name) or an Admin rule (e.g. last admin, salesman still has shops) |
| NOTHING_TO_EXPORT | No confirmed orders to export (already exported ones are skipped) |
| PRICE_NOT_AVAILABLE | No current dealer price for a product for this retailer |
| SCHEME_CONFLICT | More than one active scheme qualifies for a line (schemes are never combined) |
| INVALID_EXTRACTION_STATUS | AI draft already confirmed |
| AI_NOT_CONFIGURED | AI order capture needs `OPENAI_API_KEY` |
| AI_SERVICE_UNAVAILABLE | The AI provider failed or returned an unreadable response |
| IMAGE_STORAGE_NOT_CONFIGURED | Cloudinary settings are missing |
| IMAGE_UPLOAD_FAILED | Cloudinary did not accept the image |
| INTERNAL_SERVER_ERROR | Unexpected server error |

## 13. API Implementation Guidelines

- Keep endpoints versioned under `/api/v1`.
- Follow Router → Controller → Service → Repository.
- Pydantic schemas validate request and response data.
- Services contain business logic.
- Repositories contain database queries.
- Centralize exception handling.
- Paginate list endpoints.
- Never expose passwords, OTP hashes or internal secrets.
- Generate OpenAPI documentation through FastAPI.

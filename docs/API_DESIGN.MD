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
Return the authenticated retailer's profile.

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

### GET `/ai-orders/{extraction_id}`
The stored draft (same shape), for its retailer / assigned salesman only.

### POST `/ai-orders/{extraction_id}/confirm`
Place the reviewed draft as an order (`source` AI). Request: `{"items": [{"extraction_item_id": "uuid or null", "product_id": "uuid", "quantity": 5, "unit": "case"}], "remarks": null}`. Items without `extraction_item_id` were added by the user. Validated, priced and stock-checked exactly like `POST /orders`; returns the order (201). When the user chose a different product than the match, the line's wording (without quantity, unit and filler words) is saved as that retailer's alias. A confirmed draft cannot be confirmed again (`INVALID_EXTRACTION_STATUS`, 409).

## 7. Order APIs

Statuses: `PENDING` (submitted), `CREDIT_HOLD` (above available credit), `ON_HOLD` (held by the Order Desk), `APPROVED` (confirmed), `REJECTED`. Every action checks role and retailer access in the service.

### POST `/orders/quote`
Price a cart without placing it (RETAILER / SALESMAN). Same request as `POST /orders`. Uses the same pricing, scheme engine and stock data as order creation; stock shortages are reported per line instead of refusing.

Response data: `{"lines": [{product_id, sku, name, pack_size, order_unit, quantity, free_quantity, price_basis, unit_price, tax_inclusive, gst_rate, discount_percentage, discount_amount, taxable_amount, gst_amount, line_total, scheme: {scheme_type, description, min_quantity, free_quantity, discount_percentage} | null, available_stock, stock_ok}], "totals": {subtotal, discount_total, taxable_amount, gst_amount, grand_total}, "can_order": true}`.

### POST `/orders`
Create an order from the cart (RETAILER for their own shop; SALESMAN with `retailer_id`). Returns the order (201).

Request:
```json
{
  "items": [{"product_id": "uuid", "quantity": 10, "unit": "case"}],
  "remarks": "Deliver in the morning"
}
```

The backend calculates prices, schemes, GST and totals; any price, discount or total fields sent by the client are ignored. Quantities must be > 0 and in the product's order unit (other units are refused, not converted); each product once per order; paid + free cases must be in stock (`INSUFFICIENT_STOCK`, 409). Orders above the retailer's available credit are created as `CREDIT_HOLD`.

### GET `/orders`
Orders visible to the user (RETAILER: own; SALESMAN: assigned retailers; ORDER_DESK/ADMIN: all), newest first.

Query: `status` (repeatable), `source` (MANUAL, AI, SALESMAN), `search` (order number or shop name), `page`, `limit` (max 100).
Response data: `{"items": [{id, order_number, status, source, retailer: {id, shop_name, city}, item_count, grand_total, created_at}], "page", "limit", "total"}`.

### GET `/orders/{order_id}`
Order with retailer details (shop, owner, phone, address, city, GSTIN), `remarks`, `hold_reason`, `rejection_reason`, `ai` (`{extraction_id, original_message}` for AI orders), totals and items. Each item carries its snapshots: name, SKU, paid/free quantity, price basis, unit price, `tax_inclusive`, discount, GST, line total, `scheme` (from `scheme_snapshot`) and its `corrections`.

### PATCH `/orders/{order_id}/items/{item_id}`
ORDER_DESK/ADMIN correction of an open order's line: `{"new_product_id": "uuid?", "new_quantity": 5, "unit": "case?", "reason": "...", "save_alias": "retailer wording?"}`. The line is re-priced with the prices and schemes effective when the order was placed and recorded in `order_corrections`. Returns the updated order.

### POST `/orders/{order_id}/hold`
ORDER_DESK/ADMIN: `{"reason": "..."}` (required). Open order → `ON_HOLD`. No stock or credit change.

### POST `/orders/{order_id}/approve`
ORDER_DESK/ADMIN confirmation: `{"credit_override_reason": null}`. Rechecks stock (paid + free) and credit under row locks, deducts stock, debits credit, sets `APPROVED`. Above available credit it is refused (`CREDIT_LIMIT_EXCEEDED`, 409) unless `credit_override_reason` is given (stored in the ledger entry).

### POST `/orders/{order_id}/reject`
ORDER_DESK/ADMIN: `{"reason": "..."}` (required; shown to the retailer).

Rules:
- Only ORDER_DESK and ADMIN can correct, hold, approve or reject (`FORBIDDEN`, 403 otherwise).
- Only open orders (PENDING, CREDIT_HOLD, ON_HOLD) can be changed (`INVALID_ORDER_STATUS`, 409).
- Retailers cannot see other retailers' orders (`FORBIDDEN`, 403).
- Approval atomically updates inventory, stock movements and credit; rejected or held orders never deduct stock.
- Orders keep their original price, scheme and tax snapshots.

## 8. Order Desk APIs

The incoming queue is `GET /orders?status=PENDING&status=CREDIT_HOLD&status=ON_HOLD`.

### GET `/order-desk/summary`
ORDER_DESK/ADMIN: order counts per status, e.g. `{"PENDING": 3, "CREDIT_HOLD": 1, "ON_HOLD": 0, "APPROVED": 12, "REJECTED": 1}`.

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

### GET `/exports/tally/orders.csv`

ORDER_DESK/ADMIN. Confirmed (APPROVED) orders as a CSV download (UTF-8 with BOM), one row per order line, oldest first. Layout in `app/modules/exports/tally.py`.

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

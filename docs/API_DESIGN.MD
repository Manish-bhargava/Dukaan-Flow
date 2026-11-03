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
Fetch the product catalogue available to the authenticated retailer.

Query parameters:
- `search`
- `category_id`
- `page`
- `limit`

Return product details, retailer-specific price, available stock and applicable scheme.

### GET `/products/{product_id}`
Fetch one product with its retailer-specific price, stock and scheme.

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

### POST `/ai-orders/extract`

Accept a retailer's natural-language order and return extracted items with product matches.

Request:
```json
{
  "message": "bhaiya 5 peti biscuit chhota aur 2 peti washing powder",
  "language": "auto"
}
```

Response data:
```json
{
  "extraction_id": "uuid",
  "items": [
    {
      "original_text": "5 peti biscuit chhota",
      "product_name": "Glucose Biscuit 75g",
      "quantity": 5,
      "unit": "case",
      "matched_product_id": "uuid",
      "confidence": 0.94,
      "alternatives": [],
      "requires_clarification": false
    }
  ]
}
```

Rules:
- Use an LLM for structured text extraction only.
- Use backend matching logic to identify products.
- Use retailer-specific aliases and fuzzy matching where useful.
- Return alternatives when a match is uncertain.
- Ask for clarification when product or unit is ambiguous.
- Never create or approve an order directly from AI extraction.
- AI must not determine prices, schemes, stock, GST or credit.

### POST `/ai-orders/{extraction_id}/confirm`

Confirm corrected extraction items and create an order.

The backend must independently validate product IDs, quantities, retailer access, prices, schemes, stock and credit.

## 7. Order APIs

### POST `/orders`

Create an order manually from the retailer's cart.

Request:
```json
{
  "items": [
    {
      "product_id": "uuid",
      "quantity": 10,
      "unit": "case"
    }
  ],
  "remarks": "Deliver in the morning"
}
```

The backend calculates prices, schemes, GST and totals. Never trust client-submitted prices or discounts.

### GET `/orders`
List orders accessible to the authenticated user.

Optional filters:
- `status`
- `from_date`
- `to_date`
- `retailer_id` (only for authorized roles)
- `page`
- `limit`

### GET `/orders/{order_id}`
Fetch order details and item-level price, scheme and tax snapshots.

### PATCH `/orders/{order_id}/items`
Order desk can correct products or quantities before approval. Store every correction in `order_corrections`.

### POST `/orders/{order_id}/approve`
Approve a pending order after rechecking stock and credit.

### POST `/orders/{order_id}/reject`
Reject an order with a reason.

Rules:
- Only ORDER_DESK and ADMIN can approve/reject.
- Retailers cannot approve or modify submitted orders.
- Approval must atomically update inventory, stock movements and credit records.
- Prevent negative stock and concurrent overselling.
- Rejected orders must not deduct stock.
- Approved orders retain their original price, scheme and tax snapshots.

## 8. Order Desk APIs

### GET `/order-desk/queue`
Return pending orders and credit-held orders.

### GET `/order-desk/summary`
Return counts of pending, credit-held, approved and rejected orders.

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

Export approved orders in Tally-compatible CSV format.

Optional filters:
- `from_date`
- `to_date`

Include retailer details, GSTIN, product SKU, quantities, free quantities, price, discount, taxable amount, GST and final amount.

Only authorized ORDER_DESK and ADMIN users can export.

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

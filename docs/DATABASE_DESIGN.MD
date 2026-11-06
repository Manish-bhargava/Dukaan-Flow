# Database Design — DukaanFlow

## 1. Database Overview

- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Primary keys: UUID
- Money fields: NUMERIC, never FLOAT
- Timestamps: TIMESTAMPTZ
- Flexible AI extraction data: JSONB where appropriate.

Use foreign keys and database constraints to maintain data integrity.

## 2. Entity Relationships

Main relationships:

- One retailer can have one or more user accounts.
- One retailer can have multiple retailer-specific prices.
- One product can have multiple retailer-specific prices.
- One product can have multiple schemes over time.
- One retailer can place multiple orders.
- One order contains multiple order items.
- One product has one inventory record in the V1 single-warehouse setup.
- One retailer has one credit account.
- One order can have multiple correction records.
- One AI extraction can contain multiple extracted items.

## 3. Tables

### 3.1 users

Stores all platform users.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | VARCHAR(150) | User name |
| phone | VARCHAR(15) | Unique phone number |
| email | VARCHAR(255), nullable | Unique, stored lower case; retailers receive their login OTP here (login itself uses the phone number) |
| password_hash | VARCHAR(255) | Optional, if password login is added |
| role | VARCHAR(30) | RETAILER, SALESMAN, ORDER_DESK, ADMIN |
| retailer_id | UUID, nullable | Linked retailer for retailer accounts |
| is_active | BOOLEAN | Account status |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last update |

A retailer user must be linked to their retailer record. Salesman and admin accounts may not need a retailer_id.

### 3.2 otp_verifications

Stores OTP verification records.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| phone | VARCHAR(15) | Phone number |
| otp_hash | VARCHAR(255) | Hashed OTP |
| expires_at | TIMESTAMPTZ | Expiration |
| verified_at | TIMESTAMPTZ, nullable | Verification time |
| attempts | INTEGER | Failed attempts |
| created_at | TIMESTAMPTZ | Creation time |

Never store plain-text OTPs. Expired OTPs must not be accepted.

V1 status: not used. Retailer OTPs are sent by email and stored and verified only in Upstash Redis (see API_DESIGN.MD section 3); nothing is written to this table. It is kept for now and may be removed in a later migration.

### 3.3 retailers

Stores distributor customers (kirana shops).

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| shop_name | VARCHAR(200) | Shop name |
| owner_name | VARCHAR(150) | Owner name |
| phone | VARCHAR(15) | Contact number |
| address | TEXT | Shop address |
| city | VARCHAR(100) | City |
| gstin | VARCHAR(20), nullable | GST registration |
| assigned_salesman_id | UUID, nullable | Assigned salesman |
| is_active | BOOLEAN | Retailer status |
| created_at | TIMESTAMPTZ | Creation time |

### 3.4 categories

Stores product categories.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | VARCHAR(100) | Category name |
| is_active | BOOLEAN | Status |

### 3.5 products

Stores the distributor's product catalogue.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| sku | VARCHAR(50) | Unique product SKU |
| name | VARCHAR(200) | Product name |
| brand | VARCHAR(100) | Brand |
| category_id | UUID | Category foreign key |
| pack_size | VARCHAR(100) | Example: 75g |
| units_per_case | NUMERIC(12,3) | Units in one case |
| base_unit | VARCHAR(30) | Example: piece |
| order_unit | VARCHAR(30) | Example: case |
| gst_rate | NUMERIC(5,2) | Applicable GST percentage |
| image_url | TEXT, nullable | Cloudinary `secure_url` of the product image |
| image_public_id | VARCHAR(255), nullable | Cloudinary `public_id` (used to replace/delete the image) |
| is_active | BOOLEAN | Product status |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last update |

Keep the ordering unit explicit. Do not assume that every quantity means cases or pieces.

### 3.6 retailer_prices

Stores retailer-specific product prices.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| retailer_id | UUID | Retailer foreign key |
| product_id | UUID | Product foreign key |
| dealer_price | NUMERIC(12,2) | Selling price |
| price_basis | VARCHAR(20) | CASE or PIECE |
| tax_inclusive | BOOLEAN | Whether GST is included |
| effective_from | TIMESTAMPTZ | Price start date |
| effective_to | TIMESTAMPTZ, nullable | Price end date |
| created_at | TIMESTAMPTZ | Creation time |

A retailer's price must be selected using the active effective date range.

Do not assume whether sample prices are per case or per piece. Keep price_basis configurable and confirm the business's actual pricing convention before production use.

### 3.7 schemes

Stores product-level promotional schemes.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| product_id | UUID | Product foreign key |
| scheme_type | VARCHAR(30) | FREE_GOODS or SLAB_DISCOUNT |
| min_quantity | NUMERIC(12,3) | Minimum qualifying quantity |
| free_quantity | NUMERIC(12,3) | Free quantity |
| discount_percentage | NUMERIC(5,2) | Discount percentage |
| starts_at | TIMESTAMPTZ | Scheme start |
| ends_at | TIMESTAMPTZ, nullable | Scheme end |
| is_active | BOOLEAN | Scheme status |
| created_at | TIMESTAMPTZ | Creation time |

V1 supports:
- FREE_GOODS: Buy 10 cases, get 1 free.
- SLAB_DISCOUNT: Buy 5 or more cases, get 3% discount.

Do not apply multiple schemes together unless explicitly configured.

Implementation note: `free_quantity` and `discount_percentage` are NOT NULL; the benefit a scheme type does not use is stored as 0 (a CHECK constraint enforces this). FREE_GOODS gives `free_quantity` for every full `min_quantity` ordered (buy 10 get 1: 25 cases → 2 free). If more than one active scheme qualifies for the same order line, pricing is refused with `SCHEME_CONFLICT` instead of combining or choosing one.

### 3.8 retailer_aliases

Stores alternative product names used by individual retailers.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| retailer_id | UUID | Retailer foreign key |
| product_id | UUID | Product foreign key |
| alias | VARCHAR(200) | Retailer's product description |
| normalized_alias | VARCHAR(200) | Normalized matching text |
| created_at | TIMESTAMPTZ | Creation time |

Example:
- Retailer says: "chhota biscuit".
- Actual product: "Glucose Biscuit 75g".

Aliases improve future AI matching for that retailer.

Add a unique constraint on retailer_id + normalized_alias.

### 3.9 ai_extractions

Stores original AI order-capture requests.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| retailer_id | UUID | Retailer foreign key |
| user_id | UUID | User who submitted the message |
| original_message | TEXT | Original order message |
| extraction_status | VARCHAR(30) | PENDING, REVIEWED, CONFIRMED, FAILED |
| model_name | VARCHAR(100), nullable | Model used |
| raw_response | JSONB, nullable | Structured extraction response |
| created_at | TIMESTAMPTZ | Creation time |

### 3.10 ai_extraction_items

Stores individual items extracted from an AI request.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| extraction_id | UUID | AI extraction foreign key |
| original_text | TEXT | Original item wording |
| extracted_name | VARCHAR(200) | Extracted product description |
| quantity | NUMERIC(12,3) | Extracted quantity |
| unit | VARCHAR(30) | Extracted unit |
| matched_product_id | UUID, nullable | Matched product |
| confidence | NUMERIC(4,3) | Matching confidence |
| alternatives | JSONB, nullable | Alternative matches |
| requires_clarification | BOOLEAN | Whether user input is needed |
| created_at | TIMESTAMPTZ | Creation time |

AI extraction is not an order. A user must review and confirm the matched products and quantities.

Approved deviation: `quantity` and `unit` are nullable. NULL means the retailer's message did not state it (e.g. "5 biscuit" — cases or packets?); such items are stored with `requires_clarification = true` and the unit is never guessed. The confirming user must state the quantity and unit explicitly.

### 3.11 orders

Stores retailer orders.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| order_number | VARCHAR(50) | Unique order number |
| retailer_id | UUID | Retailer foreign key |
| created_by | UUID | User who placed the order |
| ai_extraction_id | UUID, nullable | Related AI extraction |
| source | VARCHAR(20) | MANUAL, AI, SALESMAN |
| status | VARCHAR(30) | PENDING, CREDIT_HOLD, ON_HOLD, CLARIFICATION_REQUIRED, APPROVED, REJECTED |
| subtotal | NUMERIC(14,2) | Amount before discounts |
| discount_total | NUMERIC(14,2) | Total discount |
| taxable_amount | NUMERIC(14,2) | Taxable value |
| gst_amount | NUMERIC(14,2) | Total GST |
| grand_total | NUMERIC(14,2) | Final order value |
| remarks | TEXT, nullable | Additional instructions |
| rejection_reason | TEXT, nullable | Reason for rejection |
| hold_reason | TEXT, nullable | Why the order is ON_HOLD (offline review reasons, or the desk's reason) |
| clarification_message | TEXT, nullable | What the Order Desk asked (CLARIFICATION_REQUIRED) |
| tally_exported_at | TIMESTAMPTZ, nullable | When the order was (last) exported to Tally; NULL = not exported |
| approved_by | UUID, nullable | Approving user |
| approved_at | TIMESTAMPTZ, nullable | Approval time |
| created_at | TIMESTAMPTZ | Order creation time |
| updated_at | TIMESTAMPTZ | Last update |

### 3.12 order_items

Stores products and immutable pricing snapshots for each order.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| order_id | UUID | Order foreign key |
| product_id | UUID | Product foreign key |
| product_name | VARCHAR(200) | Product name snapshot |
| sku | VARCHAR(50) | SKU snapshot |
| paid_quantity | NUMERIC(12,3) | Quantity charged |
| free_quantity | NUMERIC(12,3) | Free quantity |
| price_basis | VARCHAR(20) | CASE or PIECE |
| unit_price | NUMERIC(12,2) | Price snapshot |
| discount_percentage | NUMERIC(5,2) | Discount applied |
| discount_amount | NUMERIC(12,2) | Discount amount |
| gst_rate | NUMERIC(5,2) | GST snapshot |
| tax_inclusive | BOOLEAN, nullable | Whether unit_price included GST (NULL only for lines created before it was recorded) |
| scheme_id | UUID, nullable | Applied scheme (FK schemes) |
| scheme_snapshot | JSONB, nullable | Applied scheme terms at order time: scheme_type, min_quantity, free_quantity, discount_percentage, description |
| taxable_amount | NUMERIC(14,2) | Taxable amount |
| gst_amount | NUMERIC(14,2) | GST amount |
| line_total | NUMERIC(14,2) | Final line amount |

Keep the product name, SKU, price, scheme discount and GST snapshots even if the original product or price changes later.

Free quantities must be stored separately from paid quantities.

Salesman module (migration `768fa02aea51`): `orders.client_order_id` (VARCHAR(64), unique, nullable: id generated by the salesman's phone, makes offline sync idempotent), `orders.created_offline` (BOOLEAN, default false), `orders.client_created_at` (TIMESTAMPTZ, nullable); table `shop_visits` (id UUID from the phone, salesman_id, retailer_id, started_at, ended_at, outcome ORDER_PLACED/NO_ORDER/NULL, order_id nullable, created_at).

Every order (catalogue, salesman, AI) waits for the Order Desk, which accepts or rejects it; stock and credit change only on acceptance (a salesman order above the credit arrives as CREDIT_HOLD). Available credit = credit_limit - current_outstanding - the totals of PENDING/ON_HOLD/CLARIFICATION_REQUIRED orders (computed, not stored).

Order statuses: PENDING (under review, shown as "Under review"), CREDIT_HOLD (above available credit), ON_HOLD (held by the Order Desk with `hold_reason`), APPROVED (confirmed: stock deducted, credit debited) and REJECTED. PENDING, CREDIT_HOLD, ON_HOLD and CLARIFICATION_REQUIRED (the desk asked the retailer/salesman, `clarification_message`) are open: they can be corrected, held, sent for clarification, approved or rejected. A correction keeps ON_HOLD and CLARIFICATION_REQUIRED; otherwise it re-evaluates PENDING vs CREDIT_HOLD. Migration `0898ff9db2db` added ON_HOLD, `hold_reason` and the three order_items columns (existing lines were backfilled only where the effective price/scheme matched the stored snapshot).

### 3.13 order_corrections

Stores order desk corrections.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| order_item_id | UUID | Order item foreign key |
| old_product_id | UUID, nullable | Previous product |
| new_product_id | UUID | Corrected product |
| old_quantity | NUMERIC(12,3) | Previous quantity |
| new_quantity | NUMERIC(12,3) | Corrected quantity |
| corrected_by | UUID | User who corrected it |
| reason | TEXT, nullable | Correction reason |
| created_at | TIMESTAMPTZ | Correction time |

Every correction must be traceable. `reason` is required for new corrections.

### 3.13a order_events

Order history (audit trail), append-only. Migration `3c1d2e4f5a6b` backfilled it for existing orders from their columns (RECEIVED, CORRECTED, CONFIRMED, REJECTED, PUT_ON_HOLD; actor NULL where it was not recorded).

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| order_id | UUID | Order foreign key |
| action | VARCHAR(30) | RECEIVED, CONFIRMED, CREDIT_HOLD, PUT_ON_HOLD, CLARIFICATION_REQUESTED, CORRECTED, REJECTED, EXPORTED |
| actor_id | UUID, nullable | User who acted (NULL: not recorded) |
| message | TEXT, nullable | Reason / clarification message / override reason |
| details | JSONB, nullable | e.g. old and new values of a correction, source and initial status, re-export flag |
| created_at | TIMESTAMPTZ | When it happened |

Index `(order_id, created_at)`. Written by the orders service in the same transaction as the action, and by the Tally export.

### 3.13b Admin tables (migration `ad0ca19d9725`)

- **brands** (`id`, `name` unique, `is_active`, `created_at`): `products.brand` is a foreign key to `brands.name` with ON UPDATE CASCADE (renaming a brand renames it on products). Backfilled from existing product brands.
- **audit_logs** (`id`, `actor_id` nullable, `action`, `entity_type`, `entity_id`, `entity_label`, `details` JSONB, `created_at`; indexes `(entity_type, entity_id)`, `created_at`): append-only record of master-data changes and refused salesman syncs (`SYNC_FAILED`). Never stores passwords, OTPs or keys.
- **app_settings** (`key` PK, `value` JSONB, `updated_by`, `updated_at`): business settings (see `app/modules/settings`).
- **salesman_sync_status** (`user_id` PK, `last_sync_at`, `reported_at`, `pending_orders`, `failed_orders`, `pending_visits`, `last_error`): what each salesman's phone last reported.
- **retailer_prices.retailer_id** is nullable: NULL = the product's default price (used when the retailer has no own price); `created_by` records who set it. Changing a price closes the current row (`effective_to`) and adds a new one.
- **retailers.ordering_restricted_reason**: set = ordering paused by the Admin (all channels).
- **stock_movements.stock_after**: stock after the movement (backfilled as the running sum); before = after − quantity.
- **users.last_login_at**.

### 3.13c AI extraction additions (migrations `7431a895841f`, `0ab00ee2a897`)

- `ai_extractions.input_type` (TEXT, IMAGE, VOICE).
- `ai_extraction_items.line_no` (position in the message), `evidence` JSONB (business evidence for the match), `clarification_reason`, `order_item_id` (FK order_items: the order line this AI line became; backfilled for placed orders by matching product). The order line's current product is what the retailer meant: used as retailer-specific history for future matching.

### 3.14 inventory

V1 uses a single warehouse.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| product_id | UUID | Unique product foreign key |
| stock_cases | NUMERIC(12,3) | Available case stock |
| updated_at | TIMESTAMPTZ | Last update |

### 3.15 stock_movements

Stores inventory movement history.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| product_id | UUID | Product foreign key |
| order_id | UUID, nullable | Related order |
| movement_type | VARCHAR(30) | ORDER_DEDUCTION, RESTOCK, ADJUSTMENT |
| quantity | NUMERIC(12,3) | Movement quantity |
| reference | VARCHAR(200), nullable | Reference details |
| created_by | UUID | User responsible |
| created_at | TIMESTAMPTZ | Creation time |

Use stock movements to maintain an auditable inventory history.

### 3.16 credit_accounts

Stores each retailer's credit information.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| retailer_id | UUID | Unique retailer foreign key |
| credit_limit | NUMERIC(14,2) | Maximum allowed credit |
| current_outstanding | NUMERIC(14,2) | Current outstanding amount |
| updated_at | TIMESTAMPTZ | Last update |

Available credit:

`available_credit = credit_limit - current_outstanding`

### 3.17 credit_ledger

Stores credit transactions.

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| retailer_id | UUID | Retailer foreign key |
| order_id | UUID, nullable | Related order |
| transaction_type | VARCHAR(30) | ORDER_DEBIT, PAYMENT_CREDIT, ADJUSTMENT |
| amount | NUMERIC(14,2) | Transaction amount |
| description | TEXT, nullable | Transaction details |
| created_by | UUID | User responsible |
| created_at | TIMESTAMPTZ | Creation time |

Do not let retailers modify their own credit limit or outstanding balance.

## 4. Relationship Summary

| Parent | Child | Relationship |
|---|---|---|
| retailers | users | One-to-many |
| categories | products | One-to-many |
| retailers | retailer_prices | One-to-many |
| products | retailer_prices | One-to-many |
| products | schemes | One-to-many |
| retailers | retailer_aliases | One-to-many |
| products | retailer_aliases | One-to-many |
| retailers | ai_extractions | One-to-many |
| ai_extractions | ai_extraction_items | One-to-many |
| retailers | orders | One-to-many |
| orders | order_items | One-to-many |
| order_items | order_corrections | One-to-many |
| orders | order_events | One-to-many |
| products | inventory | One-to-one |
| products | stock_movements | One-to-many |
| retailers | credit_accounts | One-to-one |
| retailers | credit_ledger | One-to-many |

## 5. Important Database Constraints

- All primary keys must be UUIDs.
- Product SKU must be unique.
- User phone number must be unique.
- User email must be unique when present and stored normalized (lower case, trimmed).
- Order number must be unique.
- A retailer must not have duplicate normalized aliases.
- Each product must have only one inventory row in V1.
- Each retailer must have one credit account.
- Use foreign keys for related records.
- Use NUMERIC for monetary values and quantities.
- Quantities must not be negative.
- GST rate and discount percentage must be within valid ranges.
- Use appropriate indexes for frequently filtered fields.

## 6. Important Indexes

Create indexes on:

- users.phone
- users.role
- retailers.assigned_salesman_id
- products.sku
- products.category_id
- retailer_prices (retailer_id, product_id)
- schemes (product_id, is_active)
- retailer_aliases (retailer_id, normalized_alias)
- orders (retailer_id, created_at)
- orders (status, created_at)
- order_items.order_id
- ai_extractions.retailer_id
- stock_movements.product_id
- credit_ledger.retailer_id

Add unique and composite indexes where appropriate.

## 7. Transaction and Data Integrity Rules

### Order approval

Order approval must run inside one database transaction.

1. Lock the relevant inventory rows.
2. Recheck available stock, including free quantities.
3. Recheck available credit.
4. Calculate or verify the final order totals.
5. Deduct stock.
6. Insert stock movement records.
7. Update the credit account and insert credit ledger entries according to the distributor's credit policy.
8. Update order status to APPROVED.
9. Commit the transaction.

If any operation fails, roll back the entire transaction.

Prevent concurrent approvals from selling the same stock twice.

### Order rejection

- Update order status to REJECTED.
- Store the rejection reason.
- Do not deduct inventory.
- Do not create an order debit in the credit ledger.

### Historical order data

- Do not calculate historical orders using current product prices.
- Preserve product, price, discount, scheme and GST snapshots.
- Do not hard-delete approved orders or financial ledger records.

## 8. V1 Scope

Implement these tables in V1:

1. users
2. otp_verifications
3. retailers
4. categories
5. products
6. retailer_prices
7. schemes
8. retailer_aliases
9. ai_extractions
10. ai_extraction_items
11. orders
12. order_items
13. order_corrections
14. inventory
15. stock_movements
16. credit_accounts
17. credit_ledger

Do not add multi-warehouse, payments, delivery tracking or unnecessary tables in V1.

## 9. Implementation Guidelines

- Define SQLAlchemy models with proper foreign keys and relationships.
- Use Alembic for schema migrations.
- Keep database models separate from Pydantic API schemas.
- Seed realistic demo data.
- Use database transactions for critical operations.
- Add constraints and indexes through migrations.
- Never store API keys, passwords or secrets in database seed files.
- Keep the schema simple and extensible without introducing unnecessary abstractions.
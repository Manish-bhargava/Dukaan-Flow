# Project Context: DukaanFlow

## 1. Project Overview

**Project Name:** DukaanFlow

**Product Type:** FMCG Distribution Management and Retailer Ordering Platform with AI-powered Order Capture.

DukaanFlow is a lightweight, mobile-first ordering and distribution management platform designed for an FMCG distributor in Jabalpur, India.

The platform connects retailers, salesmen and the distributor's internal order desk through a centralized system.

Its primary purpose is to digitize the retailer ordering process, reduce manual order-entry work, improve order accuracy, provide visibility into product availability and schemes, and simplify distributor operations.

This is not simply an e-commerce application or an AI chatbot. It is a practical distribution management system with an AI-assisted ordering workflow.

---

## 2. Business Background

The client is an FMCG distributor operating in Jabalpur.

Business context:

- Distributes products from 4 packaged food and home-care brands.
- Serves approximately 1,800 kirana shops.
- Has approximately 70 employees, including 18 salesmen.
- Annual revenue is approximately ₹85–100 crore.

### Existing ordering process

Currently, retailers place orders through:

1. Salesmen visiting shops and writing orders in notebooks.
2. Retailers sending WhatsApp text messages.
3. Retailers sharing photographs of handwritten order lists.
4. Retailers sending voice notes.

The distributor's office team, consisting of approximately 6 employees, manually enters these orders into Tally the following morning.

### Business problems

- Manual order entry consumes significant employee time.
- Handwritten and WhatsApp orders can be misinterpreted.
- Product names and quantities can be entered incorrectly.
- Retailers do not have real-time visibility into stock.
- Retailers do not know which schemes are currently available.
- Salesmen cannot reliably communicate stock availability and promotional offers.
- Credit limits are difficult to manage consistently.
- The distributor lacks a centralized view of retailer ordering activity.

### Business objective

Create a centralized digital platform where retailers can place orders themselves or through AI-assisted message capture, while distributor employees can review, correct, approve and export those orders.

---

## 3. Target Users and Roles

The system should support four user roles.

### 1. Retailer

Retailers should be able to:

- Log in using mobile OTP.
- Browse the product catalogue.
- View their own dealer prices.
- View product availability.
- View applicable schemes.
- Add products to their cart.
- Place orders manually.
- Generate orders from text messages using AI.
- Review AI-generated product matches before confirmation.
- View their order history and order status.
- View their credit limit, outstanding balance and available credit.
- Repeat previous orders.

Retailers must only see their own prices, orders and credit information.

### 2. Salesman

Salesmen should be able to:

- Access their assigned retailers.
- Browse the product catalogue.
- Place orders on behalf of retailers.
- View applicable product prices and schemes for assigned retailers.
- Create orders when internet connectivity is poor, with offline drafts as a possible extension.

Salesman functionality can be simplified in V1.

### 3. Order Desk

Order desk employees should be able to:

- View incoming orders from all retailers.
- Review pending orders.
- Review AI-generated orders.
- Correct incorrect product matches and quantities.
- View pricing, schemes, stock and credit information.
- Handle credit holds.
- Approve or reject orders.
- Export approved orders into Tally-compatible CSV format.

### 4. Admin / Distributor Owner

The distributor owner should be able to:

- View distributor-wide dashboard metrics.
- Monitor sales and order activity.
- Manage products and inventory.
- Manage retailers.
- Configure retailer-specific prices.
- Configure promotional schemes.
- Monitor inactive retailers.
- View operational reports.

For V1, admin and order desk can share some permissions.

---

## 4. Core Product Features

### A. Authentication and Role Management

- Mobile number-based OTP authentication.
- JWT-based authentication.
- Role-based access control.
- Protected APIs and frontend routes.
- Retailer-to-user mapping.
- Mock OTP functionality for the demo.
- Separate retailer and distributor experiences.

Security is important. A retailer must not be able to access another retailer's pricing, credit, orders or personal information by modifying API parameters.

### B. Product Catalogue

The catalogue should display:

- Product name.
- Brand.
- SKU.
- Product image.
- Pack size.
- Units per case.
- Dealer price.
- Price basis (per case or per piece).
- Available stock.
- Applicable promotional scheme.
- Availability status.

Features:

- Product search.
- Category filtering.
- Product details.
- Add to cart.
- Quantity adjustment.
- Out-of-stock indication.
- Retailer-specific pricing.

The same product may have different dealer prices for different retailers.

Product prices must come from the backend, never from hardcoded frontend values.

### C. Cart and Order Management

Retailers should be able to:

- Add multiple products.
- Change quantities.
- Remove products.
- View scheme benefits.
- View discounts.
- View GST.
- View the final order amount.
- Submit orders.

The backend must calculate all pricing and totals.

The frontend must never be trusted for final prices, discounts, GST or order totals.

Order statuses:

- PENDING
- CREDIT_HOLD
- APPROVED
- REJECTED

Unsubmitted carts can remain frontend drafts in V1.

### D. AI-Powered Order Capture

This is one of the most important features.

Retailers should be able to type a natural-language order instead of manually selecting every product.

Example message:

"bhaiya 5 peti biscuit chhota, 2 peti washing powder 1 kilo, chai patti 250 wala 1 peti"

The AI should understand the message and extract:

- Product description.
- Quantity.
- Unit.
- Original text for each product line.

The system should then identify matching catalogue SKUs.

#### AI processing pipeline

1. Retailer submits a text message.
2. LLM extracts structured order information.
3. Backend matches extracted descriptions against catalogue products.
4. Matching considers:
   - Exact product names.
   - SKU.
   - Product aliases.
   - Hindi and English terminology.
   - Hinglish expressions.
   - Fuzzy matching.
   - Retailer-specific previous corrections.
5. System returns the best matching product and two alternatives where available.
6. Each line displays matching confidence.
7. Retailer reviews and corrects matches.
8. Retailer confirms the order.
9. Normal pricing, scheme, stock and credit validation takes place.

#### Important AI rules

- The LLM only understands and extracts the retailer's message.
- The LLM must not decide final SKU prices, schemes, stock or credit.
- Python business logic must determine these values.
- Matching confidence must be calculated by the matching process, not blindly trusted from the LLM.
- Every product line should retain its original retailer wording.
- Alternative SKUs should be displayed when matching is uncertain.
- If the product or unit is ambiguous, ask for clarification.
- Never assume whether a quantity means cases or individual pieces.
- Never create or submit an order without human confirmation.

For example, if a retailer says "5 biscuit bhej dena" and it is unclear whether they mean 5 cases or 5 packets, the application must ask.

#### Learning from corrections

If the order desk corrects a product match, the system should optionally save the corrected retailer-specific alias.

Example:

Retailer A uses "chhota biscuit" for SKU-BS-075.

The next time that retailer uses the same phrase, the system should use the saved alias to improve matching.

This does not require model retraining.

#### Future AI capabilities

The same pipeline should eventually support:

- Photographs of handwritten order lists.
- Hindi voice notes.
- WhatsApp order integration.

These can be added later. The first implementation should prioritize reliable text-based AI ordering.

---

## 5. Scheme and Pricing Engine

This is a critical business logic component.

The platform must support at least two promotional scheme types.

### Scheme 1: Free Goods

Example:

Buy 10 cases of glucose biscuits and get 1 case free.

If a retailer orders:

- Paid quantity: 10 cases.
- Free quantity: 1 case.
- Total fulfilled quantity: 11 cases.

The system should automatically calculate the free quantity.

### Scheme 2: Slab Discount

Example:

Buy 5 or more cases of detergent and get a 3% discount.

- 4 cases: No discount.
- 5 cases: 3% discount.
- 6 cases: 3% discount.

### Pricing engine responsibilities

- Fetch retailer-specific dealer prices.
- Determine applicable schemes.
- Calculate free quantities.
- Calculate slab discounts.
- Calculate taxable amounts.
- Calculate GST.
- Calculate final totals.
- Return a detailed price breakdown.

All calculations must happen on the backend.

The system should support configurable:

- Price basis (per case or per piece).
- GST rate.
- GST-inclusive or GST-exclusive pricing.
- Scheme start and end dates.
- Scheme eligibility.
- Quantity thresholds.

For V1, implement the two required scheme types with straightforward Python functions. Do not build a complicated generic rule engine.

Free goods must also be included in inventory deduction.

---

## 6. Inventory Management

The distributor should have a centralized inventory view.

Each product should have its available stock in cases.

Sample inventory:

- Glucose biscuit 75g: 340 cases.
- Detergent powder 1kg: 85 cases.
- Tea leaf 250g: 0 cases.

Requirements:

- View available stock.
- Identify low-stock products.
- Identify out-of-stock products.
- Validate stock before order submission.
- Recheck stock during order approval.
- Prevent negative inventory.
- Record every stock movement.

### Inventory deduction policy

A pending order should not permanently deduct stock.

When the order desk approves an order:

1. Recheck available stock.
2. Lock the relevant inventory rows.
3. Deduct paid quantity plus free quantity.
4. Record stock movements.
5. Mark the order approved.
6. Commit the transaction.

These operations must be atomic to prevent overselling when multiple employees approve orders simultaneously.

Rejected orders must not deduct inventory.

---

## 7. Credit Management

Each retailer should have an assigned credit limit and outstanding balance.

Example:

- Credit limit: ₹50,000.
- Current outstanding: ₹35,000.
- Available credit: ₹15,000.
- New order amount: ₹20,000.

The order should be flagged for a credit hold.

Formula:

Available credit = Credit limit - Outstanding balance.

Requirements:

- Retailers can view their credit information.
- Retailers cannot modify their own credit limits.
- Order desk can view credit details.
- Orders exceeding available credit should be flagged.
- Distributor employees should be able to review credit holds.
- Approved credit-related changes must be auditable.

Maintain a credit ledger to record debits, payments and adjustments.

For V1, actual payment gateway integration is not required.

---

## 8. Distributor Dashboard

The distributor dashboard should provide a centralized operational overview.

Important metrics:

- Total orders today.
- Total sales today.
- Pending orders.
- Credit-hold orders.
- Approved orders.
- Low-stock products.
- Out-of-stock products.
- Inactive retailers.

### Inactive retailers

The system should identify retailers who have not placed an order in the previous 14 days.

This information can help the distributor and salesmen follow up with inactive shops.

---

## 9. Order Desk

The order desk is a central operational screen.

It should provide:

- Incoming order queue.
- Order status filters.
- Search by retailer or order ID.
- Order details.
- Original AI message when applicable.
- AI product matching information.
- Product correction.
- Quantity correction.
- Scheme and pricing breakdown.
- GST breakdown.
- Stock validation.
- Credit validation.
- Approve and reject actions.

All corrections should be recorded for audit purposes.

When a product is corrected, the application should offer to save the corrected name as a retailer-specific alias.

---

## 10. Tally Export

Actual Tally integration is not required for V1.

The application should generate Tally-compatible CSV files for approved orders.

CSV should include:

- Order number.
- Order date.
- Retailer name.
- Retailer ID.
- Retailer address.
- GSTIN, where applicable.
- Product SKU.
- Product name.
- Paid quantity.
- Free quantity.
- Price basis.
- Unit price.
- Discount.
- Taxable amount.
- GST rate.
- GST amount.
- Final amount.

Only approved orders should be exportable.

Historical order prices and scheme calculations must remain unchanged even if the current catalogue price or scheme changes.

An optional export history can record which orders have already been exported.

---

## 11. Progressive Web Application (PWA)

The application should be installable on mobile devices.

Important requirements:

- Responsive design.
- Mobile-first interface.
- Installable PWA.
- Fast initial loading.
- Large touch targets.
- Simple navigation.
- Low-bandwidth optimization.
- Basic catalogue caching.
- Offline order drafts as a stretch feature.

The application must work well on low-end Android phones and slow 3G connections.

Target first-load performance should be under 3 seconds under reasonable test conditions.

Full offline synchronization is not a V1 requirement.

The UI should support Hindi and English, with a simple, practical interface suitable for kirana shop owners.

---

## 12. Initial Sample Product Data

The assignment provides the following sample catalogue:

| SKU | Product | Pack | Case Size | Dealer Price | Stock | Scheme |
|---|---|---|---:|---:|---:|---|
| SKU-BS-075 | Glucose biscuit | 75g | 96 | ₹8.10 | 340 cases | Buy 10, get 1 free |
| SKU-DT-1KG | Detergent powder | 1kg | 20 | ₹101.50 | 85 cases | 3% off on 5+ cases |
| SKU-TE-250 | Tea leaf | 250g | 40 | ₹118 | 0 cases | No scheme |

Important: The sample does not explicitly establish whether dealer prices are per piece or per case, or whether GST is included. These must be configurable rather than assumed.

---

## 13. Technology Stack

Recommended V1 stack:

### Frontend
- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- React Router.
- TanStack Query.
- React Hook Form.
- Zod.
- vite-plugin-pwa.

### Backend
- Python.
- FastAPI.
- Pydantic.
- SQLAlchemy.
- Alembic.
- JWT authentication.
- OpenAI SDK.
- RapidFuzz for product matching.

### Database
- PostgreSQL.

### Deployment
- Vercel for frontend.
- Render for backend.
- Render PostgreSQL or Neon for database.

### Development tools
- GitHub.
- Postman.
- Docker where useful.

Use a modular monolith, not microservices.

Do not introduce unnecessary technologies such as Kafka, Celery, Redis, LangGraph or complex agent architectures unless a real requirement emerges.

---

## 14. Database Design Overview

The database should use PostgreSQL with UUID primary keys, foreign keys, indexes, constraints and transactional updates.

Suggested V1 tables:

### Authentication
- users
- otp_verifications

### Retailer management
- retailers

### Product catalogue
- categories
- products

### Pricing and schemes
- retailer_prices
- schemes

### AI order processing
- retailer_aliases
- ai_extractions
- ai_extraction_items

### Order management
- orders
- order_items
- order_corrections

### Inventory
- inventory
- stock_movements

### Credit
- credit_accounts
- credit_ledger

Important database principles:

- Retailer-specific pricing must be stored separately.
- Product aliases must be retailer-specific.
- Order items must store price, tax and scheme snapshots.
- Stock changes must be recorded.
- Credit changes must be traceable.
- Use NUMERIC/DECIMAL for money.
- Use timezone-aware timestamps.
- Enforce data integrity through database constraints.
- Protect historical orders from changes to current catalogue data.

---

## 15. Backend Architecture

Use a layered modular monolith.

The application should follow:

Router → Controller → Service → Repository → Database.

Responsibilities:

- Router: Defines HTTP endpoints.
- Controller: Handles HTTP requests and responses.
- Service: Contains business logic.
- Repository: Handles database queries.
- Models: SQLAlchemy database definitions.
- Schemas: Pydantic request and response validation.
- Middleware: Authentication and request processing.
- Exceptions: Centralized application error handling.
- Core: Configuration, security and shared dependencies.

Organize modules by business capabilities:

- auth
- retailers
- products
- pricing
- ai_orders
- orders
- inventory
- dashboard
- exports

Keep the architecture practical. Avoid empty abstractions or unnecessary layers.

---

## 16. Core Software Engineering Requirements

The following are non-negotiable:

1. Backend is the source of truth for prices, schemes, GST, inventory and credit.
2. LLM only extracts and understands retailer messages; Python handles matching and business rules.
3. No order should be created from AI output until a human confirms it.
4. Every AI extraction and correction should be traceable.
5. Retailer-specific information must be protected by backend authorization.
6. Inventory deduction and order approval must be atomic.
7. Prevent negative inventory and concurrent overselling.
8. Preserve historical price and scheme snapshots.
9. Centralize error handling.
10. Use proper database transactions.
11. Validate API inputs and outputs.
12. Maintain consistent API response formats.
13. Keep the architecture maintainable and straightforward.

---

## 17. Five-Day Development Timeline

The complete project must be implemented within approximately five days.

### Day 1 — Backend Foundation

- FastAPI project setup.
- PostgreSQL connection.
- SQLAlchemy models.
- Database relationships.
- Alembic migrations.
- Seed data.
- Authentication.
- JWT.
- Role-based authorization.

Deliverable: Working backend with seeded database and retailer/order-desk login.

### Day 2 — Catalogue and Order Business Logic

- Product APIs.
- Retailer-specific pricing.
- Scheme engine.
- Cart calculations.
- GST calculations.
- Order creation.
- Stock validation.
- Credit validation.

Deliverable: A retailer can create a valid manual order.

### Day 3 — AI Order Capture

- OpenAI structured extraction.
- Hinglish product extraction.
- SKU matching.
- Confidence calculation.
- Alternative product suggestions.
- Unit clarification.
- Retailer aliases.
- AI extraction history.

Deliverable: A retailer can enter a natural-language message, review matches and convert it into a confirmed order.

### Day 4 — Distributor Operations

- Dashboard.
- Order queue.
- Order correction.
- Order approval and rejection.
- Credit holds.
- Transaction-safe stock deduction.
- Credit ledger.
- Tally CSV export.

Deliverable: Distributor can manage orders end to end.

### Day 5 — Frontend Integration and Deployment

- Retailer UI.
- Distributor dashboard.
- Responsive design.
- PWA setup.
- API integration.
- Testing.
- Authorization checks.
- Deployment.
- README and demo preparation.

Deliverable: A working, deployed end-to-end product.

---

## 18. Explicitly Out of Scope for V1

Do not spend time implementing:

- Delivery tracking.
- In-app payments.
- GST e-invoicing.
- Full Tally API integration.
- Complex microservices.
- Generic configurable rule engines.
- Multi-warehouse inventory.
- Full WhatsApp integration.
- Complete offline synchronization.
- AI agent orchestration.

These can be considered for future versions.

---

## 19. Definition of a Successful V1

The project should demonstrate the following end-to-end scenarios:

1. Retailer logs in and sees their own catalogue and prices.
2. Retailer can create an order manually.
3. AI understands the sample Hinglish order.
4. AI suggests matching SKUs and alternatives.
5. Ambiguous units require clarification.
6. Retailer confirms the AI-generated order.
7. Free-goods scheme is calculated correctly.
8. Slab discount is calculated correctly.
9. Out-of-stock products are handled correctly.
10. Credit-limit violations are flagged.
11. Order desk can correct an order.
12. Corrections can become retailer-specific aliases.
13. Order desk can approve or reject orders.
14. Stock and credit update consistently on approval.
15. Concurrent approvals cannot oversell inventory.
16. Historical orders retain their original pricing.
17. Approved orders can be exported to CSV.
18. Dashboard shows pending orders and inactive retailers.
19. Retailers cannot access another retailer's private information.
20. Application works responsively and can be installed as a PWA.

---

## 20. Overall Product Vision

DukaanFlow should be a practical, reliable and easy-to-use digital platform for FMCG distributors and kirana retailers.

The most important value propositions are:

- Faster retailer ordering.
- Reduced manual order-entry work.
- Fewer product and quantity mistakes.
- Better visibility into stock and promotional schemes.
- Reliable pricing and credit validation.
- Easier order review and approval.
- Faster Tally export.
- Better distributor operational visibility.

The goal is to build a working business product, not an unnecessarily complicated technical demonstration.

**Primary engineering priorities:** Reliable business logic, correct database design, accurate AI-assisted product matching, secure role-based access and transaction-safe order processing.

**Development approach:** Start with backend architecture and database design, implement business logic and APIs, then integrate the frontend. Build V1 first and avoid adding V2 complexity prematurely.
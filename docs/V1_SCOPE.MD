# DukaanFlow — V1 Implementation Plan

## 1. Implementation Approach

We will build DukaanFlow incrementally, step by step.

The project must not be generated completely in one attempt.

Each implementation milestone must be completed, reviewed, tested and approved before moving to the next milestone.

The goal is to maintain a working application throughout development.

## 2. Development Workflow

For every milestone:

1. Understand the milestone requirements.
2. Inspect the existing project structure and code.
3. Identify the files and components that need to be created or modified.
4. Explain the proposed implementation briefly.
5. Implement only the current milestone.
6. Run the application and verify the changes.
7. Run relevant tests.
8. Report what was implemented, files changed, commands to run and any remaining issues.
9. Wait for my review and approval before proceeding.

Do not automatically move to the next milestone.

Do not overwrite or unnecessarily modify existing working code.

## 3. Milestone 1 — Initial Project Setup

<badge color="success">First milestone</badge>

The first milestone is strictly limited to establishing the project foundation.

### Backend

Set up:
- Python virtual environment.
- FastAPI application.
- Application entry point.
- Environment configuration.
- Basic database configuration structure for PostgreSQL.
- Basic SQLAlchemy setup.
- Centralized application configuration.
- Basic CORS configuration.
- Basic error handling.
- A clean and minimal project structure.

### Frontend

Set up:
- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- Basic application entry point.
- Minimal routing setup if required.
- Environment configuration.

### Health Check Endpoint

Create:

`GET /api/v1/health`

Expected response:

```json
{
  "success": true,
  "message": "DukaanFlow API is running",
  "data": {
    "status": "healthy"
  }
}
```

This is a mock health-check endpoint. It only confirms that the API application is running.

Do not implement actual database connectivity checks or business functionality in this endpoint yet.

### Initial Frontend Screen

Create a minimal home screen that:
- Displays DukaanFlow.
- Confirms that the frontend is running.
- Calls the backend health endpoint.
- Displays the API connection status.

Keep the UI simple. No catalogue, login, dashboard or ordering screens yet.

### Documentation and Setup

Create:
- Root README.md.
- Backend requirements file.
- Backend `.env.example`.
- Frontend `.env.example`.
- `.gitignore`.
- Basic local development instructions.

Include commands to start both frontend and backend.

Never commit `.env` files, API keys, credentials or other secrets.

## 4. First Review and Commit — My Responsibility

After Milestone 1 is complete:

- Stop implementation.
- Show me the final project structure.
- Explain the important setup files.
- Provide the commands to run the frontend and backend.
- Confirm that the health endpoint works.
- Confirm that the frontend successfully connects to the backend.
- Report the test results.

**I will personally review the initial setup and make the first Git commit.**

Do not create the first commit on my behalf.

Do not proceed to Milestone 2 until I explicitly approve it.

## 5. Subsequent Implementation Milestones

After I approve the first commit, we will proceed in this order:

### Milestone 2 — Database and Authentication
- PostgreSQL connection.
- SQLAlchemy models.
- Alembic migrations.
- Initial database schema.
- Seed data.
- Mock OTP authentication.
- JWT generation and verification.
- User roles and authorization.

### Milestone 3 — Retailers and Product Catalogue
- Retailer management.
- Product and category APIs.
- Retailer-specific prices.
- Inventory visibility.
- Scheme configuration.

### Milestone 4 — Pricing and Scheme Engine
- Price calculations.
- Free-goods schemes.
- Slab discounts.
- GST calculations.
- Order total calculations.
- Unit and quantity handling.

### Milestone 5 — Manual Ordering
- Retailer cart.
- Order creation.
- Order history.
- Order status.
- Backend validation.

### Milestone 6 — AI Order Capture
- Natural-language extraction.
- Structured LLM output.
- Product matching.
- Retailer aliases.
- Confidence and alternatives.
- Clarification flow.
- AI extraction review and confirmation.

### Milestone 7 — Order Desk
- Incoming order queue.
- Order corrections.
- Order approval and rejection.
- Credit validation.
- Inventory deduction.
- Credit ledger updates.
- Transaction safety.

### Milestone 8 — Dashboard and Tally Export
- Operational dashboard.
- Inactive retailers.
- Stock information.
- Approved order CSV export.

### Milestone 9 — Frontend Integration and Finalization
- Connect all frontend screens to backend APIs.
- Responsive mobile-first UI.
- PWA configuration.
- Error and loading states.
- End-to-end testing.
- Deployment.
- Final README and demo instructions.

## 6. Development Rules

- Implement only the current milestone.
- Keep the implementation simple and production-conscious.
- Avoid unnecessary abstractions and overengineering.
- Do not introduce microservices.
- Do not add features outside the current milestone.
- Do not create placeholder modules for every future feature unless needed.
- Do not silently make business assumptions.
- Ask me when an important business decision is unclear.
- Preserve existing working code and Git history.
- Keep the application runnable after each milestone.
- Prefer small, understandable changes over large generated implementations.

**Important:** The milestone sequence is a development plan, not permission to implement all milestones at once.
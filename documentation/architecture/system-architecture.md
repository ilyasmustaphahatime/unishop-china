# system architecture

Verified 2026-10-07 through Phase 8. One React client, one FastAPI application and
one MySQL schema form a modular monolith. No event bus, microservices, universal
CRUD framework, payment processing or Phase 9 implementation.

```text
React Router -> feature hooks -> Zod contracts -> centralized Axios clients
                                                     |
                                                     v
FastAPI dependencies -> domain services -> repositories / MySQL / Alembic
                               |
                               v
               private StorageProvider / delivery interfaces
```

Auth, Profiles, Seller Verification and Catalog are business modules; Admin grants
no authority itself and delegates to seller/catalog services. Shared configuration,
errors, peer/HMAC budgets, neutral validators and transaction policies serve them.
Modules own tables; profiles consume narrow catalog/seller interfaces. ORM/FK
relationships connect these tables within a single transactional database.

The API is the authorization authority. React guards and disabled controls are UX.
Zustand owns memory-only access identity; TanStack Query owns server state. Public
catalog keys are distinct from private profile/seller/inbox caches. Dedicated
refresh/CSRF cookie transport uses backend Origin/CSRF checks. Evidence credentials
travel in a header, not URLs, and private evidence reads are audited before release.

Only development private-disk storage is configured. Production evidence fails
closed until a private object-store adapter is installed and verified. Current rate
budgets/one-use grants are process-local: multi-worker controls remain release work.
Real Tencent/production email delivery is not certified by fake-provider tests.

Local automated gates passed; production approval remains NO. Build advisories,
production storage/operations and browser/container runtime evidence are unresolved.
Local MySQL is 9.4; MySQL 8 deployment validation is a separate release gate.
See [current status](../CURRENT_PROJECT_STATUS.md) and
[the full architecture review](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).

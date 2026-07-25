# Phase 3B Fake SMS Threat Model

## Scope

This model covers the deliberately sensitive local fake SMS inbox used to manually test phone verification. It is a development aid, not a production SMS design.

## Assets

- Raw OTP values
- User accounts
- Phone numbers
- Verification status
- Passwords
- Database credentials
- Application secrets

## Actors

- Local developer
- Normal application user
- Remote attacker
- Malicious local process
- Accidental production deployer

## Trust boundaries

- Browser to local React development server
- React development server to local FastAPI
- FastAPI to MySQL
- Fake SMS sender to the process-memory inbox
- Development configuration to staging or production configuration

## Threat analysis

| # | Threat | Preventive control | Automated test | Remaining limitation |
|---|---|---|---|---|
| 1 | Fake inbox accidentally enabled in production | Startup validation rejects the flag outside `development`; the router is conditionally omitted | Production startup and route-absence tests | Deployment configuration must still set the intended environment correctly |
| 2 | Remote user accesses the inbox | The route checks the connection peer with `ipaddress.is_loopback`; localhost-only mode is mandatory | IPv4, IPv6, remote-peer, and forged-forwarding tests | A malicious process already running locally can reach a localhost service |
| 3 | OTP is written to application logs | Sender/store contain no logging or printing; safe exceptions contain no OTP | Captured-log and response-content assertions in backend security tests | Future logging changes require the same review |
| 4 | OTP is stored raw in MySQL | Existing HMAC repository remains the only database persistence path; raw value stays in memory | Registration/database assertions verify the stored value is a hash | In-process memory can be inspected by a sufficiently privileged local actor |
| 5 | Normal registration or resend returns OTP | Existing normal response schemas are unchanged; inbox has a separate development route | Existing Phase 3A API tests and Phase 3B response assertions | The explicit development inbox intentionally returns the raw OTP |
| 6 | Production OpenAPI exposes development routes | Router registration requires both development mode and the explicit flag | Production OpenAPI exclusion and development inclusion tests | Generated documentation from a development process contains the route by design |
| 7 | Expired OTP remains visible | Store prunes expired messages on access/add/count/consume and uses UTC-aware timestamps | Store expiration and route 404 tests | Cleanup is access-driven rather than a background timer |
| 8 | Verified OTP remains visible | Successful committed verification consumes the matching in-memory message | Successful verification/consume integration test | A process crash between commit and cleanup could retain it until expiry or restart |
| 9 | Cross-phone OTP disclosure | Lookup is keyed by normalized phone and returns only a matching message | Cross-phone isolation unit test | Anyone with local access and knowledge of another test number can query it |
| 10 | Password or OTP is stored in browser storage | Component state only; password/OTP are explicitly cleared; no persistence store is used | Frontend storage and state-clearing tests | Browser extensions or local debugging tools can inspect live page memory |
| 11 | Frontend console logs sensitive input | Development page and API wrapper contain no console calls or request-body logging | Static secret/log audit plus frontend tests | Browser tooling may display network requests to the local developer |
| 12 | CORS exposes the inbox remotely | Development CORS is limited to configured/local frontend origins; route also enforces loopback peer | Application configuration and remote-client tests | CORS does not protect against malicious local non-browser processes |
| 13 | Multiple messages cause code confusion | A new message supersedes every older message for the same normalized phone | Superseding and resend integration tests | Simultaneous requests are serialized in memory but user-facing cooldown errors remain possible |
| 14 | Test mode calls Tencent | Development fake sender performs no external I/O and is selected through the existing sender abstraction | Dependency and sender tests use the memory sender and no network mock | A different, explicitly selected provider follows its own configuration |
| 15 | Fake provider is selected in staging or production | Startup validation rejects `SMS_PROVIDER=fake` outside development | Parameterized production/staging guard tests | Incorrectly labelling a real deployment as development remains an operational risk |

## Security conclusion

The inbox exposes raw OTP values only on an explicitly enabled, loopback-only development route. Production and staging fail closed when fake mode is selected, and normal authentication APIs and MySQL retain the Phase 3A HMAC-only security model.

# Pre-Phase-4 Duplicate Audit

## Scope

This audit hashed every tracked, non-generated repository file with SHA-256 and reviewed security-relevant semantic duplication. Dependency directories, virtual environments, build output, caches, coverage, and temporary files were excluded.

## Exact duplicate result

Seventeen content-hash groups were found. None contained two active implementations that were safe to merge.

| Group | Classification | Decision |
|---|---|---|
| Package `__init__.py` and `.gitkeep` marker groups | Intentional structural markers | Preserve |
| Domain and admin route stubs | Separate future route ownership | Preserve |
| Backend model/schema/repository/service/seed/background-task stubs | Intentionally reserved architecture; ambiguous until their phases begin | Preserve |
| Script stubs | Ambiguous future operational tools | Preserve; review before implementation |
| Test and fixture stubs | Separate future test ownership | Preserve |
| Alembic-managed schema and container-init SQL stubs | Separate deployment/documentation responsibilities | Preserve |
| Seed SQL stubs | Separate domain datasets | Preserve |
| Placeholder favicon and logo | Ambiguous visual assets | Preserve pending design decision |
| Frontend feature, hook, service, store, type, and utility stubs | Separate future module responsibilities | Preserve |

Deleting or consolidating these files would erase intended architectural ownership without reducing active duplicated logic.

## Semantic duplicate result

### Consolidated

- UTC normalization existed independently in `development_fake_sms.py` and `phone_verification_service.py`.
- It is now implemented once in `app/common/datetime_utils.py`.
- Existing fake-SMS and verification tests prove behavior is unchanged.

### Intentionally separate

- Automated-test `FakeSmsSender` and the development inbox sender have different trust boundaries.
- Backend Pydantic types and frontend API response types validate different runtime boundaries.
- Repeated Pydantic phone validators all delegate to the single authoritative backend normalizer.
- Repository user lookup methods express different indexed identifiers.
- The application router and versioned router provide intentional prefix layering.

### Ambiguous and preserved

- `frontend/src/features/auth/store.ts` is an empty future feature stub while `frontend/src/stores/authStore.ts` is the active navigation-state scaffold.
- Numerous marketplace modules are placeholders reserved for later phases.
- Placeholder visual assets have identical content but different intended roles.

## Safety conclusion

No byte-for-byte active-code duplicate was deleted. One proven semantic duplicate was consolidated. Ambiguous scaffolding remains intact for explicit decisions during its owning phase.

# Remaining Work and Production Readiness

This document summarizes the main backend and platform work still pending before the system is production-ready.

## 1. Google Maps integration

Location handling is still incomplete.

Remaining work:

- Integrate Google Maps or Google Places for address lookup and validation.
- Standardize how addresses are stored for users, family members, and care requests.
- Capture latitude and longitude from Google geocoding, browser/device location, or admin pin-drop flows; Uber API access is not required for this.
- Add latitude and longitude fields to the records that drive matching: family member address, appointment visit location, and nurse base/service location.
- Use those coordinates first for straight-line distance checks and nurse assignment; add a separate routing provider later only if travel-time or turn-by-turn route calculations are needed.
- Protect the Google Maps API key using environment variables.
- Define which flows need maps support first: signup, family member address capture, or appointment matching.

Why this matters:

- Cleaner address data improves nurse assignment accuracy.
- It reduces manual correction of incomplete or inconsistent location details.

## 2. Better production database

SQLite is acceptable for local development, but it should not be the main production database.

Recommended production database:

- PostgreSQL on DigitalOcean Managed Database or another managed PostgreSQL provider.

Remaining work:

- Use PostgreSQL as the default production database.
- Confirm backups, monitoring, and restore procedures.
- Verify database migrations on staging before production rollout.
- Review indexes and query performance once production traffic begins.
- Separate development and production database credentials fully.

Why this matters:

- PostgreSQL is safer for concurrent production traffic.
- Managed databases provide better backup, reliability, and operational visibility.

## 3. Nurse module fixes

Parts of the nurse workflow still need review and testing.

Known concern:

- Some nurse module functionality is not working correctly yet.

Remaining work:

- Review nurse dashboard flows end to end.
- Confirm nurses can see assigned appointments consistently.
- Verify nurse profile creation and updates.
- Test nurse availability scheduling.
- Test appointment status changes from the nurse side.
- Add targeted API and UI test coverage for nurse-specific actions.
- Log and fix each failing nurse flow before release.

Recommended approach:

- Test with real nurse accounts and real appointment lifecycle data.
- Track failures by endpoint, role, and expected behavior.

## 4. What is Redis?

Redis is a very fast in-memory data store.

In this backend, Redis is useful mainly for background jobs through Celery.

How it fits here:

- The project already includes Celery settings for a Redis broker/result backend in production.
- Redis can queue tasks such as sending emails or notifications without blocking user requests.
- It can also be used later for caching, rate limiting, or temporary session/state storage.

Simple explanation:

- PostgreSQL stores permanent application data.
- Redis stores fast temporary data and job queue messages.

Why Redis is helpful:

- Faster response times for users.
- Better handling of background work.
- Less risk that email or notification work slows down API requests.

## 5. Recommended next implementation order

1. Stabilize the nurse module and document all broken flows.
2. Move production fully to managed PostgreSQL if not already done.
3. Configure Redis for Celery in production.
4. Add Google Maps integration once address and matching requirements are finalized.

## 6. Suggested message to share

The backend is functional, but a few important items still need completion before full production readiness. The main remaining work is Google Maps integration for better location handling, using a stronger production database setup with managed PostgreSQL, and fixing incomplete nurse-module flows. We should also enable Redis in production to support Celery background jobs such as email and notification processing.

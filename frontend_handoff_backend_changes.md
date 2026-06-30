# Frontend Handoff: Current Backend Contract

## Date

- April 2, 2026

## Current auth model

Roles are now:

- `user`
- `nurse`
- `admin`

Important rules:

- Public signup never chooses a role.
- `POST /api/auth/register/` always creates a `user`.
- Only admins should assign `nurse` or `admin`.
- Google sign-in also creates a `user` by default.

## Frontend role and ID contract (must follow)

Use only these role values:

- `user`
- `nurse`
- `admin`

For end-user list payloads:

- `id` = **EndUserProfile ID** (profile resource)
- `user_id` = **CustomUser ID** (user resource)

When calling admin role change:

- Endpoint: `POST /api/admin/users/{id}/change-role/`
- Prefer `{id} = user_id` from end-user payload.
- Send body: `{"role": "user" | "nurse" | "admin"}`

## Auth endpoints

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/google/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`

## Frontend token refresh strategy (recommended)

The backend protects most `/api/*` endpoints. If the access token is missing or expired, protected calls return `401`.

Recommended frontend behavior:

1. Attach `Authorization: Bearer <access_token>` on every protected request.
2. On first `401`, call `POST /api/auth/refresh/` once using the refresh token.
3. Retry the original request exactly once with the new access token.
4. If refresh fails (`401`/`403`), clear tokens and redirect to login.
5. If several requests fail at the same time, queue them while one refresh is in progress.

Axios interceptor shape (reference):

- Request interceptor:
  - Read access token from storage.
  - Add `Authorization` header when token exists.

- Response interceptor:
  - If response is not `401`, reject normally.
  - If request is already retried, reject to avoid loops.
  - If refresh is already in progress, queue the request and replay after refresh succeeds.
  - Otherwise:
    - Mark refresh as in progress.
    - Call `/api/auth/refresh/` with refresh token.
    - Save returned access token.
    - Replay queued requests.
    - Retry the failed request once.
    - On refresh failure, reject queued requests, clear auth state, and route to login.

Practical notes:

- Keep refresh endpoint call free of stale `Authorization` header from old access token.
- Do not trigger multiple parallel refresh calls.
- Keep access token lifetime short and refresh token lifetime longer for better security.
- Seeing an occasional `401` before a successful refresh is expected; the interceptor should make it invisible to users.

## Register request

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "first_name": "Jane",
  "last_name": "Doe",
  "current_country": "Kenya",
  "current_city": "Nairobi"
}
```

## Login request

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

## Login/register response

```json
{
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "phone": null,
    "first_name": "Jane",
    "last_name": "Doe",
    "role": "user",
    "profile_image": null,
    "is_verified": false,
    "is_active": true,
    "created_at": "2026-04-02T12:00:00Z"
  }
}
```

## Frontend route mapping

If you are building a separate frontend app, match the backend role redirects like this:

- `user` -> `/dashboard/user`
- `nurse` -> `/dashboard/nurse`
- `admin` -> `/dashboard/admin`

If you use the Django-rendered auth pages directly, these routes already exist:

- `/signup/`
- `/login/`
- `/dashboard/`
- `/dashboard/user`
- `/dashboard/nurse`
- `/dashboard/admin`

## Care request workflow

### Status values

- `SUBMITTED`
- `UNDER_REVIEW`
- `NURSE_SUGGESTED`
- `APPROVED`
- `REJECTED`
- `PENDING`
- `CONFIRMED`
- `COMPLETED`
- `CANCELLED`
- `NO_SHOW`
- `RESCHEDULED`

### Flow

1. User submits request.
2. Admin suggests nurse.
3. Admin approves or rejects.

### Important request rules

- End users do not choose a nurse during request creation.
- `family_member` must be an active family member owned by the authenticated user.
- If admission support is enabled, `admission_questionnaire` is required.
- Rejection requires `rejection_reason`.

### Appointment service_type accepted values

- `WELLNESS_VISIT`
- `CARE_VISIT`
- `CHRONIC_CONDITION_VISIT`
- `DAILY_CARE`
- `LIVE_IN_CARE`
- `EMERGENCY_ACCOMPANIMENT`

### Family member source of truth

- Load family members from `GET /api/family-members/`.
- Render `full_name` directly or join `first_name` + `last_name`.
- If `POST /api/appointments/` returns `400` or `401`/`403`, do not save a fake local request.
- Only use local offline fallback for genuine network failures where no API response is received.

### Required admission questionnaire keys

- `insurance_details`
- `last_procedure`
- `medical_conditions`
- `allergies`
- `emergency_contact`
- `consent_for_emergency_admission`

## Appointment endpoints

- `GET /api/appointments/`
- `POST /api/appointments/`
- `GET /api/appointments/{id}/`
- `PATCH /api/appointments/{id}/`
- `GET /api/appointments/pending-matching/`
- `POST /api/appointments/{id}/suggest-nurse/`
- `POST /api/appointments/{id}/decision/`
- `POST /api/appointments/{id}/confirm/`
- `POST /api/appointments/{id}/cancel/`
- `POST /api/appointments/{id}/reschedule/` (Payload: `appointment_date`, `start_time`, `end_time`)
- `POST /api/appointments/{id}/no-show/`

### Appointment cancel contract

- Endpoint: `POST /api/appointments/{id}/cancel/`
- Only the appointment owner can cancel.
- Allowed current statuses for cancel by owner:
  - `SUBMITTED`
  - `UNDER_REVIEW`
  - `NURSE_SUGGESTED`
- Successful cancel sets `status` to `CANCELLED` and returns `200`.
- If already `CANCELLED`, endpoint is idempotent and returns `200`.
- Error semantics:
  - `403` when requester is not the owner.
  - `404` when appointment id does not exist.
  - `400` when status transition to `CANCELLED` is not allowed.

## Notification endpoints

- `GET /api/notifications/`
- `GET /api/notifications/?is_read=false`
- `POST /api/notifications/{id}/mark-read/`
- `POST /api/notifications/mark-all-read/`
- `GET /api/notifications/unread-count/`

## Admin User Management endpoints

- `GET /api/admin/users/` (List all users, searchable)
- `POST /api/admin/users/{id}/change-role/` (Payload: `{"role": "nurse"}`)

## Nurse Earnings endpoints

- `GET /api/nurse-earnings/` (Admin sees all; Nurse sees only their own)
- `POST /api/nurse-earnings/` (Admin only: create an earning record)
- `PUT/PATCH /api/nurse-earnings/{id}/` (Admin only: update earning record)
- `POST /api/nurse-earnings/{id}/mark-paid/` (Admin only: marks earning as COMPLETED)

## Payment Integrations (M-Pesa, Stripe, PesaPal) endpoints

- `GET /api/payments/`
- `POST /api/payments/` (Initiate a payment)
- `GET /api/payments/{id}/`
- `POST /api/payments/{id}/refund/`
- `GET /api/payments/stats/`
- `POST /api/payments/mpesa-callback/` (Used internally by Safaricom API)
- `POST /api/payments/stripe-webhook/` (Used internally by Stripe API)
- `POST /api/payments/pesapal-ipn/` (Used internally by PesaPal IPN)

### Payment Rules

- `POST /api/payments/` requires `amount`, `method` (e.g., 'MPESA', 'STRIPE', 'PESAPAL'), and optional `appointment_ids`.
- If `method` is 'MPESA', the backend automatically generates an internal transaction tracking ID.
- If `method` is 'STRIPE' or 'PESAPAL', the backend similarly initializes the payment intent or tracking and returns the necessary data (such as client secret) to the frontend.

## Asynchronous Background Tasks (Celery)

- **Email Notifications:** The backend automatically dispatches email notifications asynchronously when appointments are created, approved, or rejected. The frontend will receive an immediate `200/201` API response without waiting for the email provider.
- **M-Pesa Receipts:** Once the `mpesa-callback` is triggered by Safaricom and the payment is marked `COMPLETED`, a payment receipt email is sent to the user in the background. No extra frontend action is required.

## Nurse discovery

Nurse `professional_type` values:

- `PHYSIOTHERAPIST`
- `CAREGIVER_NURSE`
- `PALLIATIVE_CARE_NURSE`

Filtering:

- `GET /api/nurses/?professional_type=PHYSIOTHERAPIST`

## Frontend implementation checklist

1. Remove any role selector from public signup.
2. Assume new signups are always `user`.
3. Redirect by returned `user.role`.
4. Remove nurse selection from end-user care request creation.
5. Add admin flows for pending matching, suggest nurse, and final decision.
6. Add notifications UI using `/api/notifications/*`.
7. Add nurse filtering by `professional_type`.
8. Connect payment flows using `/api/payments/`.
9. Implement Admin User Management page to change user roles.
10. Add UI for Appointment Reschedule and No-Show actions.
11. Implement Nurse Earnings view for Nurses and Payout management for Admins.

## Validation status

- Migration chain is repaired through `0009`.
- Local database has been reconciled.
- Auth and web auth tests are passing against the current contract.

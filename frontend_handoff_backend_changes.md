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

## Auth endpoints

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/google/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`

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

## Notification endpoints

- `GET /api/notifications/`
- `GET /api/notifications/?is_read=false`
- `POST /api/notifications/{id}/mark-read/`
- `POST /api/notifications/mark-all-read/`
- `GET /api/notifications/unread-count/`

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

## Validation status

- Migration chain is repaired through `0009`.
- Local database has been reconciled.
- Auth and web auth tests are passing against the current contract.

# Frontend Handoff: Backend Changes Implemented

## Date
- February 24, 2026

## Scope Completed
- Admin-led nurse suggestion and final decision flow
- User request enhancements (notes, shifts, evaluation type, admission details)
- Notification system for request lifecycle events
- Healthcare professional categorization
- Unified user role naming to `END_USER`

## 1) Care Request Workflow (via `Appointment`)

### New/Updated Status Values
- `SUBMITTED`
- `UNDER_REVIEW`
- `NURSE_SUGGESTED`
- `APPROVED`
- `REJECTED`
- Existing statuses still present: `PENDING`, `CONFIRMED`, `COMPLETED`, `CANCELLED`, `NO_SHOW`, `RESCHEDULED`

### Flow
1. End user submits request (`SUBMITTED`)
2. Admin suggests nurse (`NURSE_SUGGESTED`)
3. Admin final decision:
- approve -> `APPROVED`
- reject -> `REJECTED` (with reason)

### Request Fields Added
- `additional_notes: string | null`
- `shift_type: "DAILY_PER_HOUR_12H" | "LIVE_IN_24H"`
- `evaluation_type: "ONLINE_CALL" | "PHYSICAL_VISIT" | null`
- `admission_clause_accepted: boolean`
- `admission_support_in_subscription: boolean`
- `admission_questionnaire: object`
- `suggested_nurse: uuid | null` (admin-set)
- `reviewed_by: uuid | null` (admin-set)
- `rejection_reason: string | null`
- `decision_at: datetime | null`

### Important Rule Changes
- End user no longer selects nurse during creation.
- Admin suggests nurse and does final approve/reject.
- If admission support is enabled (`admission_clause_accepted` or `admission_support_in_subscription`), `admission_questionnaire` is required.
- Rejection requires `rejection_reason`.

### Required `admission_questionnaire` Keys (when required)
- `insurance_details`
- `last_procedure`
- `medical_conditions`
- `prescriptions`
- `allergies`
- `emergency_contact`
- `consent_for_emergency_admission`

## 2) Appointment Endpoints

### Existing Base
- `GET /api/appointments/`
- `POST /api/appointments/`
- `GET /api/appointments/{id}/`
- `PATCH /api/appointments/{id}/`

### New Admin Actions
- `GET /api/appointments/pending-matching/`
- `POST /api/appointments/{id}/suggest-nurse/`
- `POST /api/appointments/{id}/decision/`

### Existing Actions (behavior updated)
- `POST /api/appointments/{id}/confirm/`
  - allowed from `APPROVED` (and legacy `PENDING`)
- `POST /api/appointments/{id}/cancel/`
  - allows submitted/review/approved flow states + confirmed/pending

### Sample: Create Appointment Request
```json
{
  "family_member": "uuid",
  "appointment_date": "2026-03-01",
  "start_time": "09:00:00",
  "end_time": "11:00:00",
  "reason": "Post-discharge support",
  "service_type": "Home Visit",
  "shift_type": "DAILY_PER_HOUR_12H",
  "evaluation_type": "ONLINE_CALL",
  "visit_address": "Westlands",
  "visit_city": "Nairobi",
  "notes": "General care instructions",
  "additional_notes": "Prefer Swahili-speaking nurse",
  "admission_clause_accepted": true,
  "admission_support_in_subscription": true,
  "admission_questionnaire": {
    "insurance_details": "AAR, member #123",
    "last_procedure": "Hip surgery Jan 2026",
    "medical_conditions": "Hypertension",
    "prescriptions": "Amlodipine",
    "allergies": "Penicillin",
    "emergency_contact": "+254700000000",
    "consent_for_emergency_admission": true
  }
}
```

### Sample: Suggest Nurse (Admin)
```json
{
  "suggested_nurse": "uuid"
}
```

### Sample: Final Decision (Admin Approve)
```json
{
  "decision": "APPROVED"
}
```

### Sample: Final Decision (Admin Reject)
```json
{
  "decision": "REJECTED",
  "rejection_reason": "Incomplete medical details"
}
```

## 3) Notifications

### Event Types
- `NURSE_SUGGESTED`
- `REQUEST_APPROVED`
- `REQUEST_REJECTED`

### Endpoints
- `GET /api/notifications/`
- `GET /api/notifications/?is_read=false`
- `POST /api/notifications/{id}/mark-read/`
- `POST /api/notifications/mark-all-read/`
- `GET /api/notifications/unread-count/`

### Notification Payload Fields
- `id`
- `recipient`
- `appointment`
- `event_type`
- `event_type_display`
- `title`
- `message`
- `is_read`
- `created_at`

## 4) Healthcare Professional Categories

### New Field on Nurse
- `professional_type`

### Values
- `PHYSIOTHERAPIST`
- `CAREGIVER_NURSE`
- `PALLIATIVE_CARE_NURSE`

### API Support
- Included in nurse serializer:
  - `professional_type`
  - `professional_type_display`
- Filter supported:
  - `GET /api/nurses/?professional_type=PHYSIOTHERAPIST`

## 5) User Role (Unified: `END_USER`)

### What is live now
- Single end-user role: `END_USER`
- `DIASPORA_USER` is no longer part of active API contracts.

### Registration
- `role` accepts:
  - `END_USER`
  - `HEALTHCARE_NURSE`
  - `ADMIN`

### Profile Endpoint
- `GET/POST/PATCH /api/end-users/`

## 6) Frontend Integration Checklist

1. Use `END_USER` for all new registrations.
2. Remove nurse selection from end-user request creation UI.
3. Add UI for:
- `additional_notes`
- `shift_type`
- `evaluation_type`
- admission fields and questionnaire
4. Add admin pages/actions:
- pending matching queue
- suggest nurse
- final approve/reject (with reason)
5. Add notifications center and unread badge using `/api/notifications/*`.
6. Add nurse filtering by `professional_type`.

## 7) Validation + Testing Status
- Migrations applied through `0005`.
- Automated tests currently passing for:
  - admin suggest/decision notifications
  - role and permission guardrails
  - unread count
  - professional type filtering/display
  - `END_USER` care request submission

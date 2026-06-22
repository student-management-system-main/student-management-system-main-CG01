# Requirements Document

## Introduction

This document defines the requirements for a modern, professional, production-ready frontend for the Student Management System. The frontend is a React + Vite single-page application that connects to an existing Flask/Python backend. It covers the complete set of features exposed by the backend API: authentication, student management, fee type management, invoice management, payment processing, transaction history, risk scoring, reporting, and audit logs. The goal is a polished, accessible, and role-aware admin portal that staff can use confidently in a real institutional environment.

The application already has a skeleton in place (Layout, Login, Dashboard, Invoices, Transactions, Reports, Audit Log pages, plus shared components). These requirements describe the full, complete feature set — what exists today may be partial and should be expanded to meet all criteria below.

---

## Glossary

- **Application**: The React + Vite frontend SPA described by this document.
- **Admin**: A logged-in user with role `admin`. Can perform all read and write operations.
- **Viewer**: A logged-in user with role `viewer`. Can read all data but cannot create, update, or delete records.
- **Student**: A person enrolled at the institution, managed via `/api/v1/students`.
- **Fee_Type**: A named, priced charge category (e.g., tuition, library fee) managed via `/api/v1/fee-types`.
- **Invoice**: A billing document generated for a Student covering one or more Fee_Types, managed via `/api/v1/invoices`.
- **Line_Item**: A single fee charge within an Invoice; links one Fee_Type to one Invoice.
- **Transaction**: A record of a payment applied to an Invoice, stored at `/api/v1/transactions`.
- **Risk_Score**: A computed numeric score (0–100) and category (low / medium / high) for a Student, read via `/api/v1/students/:id/risk`.
- **Report**: An on-demand generated data export (fee_collection or high_risk_students), produced by `/api/v1/reports`.
- **Audit_Log**: An append-only record of all create, update, deactivate, payment, and export actions, read from `/api/v1/audit`.
- **JWT**: JSON Web Token used for stateless authentication. The access token lives in React state (in memory only); the refresh token is managed by the server as an httpOnly cookie.
- **Toast**: A transient non-blocking notification shown in the UI corner for success or error feedback.

---

## Requirements

### Requirement 1: Authentication

**User Story:** As a staff member, I want to log in with my credentials and have my session persist across API calls, so that I can use the system securely without re-entering my password for every request.

#### Acceptance Criteria

1. THE Application SHALL display a login page at `/login` with username and password fields, a visible-password toggle, and a submit button.
2. WHEN a user submits the login form with valid credentials, THE Application SHALL call `POST /api/v1/auth/login`, store the returned access token in React state (not localStorage), set the user context, and redirect to `/`.
3. IF the login API returns a 401 or 403 error, THEN THE Application SHALL display the server's error message on the login form without navigating away.
4. WHEN any API call returns a 401 error (regardless of whether the access token is near expiry), THE Application SHALL silently call `POST /api/v1/auth/refresh` to obtain a new access token and retry the original request, with at most one concurrent refresh attempt queued using a promise queue.
5. IF the refresh call fails, THEN THE Application SHALL clear the session and redirect the user to `/login`.
6. WHEN a user clicks "Sign out", THE Application SHALL call `POST /api/v1/auth/logout`, clear the access token from memory, clear the user context, and redirect to `/login`.
7. THE Application SHALL attach the current JWT access token as a `Bearer` token in the `Authorization` header of every API request to protected endpoints.
8. WHERE the user role is `viewer`, THE Application SHALL hide all create, edit, deactivate, and payment action buttons and forms throughout the UI.

---

### Requirement 2: Navigation and Layout

**User Story:** As a staff member, I want a clear, persistent navigation structure, so that I can quickly move between modules without losing my place.

#### Acceptance Criteria

1. THE Application SHALL render a persistent sidebar navigation containing links to: Dashboard, Students, Invoices, Transactions, Reports, and Audit Log.
2. THE Application SHALL highlight the currently active navigation item to indicate the user's location.
3. THE Application SHALL display the current user's username and role in the sidebar footer, along with a sign-out button.
4. WHEN a user accesses any route other than `/login` without a valid session, THE Application SHALL redirect to `/login`.
5. THE Application SHALL render a top header bar showing the current page title and a live-status indicator.
6. WHERE a scheduled maintenance window starts within 24 hours, THE Application SHALL display a sticky dismissible warning banner at the top of every page.
7. THE Application SHALL be responsive: on screens narrower than 768 px the sidebar SHALL be hidden behind a hamburger toggle that opens a slide-over overlay. At exactly 768 px the sidebar SHALL remain visible without the hamburger toggle.

---

### Requirement 3: Dashboard

**User Story:** As a staff member, I want an at-a-glance overview of key financial and student metrics, so that I can quickly identify areas needing attention.

#### Acceptance Criteria

1. THE Application SHALL display four KPI cards: Total Collected (sum of paid invoice amounts), Outstanding Balance (sum of unpaid + overdue invoice balances), Overdue Invoices (count), and Active Students (count).
2. THE Application SHALL refresh KPI data automatically every 60 seconds using React Query's `refetchInterval`.
3. THE Application SHALL display a searchable, filterable student table on the dashboard showing: student name, student number, outstanding balance, overdue invoice count, risk category badge, and status badge.
4. WHEN the user types in the search field, THE Application SHALL filter the student table in real time (client-side) by student name or student number without an API call.
5. WHEN the user selects a risk level filter, THE Application SHALL filter the student table to show only students whose latest risk category matches the selection.
6. WHEN the user clicks a student row, THE Application SHALL navigate to `/students/:id`.
7. THE Application SHALL display a visual chart (bar or line) showing fee collection trends over time using invoice `created_at` and `paid_at` data.

---

### Requirement 4: Student Management

**User Story:** As an admin, I want to create, view, edit, and deactivate student records, so that I can keep enrollment and contact information accurate.

#### Acceptance Criteria

1. THE Application SHALL provide a dedicated Students page at `/students` displaying a paginated table of all students with columns: name, student number, email, phone, enrollment date, status, and risk badge.
2. WHEN the user changes the page or page-size control, THE Application SHALL call `GET /api/v1/students` with the updated `page` and `per_page` parameters and replace the table contents.
3. THE Application SHALL provide search and filter controls on the Students page for status (active / inactive) and free-text search by name or student number.
4. WHERE the user role is `admin`, THE Application SHALL display a "New Student" button that opens a modal form with fields: first name, last name, student number, email, phone, enrollment date, assigned admin ID, and SMS notifications toggle.
5. WHEN an admin submits the New Student form with valid data, THE Application SHALL call `POST /api/v1/students`, close the modal on success, show a success Toast, and refresh the student list.
6. IF the API returns a `CONFLICT` error for a duplicate student number, THEN THE Application SHALL display the error message inline in the form without closing the modal.
7. THE Application SHALL provide a Student Detail page at `/students/:id` showing all student fields, a risk assessment card, and the student's invoice list.
8. WHERE the user role is `admin`, THE Application SHALL display an "Edit" button on the Student Detail page that opens a pre-filled modal form for `PUT /api/v1/students/:id`.
9. WHEN an admin saves edits, THE Application SHALL call `PUT /api/v1/students/:id`, show a success Toast, and update the displayed data without a full page reload.
10. WHERE the user role is `admin` and the student status is `active`, THE Application SHALL display a "Deactivate" button on the Student Detail page with a confirmation dialog before calling `PATCH /api/v1/students/:id/deactivate`. Once deactivated, a student's status cannot be changed back to active through the UI.
11. IF a deactivation or update API call fails, THEN THE Application SHALL show an error Toast with the server error message and leave the modal or page open.

---

### Requirement 5: Fee Type Management

**User Story:** As an admin, I want to create and manage fee types with their amounts and due dates, so that I can keep the institution's fee schedule current.

#### Acceptance Criteria

1. THE Application SHALL provide a Fee Types section (accessible from the sidebar or Settings) displaying a table of all fee types with columns: name, description, amount, currency, due date, and active status.
2. WHEN the page loads, THE Application SHALL call `GET /api/v1/fee-types?is_active=true` by default and display only active fee types. IF that API call fails, THE Application SHALL display an error message and an empty table.
3. THE Application SHALL provide a toggle or filter control that, when switched to "Show inactive", calls `GET /api/v1/fee-types?is_active=false` and displays inactive fee types instead.
4. WHERE the user role is `admin`, THE Application SHALL display a "New Fee Type" button that opens a modal form with fields: name, description, amount, currency, due date, and active toggle.
5. WHEN an admin submits the New Fee Type form with valid data, THE Application SHALL call `POST /api/v1/fee-types`, close the modal, show a success Toast, and refresh the fee type list.
6. WHERE the user role is `admin`, THE Application SHALL display an "Edit" button per row that opens a pre-filled modal form using `PUT /api/v1/fee-types/:id` on save.
7. IF a create or update API call fails validation, THEN THE Application SHALL display field-level errors from the API response inside the modal form.

---

### Requirement 6: Invoice Management

**User Story:** As an admin, I want to generate invoices for students, view invoice details with line items, and apply payments, so that I can manage fee collection end-to-end.

#### Acceptance Criteria

1. THE Application SHALL provide an Invoices page at `/invoices` displaying a paginated table of invoices with columns: invoice number, student link, total amount, outstanding balance, status badge, and due date.
2. THE Application SHALL provide filter controls on the Invoices page for status (all / unpaid / overdue / paid / cancelled) and a student ID lookup input.
3. WHEN filter or pagination controls change, THE Application SHALL call `GET /api/v1/invoices` with the corresponding query parameters and update the table.
4. WHERE the user role is `admin`, THE Application SHALL display a "New Invoice" button that opens a multi-step modal: step 1 selects a student (searchable dropdown), step 2 selects one or more fee types (checkboxes with amount preview), step 3 enters a billing period (YYYY-MM format) and confirms the total.
5. WHEN an admin submits the New Invoice form, THE Application SHALL call `POST /api/v1/invoices`, show a success Toast, and refresh the invoices list.
6. IF the API returns `DUPLICATE_INVOICE` (409), THEN THE Application SHALL display the error message inside the modal and keep the modal open.
7. IF the API returns `STUDENT_INACTIVE` (422), THEN THE Application SHALL display an inline error message immediately, regardless of which step of the multi-step modal the user is currently on.
8. THE Application SHALL provide an Invoice Detail view (modal or separate page) opened when the user clicks an invoice row, showing: all invoice fields, line items with fee type name and amount, and payment history.
9. WHERE the user role is `admin` and the invoice status is `unpaid` or `overdue`, THE Application SHALL display a "Record Payment" form on the Invoice Detail view with amount and payment method fields.
10. WHEN an admin submits a payment, THE Application SHALL call `POST /api/v1/invoices/:id/payments`, update the displayed balance and status in place, and show a success Toast.
11. IF the payment amount exceeds the outstanding balance (422 `PAYMENT_EXCEEDS_BALANCE`), THEN THE Application SHALL show an inline validation error on the payment form.

---

### Requirement 7: Transaction History

**User Story:** As a staff member, I want to view a complete transaction history, so that I can verify payments and reconcile accounts.

#### Acceptance Criteria

1. THE Application SHALL provide a Transactions page at `/transactions` displaying a paginated table of all transactions with columns: transaction reference, student link, invoice link, amount, payment method, type (payment / reversal), and created date.
2. THE Application SHALL provide filter controls on the Transactions page for transaction type and a date range picker (date_from / date_to).
3. WHEN the user applies filters or changes pages, THE Application SHALL call the transactions API with the updated parameters and refresh the table. THE Application SHALL also refresh the table on initial page load.
4. THE Application SHALL format all monetary amounts using the locale currency formatter (e.g., `$1,234.56`).
5. THE Application SHALL display a "Reversal" badge in a distinct color for reversal-type transactions.

---

### Requirement 8: Risk Scoring

**User Story:** As an admin, I want to view a student's risk score and trigger batch rescoring, so that I can proactively manage students at risk of non-payment.

#### Acceptance Criteria

1. THE Application SHALL display the latest risk score and category (low / medium / high) for a student on the Student Detail page, including the numeric score on a 0–100 progress bar, the model version, and the computed-at date.
2. THE Application SHALL color-code risk badges consistently: green for low, amber for medium, red for high. The displayed color SHALL always match the received `risk_category` value from the API, regardless of any other data fields.
3. WHERE the user role is `admin`, THE Application SHALL display a "Trigger Batch Rescore" button on the Dashboard or a dedicated Risk page that calls `POST /api/v1/risk/batch`.
4. WHEN batch rescoring is triggered, THE Application SHALL show a Toast confirming the job was queued (202 response) and disable the button for 10 seconds to prevent duplicate submissions.
5. IF the risk score API returns a 404 or no data, THE Application SHALL display a "No score computed yet" message instead of an error.

---

### Requirement 9: Reports

**User Story:** As a staff member, I want to generate and export financial and risk reports with configurable filters, so that I can share data with stakeholders.

#### Acceptance Criteria

1. THE Application SHALL provide a Reports page at `/reports` with a filter form supporting: report type (fee_collection / high_risk_students), date range (date_from / date_to), invoice status, and risk category.
2. WHEN the user clicks "Generate Report", THE Application SHALL call `POST /api/v1/reports` with the selected filters, display the returned records in a preview table, and store the `report_id`.
3. THE Application SHALL display a row count and the applied filters summary above the preview table.
4. THE Application SHALL provide "Export CSV" and "Export PDF" buttons that call `GET /api/v1/reports/:id/export?format=csv` and `GET /api/v1/reports/:id/export?format=pdf` respectively and trigger a file download in the browser.
5. IF a report export call returns 404 (expired report), THEN THE Application SHALL immediately disable the "Export CSV" and "Export PDF" buttons and show an error Toast with the message "Report has expired. Please generate a new report." The user may immediately generate a new report without refreshing the page.
6. WHILE a report is being generated, THE Application SHALL display a loading indicator and disable the generate button to prevent duplicate submissions.

---

### Requirement 10: Audit Log

**User Story:** As an admin, I want to browse the append-only audit log with filters, so that I can investigate what changes were made and by whom.

#### Acceptance Criteria

1. THE Application SHALL provide an Audit Log page at `/audit-log` accessible only to admin-role users; viewers attempting to access this route SHALL be redirected to `/`.
2. THE Application SHALL display a paginated table of audit log entries with columns: ID, actor ID, resource type, resource ID, action, and created date.
3. THE Application SHALL provide filter controls for date range (date_from / date_to), actor ID, resource type, and action.
4. WHEN the user applies filters or changes pages, THE Application SHALL call `GET /api/v1/audit` with the corresponding query parameters and update the table.
5. THE Application SHALL render the `previous_values` and `new_values` JSON fields in a collapsible expandable row section (click to expand) formatted as pretty-printed JSON.
6. THE Application SHALL default to 50 entries per page, with a page-size selector offering 25, 50, and 100.

---

### Requirement 11: Global UX and Design

**User Story:** As a staff member, I want a consistent, polished, and accessible user interface, so that I can use the system comfortably and efficiently every day.

#### Acceptance Criteria

1. THE Application SHALL use Tailwind CSS utility classes consistently with the established design system (violet primary accent, slate neutrals, card / badge / button / input / table-* CSS component classes defined in `index.css`).
2. THE Application SHALL display a loading spinner with a descriptive label whenever an API request is in-flight for data required to render the page.
3. THE Application SHALL display a user-friendly error message (using the `ErrorAlert` component or an equivalent) when an API call fails, showing the server's error message where available and avoiding raw stack traces.
4. THE Application SHALL show Toast notifications (success in green, error in red) for all create, update, deactivate, and payment operations, appearing in the bottom-right corner and auto-dismissing after 4 seconds. Toast notifications are required and SHALL always be displayed when their triggering operation occurs.
5. THE Application SHALL include keyboard-navigable modals: focus SHALL be trapped inside an open modal, pressing Escape SHALL close the modal, and focus SHALL return to the trigger element on close.
6. THE Application SHALL provide `aria-label` attributes on all icon-only buttons and `aria-live` regions for Toast notifications.
7. THE Application SHALL format all dates using the user's locale via `Intl.DateTimeFormat` and all currency values using `Intl.NumberFormat` with the correct currency code.
8. WHEN a paginated table has zero results matching the current filters, THE Application SHALL display an empty-state illustration or message in the table body rather than an empty table.
9. THE Application SHALL preserve scroll position and filter state when navigating back from a detail page to a list page using React Router state or React Query's cache.
10. THE Application SHALL support a dark mode toggle that switches the UI between the light (default) and dark Tailwind color variants and persists the preference to `localStorage`.

# Incident Timestamp Display

## Goal

Make TomTom incident timing understandable to managers and supervisors without
crowding the executive dashboard.

## Display

- Priority Alert cards show compact relative timing, such as
  `Started 2h ago · Updated 12m ago`.
- The selected Context panel shows exact Toronto-local values for `Started`,
  `Last confirmed`, and `Expected end`, with a relative-time caption.
- Corridor Analysis shows compact `Age` and `Last update` columns.
- Missing timestamps display as `Not provided`.
- Long-running incidents use wording such as
  `Ongoing 30d · confirmed today` when recently reconfirmed.

## Behavior

The UI uses TomTom `startTime`, `lastReportTime`, and `endTime`, which are
already normalized into `TrafficIncident`. This change does not discard an
incident solely because it began a long time ago; a long-lived closure can
still be operationally relevant.

## Testing

Unit tests cover recent, long-running, future, and missing timestamps. The
Streamlit dashboard is then checked to confirm the timing appears in all three
surfaces without disrupting the existing layout.

# PRAMANA — SYNCHRONIZATION & CONFLICT RESOLUTION ENGINE
**Idempotent Event Ingestion, State Reconciliation & Audit Receipts**  
**SIH 2026 Problem Statement 26261 (AICTE, Regulation Bureau)**  
**Document Reference:** `docs/SYNC_AND_CONFLICT_RESOLUTION.md`  

---

## 1. Overview of Synchronization In rural inspections, field officers and central server registries evolve asynchronously. PRAMANA provides an **Idempotent, Conflict-Aware Synchronization Engine**:
* Offline actions are recorded as independent, immutable events identified by client-generated UUIDs (`device_event_id`).
* Network dropouts and re-transmissions are processed idempotently without creating duplicate records.
* Discrepancies between field observations and central records are detected across multiple scenarios and routed to an explicit reconciliation workflow.

---

## 2. Supported Conflict Scenarios

| Conflict Type | Trigger Condition | System Behavior |
|---|---|---|
| `CONCURRENT_OFFICER_EDIT` | Server application round has advanced (e.g. from R1 to R2) while inspector was working offline. | Event is tagged `CONFLICT_DETECTED`; inspection updates are quarantined pending officer review. |
| `INSTITUTION_EVIDENCE_REPLACED` | Institution uploaded replacement documents on the central portal after the case bundle was exported. | Flags potential document substitution; surfaces side-by-side diff. |
| `SIGNED_REPORT_EVIDENCE_ALTERED` | Sync batch attempts to modify checklist or evidence on an already digitally signed report. | State transition blocked; report integrity preserved. |
| `DUPLICATE_OR_RETRY` | Network timeout caused client to re-send an event that the server already processed. | Server returns `DUPLICATE_IGNORED` and the existing sync receipt without duplicate database rows. |

---

## 3. Explicit Conflict States & Transition Flow

```
                      +-------------------+
                      |   OFFLINE EVENT   |
                      +-------------------+
                                |
                                v
                   [ Idempotency Evaluation ]
                                |
               +----------------+----------------+
               |                                 |
       (Event ID Seen)                   (New Event ID)
               |                                 |
               v                                 v
     +-------------------+              [ Conflict Evaluator ]
     | DUPLICATE_IGNORED |                       |
     | (Return Receipt)  |             +---------+---------+
     +-------------------+             |                   |
                                (Discrepancy)           (Clean)
                                       |                   |
                                       v                   v
                             +-------------------+  +---------------+
                             | CONFLICT_DETECTED |  | SYNCHRONIZED  |
                             +-------------------+  +---------------+
                                       |
                                       v
                             [ Officer Scrutiny ]
                                       |
                         +-------------+-------------+
                         |                           |
                     (Accept)                    (Reject)
                         |                           |
                         v                           v
                  +--------------+            +--------------+
                  |   RESOLVED   |            |   REJECTED   |
                  +--------------+            +--------------+
```

---

## 4. Verifiable Synchronization Receipts

Every synchronization transaction yields a cryptographically verifiable receipt bound to the live Merkle audit head:

```json
{
  "receipt_id": "RCPT-8B2A91D4E03F",
  "issued_at": "2026-11-01T14:30:00Z",
  "officer_id": "officer_deshmukh",
  "events_processed": 5,
  "conflicts_detected": 0,
  "merkle_head_seq": 482,
  "merkle_head_hash": "a4f89b6c8137f81a7b...",
  "receipt_signature": "d3819c904fa..."
}
```

### Properties:
1. **Merkle Anchor:** Anchors the exact audit state at the moment of synchronization.
2. **Deterministic Sequence:** Enables proof of sequential event ordering.
3. **Audit Trail Event:** Automatically logs an `inspection.offline_sync_processed` record into the permanent ledger.


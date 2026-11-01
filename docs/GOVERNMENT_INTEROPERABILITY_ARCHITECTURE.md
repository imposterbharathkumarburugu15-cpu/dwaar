# Government Interoperability Architecture

## Architecture Overview
The PRAMANA Interoperability layer decouples internal application scrutiny from external government data exchanges through a 4-tier gateway architecture:

```
[ Institutional Applicant / Scrutiny Officer ]
                     │
                     ▼
       [ Consent & Authorization Service ]
                     │ (Active & Validated)
                     ▼
  [ 12-Step Government Verification Engine ]
                     │
                     ▼
     [ Outbound Security Gateway (SSRF/CB) ]
          │                   │
          ▼                   ▼
   [ API Setu Adapter ]  [ DigiLocker Adapter ]
```

## Security & Privacy Controls
1. **SSRF Guard**: Strict domain whitelist rejecting private IPs, loopbacks, and arbitrary ports.
2. **Circuit Breaker**: Isolates cascading failures with CLOSED -> OPEN -> HALF_OPEN states.
3. **Redaction**: Authorization tokens, API keys, and private claims are scrubbed prior to logging.
4. **Audit Immutability**: All external verification requests and verdicts commit to the hash-chained audit ledger.


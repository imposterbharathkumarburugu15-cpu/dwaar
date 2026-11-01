# Phase 5 Known Limitations

1. **Live Production Credentials**: In adherence to SIH rules and developer confidentiality guidelines, no live production government keys are bundled. All outbound testing runs in `SIMULATED_SANDBOX` or `REAL_SANDBOX` if configured.
2. **mTLS Client Certificates**: Government mTLS requirements for direct API Setu production endpoints require hardware-backed HSM certificates provisioned by NIC/CCA, which are simulated in the local environment.
3. **Network Isolation**: When running completely offline during field inspections, external verification requests are queued for deferred synchronization.


# PRAMANA — Known Limitations & Operational Constraints

1. **Government API Credentials**: Live production access to API Setu, DigiLocker, and state revenue portals requires formal statutory memorandums of understanding (MoU) and PKCS#11 hardware security modules (HSM) provisioned by the National Informatics Centre (NIC). These are simulated locally using authentic schemas clearly labeled `SIMULATED_SANDBOX`.
2. **Offline Hardware Keys**: While offline Ed25519 cryptographic signing is fully functional on field tablets, physical FIPS 140-3 Level 3 USB cryptographic tokens require vendor driver installations specific to the operating system.
3. **Database Concurrency in Local Mode**: When executing locally without PostgreSQL, SQLite runs in WAL mode. High-volume parallel concurrent writes are queued to avoid busy locks. Production deployments use PostgreSQL 16 with PgBouncer connection pooling.


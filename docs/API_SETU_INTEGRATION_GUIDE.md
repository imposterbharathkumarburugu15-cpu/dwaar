# API Setu Integration Guide

## Overview
PRAMANA integrates with API Setu National Data Exchange to verify revenue land titles, fire safety NOCs, and society registrations.

## Authentication & Headers
- `X-APISETU-CLIENTID`: Registered application ID
- `X-APISETU-APIKEY`: Secure API key (stored in secure keystore, never logged)
- Base URL: `https://sandbox.apisetu.gov.in/v1`

## Dual-Mode Operation
- **REAL_SANDBOX**: Activated when client ID and API key are configured in environment.
- **SIMULATED_SANDBOX**: Used in offline development and SIH demonstrations. Returns authentic government schema payloads clearly marked with `is_simulation: true`.


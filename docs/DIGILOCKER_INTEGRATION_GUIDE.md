# DigiLocker & National Academic Depository (NAD) Integration Guide

## Overview
DigiLocker integration enables automated retrieval of approved academic letters, Letters of Approval (LoA), and accreditation certificates via standard canonical URIs.

## URI Schema
Canonical URI format: `in.gov.<issuer>-<doc_type>-<id>`
Example: `in.gov.aicte-LOA-2025-001234`

## Verification Pipeline
1. URI syntax validation.
2. Purpose-bound consent check.
3. XML DSig signature verification against CCA trust anchors.
4. Extracted approval parameters cross-checked against application claims.


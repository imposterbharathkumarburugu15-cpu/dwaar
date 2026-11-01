export interface KmsKey {
  id: string;
  key_id: string;
  algorithm: string;
  key_purpose: string;
  provider_type: string;
  status: "GENERATED" | "ACTIVE" | "ROTATION_PENDING" | "RETIRED" | "REVOKED" | "COMPROMISED" | "ARCHIVED";
  version: number;
  public_key_fingerprint: string;
  created_at: string;
  activated_at: string | null;
  usage_count: number;
}

export interface HsmProviderHealth {
  provider_name: string;
  provider_type: string;
  is_hardware_backed: boolean;
  status: string;
  status_message: string;
  algorithms_supported: string[];
  diagnostics: Record<string, unknown>;
}

export interface HsmHealthResponse {
  system_time: string;
  active_provider: string;
  providers: Record<string, HsmProviderHealth>;
}

export interface CertificateItem {
  id: string;
  serial_number: string;
  issuer_dn: string;
  subject_dn: string;
  fingerprint_sha256: string;
  not_before: string;
  not_after: string;
  trust_status: string;
  revocation_status: string;
  crl_distribution_points: string[];
  ocsp_responder_urls: string[];
}

export interface CertValidationResponse {
  status: "VALID" | "EXPIRED" | "NOT_YET_VALID" | "UNTRUSTED_ISSUER" | "INVALID_SIGNATURE" | "REVOKED" | "INVALID_FORMAT";
  valid: boolean;
  subject_dn: string;
  issuer_dn: string;
  serial_number: string;
  fingerprint_sha256: string;
  days_until_expiry: number;
  is_self_signed: boolean;
  is_trust_anchor: boolean;
  error?: string | null;
  warnings?: string[];
}

export interface CRLItem {
  id: string;
  issuer_dn: string;
  crl_number: number;
  this_update: string;
  next_update: string;
  revoked_count: number;
  status: string;
  signature_valid: boolean;
  synced_at: string;
}

export interface TrustAnchorItem {
  entry_id: string;
  environment: string;
  version: number;
  certificate_id: string;
  subject_dn: string;
  issuer_dn: string;
  serial_number: string;
  fingerprint_sha256: string;
  not_after: string;
  added_by: string;
  added_at: string;
}

export interface IncidentItem {
  id: string;
  incident_type: string;
  affected_key_id: string | null;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  description: string;
  status: "OPEN" | "INVESTIGATING" | "CONTAINED" | "RESOLVED";
  reported_by: string;
  reported_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  actions_taken: Array<Record<string, unknown>>;
}


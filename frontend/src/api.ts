import type {
  ActiveRuleset,
  Application,
  ApplicationDetail,
  AuditEvent,
  CampusPayload,
  ChainVerification,
  Checkpoint,
  Dashboard,
  Declared,
  DemoAccounts,
  DocumentDetail,
  DocumentSummary,
  Finding,
  Institution,
  NewApplicationBody,
  PdfVerifyResult,
  PlatformStatus,
  QueuedRun,
  RectificationItem,
  ReplayResult,
  RetentionPlan,
  ReviewAction,
  ReviewEntry,
  RuleImpact,
  RunBrief,
  RunFull,
  RunMetrics,
  RunProgress,
  SessionInfo,
  SimIssuer,
  SimLookup,
  VerificationAttempt,
} from "./types";
import type { FacultyOverlapPayload, NetworkPayload } from "./pages/integrity/types";
import type { DrishtiAskBody, DrishtiAskResponse, DrishtiLanguage, DrishtiSuggestionsPayload } from "./drishti/types";
import type {
  CertificateItem,
  CertValidationResponse,
  CRLItem,
  HsmHealthResponse,
  IncidentItem,
  KmsKey,
  TrustAnchorItem,
} from "./pages/trust/types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

function describeDetail(detail: unknown, status: number, statusText: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    // FastAPI request validation errors: [{loc, msg, type}]
    const parts = detail.map((d) => {
      if (d && typeof d === "object") {
        const loc = Array.isArray((d as { loc?: unknown[] }).loc)
          ? (d as { loc: unknown[] }).loc.filter((x) => x !== "body").join(".")
          : "";
        const msg = String((d as { msg?: unknown }).msg ?? "invalid value");
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(d);
    });
    if (parts.length) return parts.join("; ");
  }
  if (status === 0) return `The Pramana server at ${window.location.origin} could not be reached. Check that it is running and reachable from this device.`;
  return `${status} ${statusText || "Request failed"}`;
}

export type Body = FormData | object | undefined;

export async function request<T>(method: string, path: string, body?: Body): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET" && csrfToken) headers["x-csrf-token"] = csrfToken;

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload, credentials: "include" });
  } catch {
    throw new ApiError(0, describeDetail(undefined, 0, ""), undefined);
  }
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, describeDetail(detail, res.status, res.statusText), detail);
  }
  return data as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: Body) => request<T>("POST", path, body ?? {});
const patch = <T>(path: string, body: Body) => request<T>("PATCH", path, body);

const enc = encodeURIComponent;

export const api = {
  // Auth
  login: (username: string, password: string) => post<SessionInfo>("/auth/login", { username, password }),
  logout: () => post<{ ok: boolean }>("/auth/logout"),
  me: () => get<SessionInfo>("/auth/me"),
  demoAccounts: () => get<DemoAccounts>("/auth/demo-accounts"),

  // Official workspace
  dashboard: () => get<Dashboard>("/dashboard"),
  runMetrics: () => get<RunMetrics>("/metrics/runs"),

  // Applications
  applications: () => get<Application[]>("/applications"),
  createApplication: (body: NewApplicationBody) => post<Application>("/applications", body),
  application: (id: string) => get<ApplicationDetail>(`/applications/${enc(id)}`),
  updateDeclared: (id: string, declared: Declared) =>
    patch<Application>(`/applications/${enc(id)}/declared`, { declared }),
  uploadDocument: (id: string, declaredType: string, file: File) => {
    const fd = new FormData();
    fd.append("declared_type", declaredType);
    fd.append("file", file, file.name);
    return post<DocumentSummary>(`/applications/${enc(id)}/documents`, fd);
  },
  submit: (id: string) =>
    post<{ application: Application; run: (RunBrief & { background?: boolean }) | null }>(`/applications/${enc(id)}/submit`),
  validate: (id: string) => post<RunFull | QueuedRun>(`/applications/${enc(id)}/validate`),
  reprocess: (id: string) => post<QueuedRun>(`/applications/${enc(id)}/reprocess`),
  retryRun: (runId: string) => post<QueuedRun>(`/runs/${enc(runId)}/retry`),
  activeRun: (id: string) => get<{ run: RunBrief | null }>(`/applications/${enc(id)}/active-run`),
  runProgress: (runId: string, after: number) => get<RunProgress>(`/runs/${enc(runId)}/progress?after=${after}`),
  runEventsUrl: (runId: string, after: number) => `/api/runs/${enc(runId)}/events?after=${after}`,
  runs: (id: string) => get<RunBrief[]>(`/applications/${enc(id)}/runs`),
  run: (runId: string) => get<RunFull>(`/runs/${enc(runId)}`),
  replay: (runId: string) => post<ReplayResult>(`/runs/${enc(runId)}/replay`),
  findings: (id: string, runId?: string) =>
    get<Finding[]>(`/applications/${enc(id)}/findings${runId ? `?run_id=${enc(runId)}` : ""}`),
  verifications: (id: string) => get<VerificationAttempt[]>(`/applications/${enc(id)}/verifications`),
  applicationAudit: (id: string) => get<AuditEvent[]>(`/applications/${enc(id)}/audit`),
  requestRectification: (id: string, findingIds: string[], message: string | null) =>
    post<{ id: string; round: number; items: RectificationItem[] }>(`/applications/${enc(id)}/rectification`, {
      finding_ids: findingIds,
      message,
    }),
  institution: (id: string) => get<Institution>(`/institutions/${enc(id)}`),

  // Documents
  document: (docId: string) => get<DocumentDetail>(`/documents/${enc(docId)}`),
  pageImageUrl: (docId: string, page: number) => `/api/documents/${enc(docId)}/pages/${page}.png`,
  fileUrl: (docId: string) => `/api/documents/${enc(docId)}/file`,
  photoUrl: (docId: string, size: "thumb" | "preview" = "thumb") => `/api/documents/${enc(docId)}/photo.jpg?size=${size}`,

  // Campus map and photo evidence (officials only)
  campus: (id: string) => get<CampusPayload>(`/applications/${enc(id)}/campus`),

  // Cycle-wide integrity insights (officials only)
  integrityNetwork: (dataset: "current" | "synthetic" = "current") => get<NetworkPayload>(`/insights/network?dataset=${dataset}`),
  facultyOverlaps: () => get<FacultyOverlapPayload>("/insights/faculty-overlaps"),

  // Findings and verification
  reviewFinding: (findingId: string, action: ReviewAction, note: string | null) =>
    post<Finding>(`/findings/${enc(findingId)}/review`, { action, note }),
  findingHistory: (findingId: string) => get<ReviewEntry[]>(`/findings/${enc(findingId)}/history`),
  manualVerification: (attemptId: string, status: string, note: string) =>
    post<VerificationAttempt>(`/verifications/${enc(attemptId)}/manual`, { status, note }),
  officerReview: (docId: string, note: string) => post<VerificationAttempt>(`/documents/${enc(docId)}/officer-review`, { note }),

  // Rules
  activeRuleset: () => get<ActiveRuleset>("/rulesets/active"),
  ruleImpact: () => get<RuleImpact>("/rulesets/impact"),

  // Audit
  audit: (limit = 200) => get<AuditEvent[]>(`/audit?limit=${limit}`),
  verifyAudit: () => get<ChainVerification>("/audit/verify"),
  checkpoint: () => post<Checkpoint>("/audit/checkpoint"),

  // Tools
  verifyPdf: (file: File) => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    return post<PdfVerifyResult>("/tools/verify-pdf", fd);
  },

  // Platform
  platformStatus: () => get<PlatformStatus>("/admin/platform"),
  retentionPlan: () => get<RetentionPlan>("/admin/retention"),
  retentionPurge: (dryRun: boolean, reason?: string) =>
    post<RetentionPlan>("/admin/retention/purge", { dry_run: dryRun, reason }),

  // Simulated issuers
  simIssuers: () => get<SimIssuer[]>("/sim/issuers"),
  setIssuerAvailability: (code: string, available: boolean) =>
    post<SimIssuer>(`/sim/issuers/${enc(code)}/availability`, { available }),
  simLookup: (code: string, ref: string) => get<SimLookup>(`/sim/issuers/${enc(code)}/lookup?ref=${enc(ref)}`),

  // Drishti, the assistant (docs/features/drishti-spec.md)
  drishtiAsk: (body: DrishtiAskBody) => post<DrishtiAskResponse>("/drishti/ask", body),
  drishtiSuggestions: (lang: DrishtiLanguage = "en") => get<DrishtiSuggestionsPayload>(`/drishti/suggestions?lang=${lang}`),

  // Intelligence Systems (SIH 2026 Problem Statement 26261)
  rulesets: () => get<any[]>("/intelligence/regulatory/rulesets"),
  compareRulesets: (base: string, target: string) =>
    get<any>(`/intelligence/regulatory/compare?base_version=${enc(base)}&target_version=${enc(target)}`),
  simulateRules: (body: any) => post<any>("/intelligence/regulatory/simulate", body),
  crossDoc: (appId: string) => get<any>(`/intelligence/applications/${enc(appId)}/cross-doc`),
  institutionRisk: (instId: string) => get<any>(`/intelligence/risk/institution/${enc(instId)}`),
  sectorRisk: () => get<any>("/intelligence/risk/sector-observatory"),
  applicationLifecycle: (appId: string) => get<any>(`/intelligence/applications/${enc(appId)}/lifecycle`),
  exportOfflineBundle: (appId: string) => get<any>(`/intelligence/offline/bundle/${enc(appId)}`),
  syncOffline: (body: any) => post<any>("/intelligence/offline/sync", body),
  reconcileOffline: (body: any) => post<any>("/intelligence/offline/reconcile", body),
  // Phase 2: Offline Field Scrutiny & Tablet Signing
  listFieldInspections: () => get<any[]>("/offline/inspections"),
  createFieldInspection: (body: any) => post<any>("/offline/inspections", body),
  getFieldInspection: (id: string) => get<any>(`/offline/inspections/${enc(id)}`),
  attachFieldEvidence: (id: string, body: any) => post<any>(`/offline/inspections/${enc(id)}/evidence`, body),
  signInspectionReport: (id: string, body: any) => post<any>(`/offline/inspections/${enc(id)}/sign`, body),
  verifyInspectionSignature: (id: string) => post<any>(`/offline/inspections/${enc(id)}/verify-signature`, {}),
  verifyOfflineQr: (body: any) => post<any>("/offline/qr/verify", body),
  syncOfflineBatch: (body: any) => post<any>("/offline/sync/batch", body),
  resolveOfflineConflict: (body: any) => post<any>("/offline/sync/resolve", body),
  auditReceipt: () => get<any>("/intelligence/audit/receipt"),
  simulateAuditTamper: () => post<any>("/intelligence/audit/simulate-tamper", {}),
  deficiencyNoticeDraft: (appId: string) =>
    get<any>(`/intelligence/applications/${enc(appId)}/deficiency-notice-draft`),
  investigationBrief: (appId: string) =>
    get<any>(`/intelligence/applications/${enc(appId)}/investigation-brief`),
  trustKeys: () => get<KmsKey[]>("/trust/keys"),
  trustKey: (keyId: string) => get<KmsKey>(`/trust/keys/${enc(keyId)}`),
  generateTrustKey: (body: { key_id: string; algorithm: string; key_purpose: string; provider_type?: string }) =>
    post<KmsKey>("/trust/keys", body),
  rotateTrustKey: (keyId: string, body: { rotation_reason: string; grace_period_days?: number }) =>
    post<{ status: string; old_key_id: string; new_key_id: string; new_version: number }>(`/trust/keys/${enc(keyId)}/rotate`, body),
  revokeTrustKey: (keyId: string, body: { reason: string }) =>
    post<{ status: string; key_id: string }>(`/trust/keys/${enc(keyId)}/revoke`, body),
  hsmHealth: () => get<HsmHealthResponse>("/trust/hsm/health"),
  certificates: () => get<CertificateItem[]>("/trust/certificates"),
  validateCert: (body: { certificate_pem: string; environment?: string }) =>
    post<CertValidationResponse>("/trust/certificates/validate", body),
  crlList: () => get<CRLItem[]>("/trust/crl"),
  syncCrl: (body: { crl_bytes_b64: string; issuer_cert_pem: string }) =>
    post<any>("/trust/crl/sync", body),
  trustAnchors: (env: string = "development") =>
    get<TrustAnchorItem[]>(`/trust/anchors?environment=${enc(env)}`),
  addTrustAnchor: (body: { certificate_id: string; environment?: string }) =>
    post<any>("/trust/anchors", body),
  removeTrustAnchor: (certificateId: string, env: string = "development") =>
    post<any>(`/trust/anchors/${enc(certificateId)}/remove?environment=${enc(env)}`, {}),
  trustIncidents: () => get<IncidentItem[]>("/trust/incidents"),
  raiseIncident: (body: { incident_type: string; description: string; affected_key_id?: string; severity?: string }) =>
    post<IncidentItem>("/trust/incidents", body),
  recoverIncident: (incidentId: string, body: { generate_replacement_key?: boolean; resolution_notes?: string }) =>
    post<any>(`/trust/incidents/${enc(incidentId)}/recover`, body),
};

export const qk = {
  me: ["me"] as const,
  demo: ["demo-accounts"] as const,
  dashboard: ["dashboard"] as const,
  metrics: ["metrics"] as const,
  applications: ["applications"] as const,
  application: (id: string) => ["application", id] as const,
  runs: (id: string) => ["application", id, "runs"] as const,
  findings: (id: string, runId?: string) => ["application", id, "findings", runId ?? "latest"] as const,
  verifications: (id: string) => ["application", id, "verifications"] as const,
  appAudit: (id: string) => ["application", id, "audit"] as const,
  campus: (id: string) => ["application", id, "campus"] as const,
  integrityNetwork: (dataset: "current" | "synthetic" = "current") => ["insights", "network", dataset] as const,
  facultyOverlaps: ["insights", "faculty-overlaps"] as const,
  run: (runId: string) => ["run", runId] as const,
  activeRun: (id: string) => ["application", id, "active-run"] as const,
  document: (docId: string) => ["document", docId] as const,
  history: (findingId: string) => ["finding-history", findingId] as const,
  ruleset: ["ruleset"] as const,
  impact: ["rule-impact"] as const,
  audit: ["audit"] as const,
  issuers: ["sim-issuers"] as const,
  platform: ["platform"] as const,
  retention: ["retention"] as const,
  drishtiSuggestions: (lang: string) => ["drishti", "suggestions", lang] as const,
  rulesetsList: ["intelligence", "rulesets"] as const,
  rulesetDiff: (base: string, target: string) => ["intelligence", "ruleset-diff", base, target] as const,
  sectorRisk: ["intelligence", "sector-risk"] as const,
  instRisk: (instId: string) => ["intelligence", "institution-risk", instId] as const,
  crossDoc: (appId: string) => ["intelligence", "cross-doc", appId] as const,
  lifecycle: (appId: string) => ["intelligence", "lifecycle", appId] as const,
  brief: (appId: string) => ["intelligence", "brief", appId] as const,
  deficiencyDraft: (appId: string) => ["intelligence", "deficiency-draft", appId] as const,
  trustKeys: ["trust", "keys"] as const,
  hsmHealth: ["trust", "hsm-health"] as const,
  certificates: ["trust", "certificates"] as const,
  crlList: ["trust", "crl-list"] as const,
  trustAnchors: (env: string) => ["trust", "anchors", env] as const,
  trustIncidents: ["trust", "incidents"] as const,
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}

// Shapes of the staff resource endpoints (backend/app/schemas/resource.py,
// docs/design-rag.md §7.5). Kept apart from types.ts, which mirrors the
// student app's file.

export type ResourceType = 'SYLLABUS' | 'SCHEDULE' | 'REPO';

// One index_syncs row: a source's last sync under one ingestion profile.
export interface SyncStatus {
  profile: string;
  last_synced_at: string | null;
  chunk_count: number;
  truncated_chunk_count: number;
  commit_sha: string | null;
  last_error: string | null;
  last_error_at: string | null;
}

export interface SourceStatus {
  syncing: boolean;
  // The source's profiles hold different versions of it (§7.3).
  version_mismatch: boolean;
  syncs: SyncStatus[];
}

export interface Resource extends SourceStatus {
  id: number;
  type: ResourceType;
  title: string;
  origin: 'URL' | 'UPLOAD';
  fetch_url: string | null;
  link_base_url: string | null;
  repo_branch: string | null;
  created_at: string;
}

export interface ResourceList {
  live_profile: string;
  profiles: string[];
  resources: Resource[];
  historical_qa: SourceStatus;
}

export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  SYLLABUS: 'Syllabus',
  SCHEDULE: 'Schedule',
  REPO: 'Repository',
};

// The backend stores UTC without a zone ("2026-10-21T20:30:39"); without
// the Z the browser would read it as local time.
export function formatTimestamp(value: string | null): string {
  if (!value) return '—';
  const utc = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`;
  const date = new Date(utc);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

// Re-sync default (§7.5): every profile the source is already ingested
// under, or the live profile for a source with none.
export function defaultProfiles(source: SourceStatus, liveProfile: string): string[] {
  const existing = source.syncs.map((s) => s.profile);
  return existing.length > 0 ? existing : [liveProfile];
}

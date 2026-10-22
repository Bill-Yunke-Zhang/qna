import { useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, Loader2, Plus, RefreshCw, Trash2, Upload } from 'lucide-react';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import {
  RESOURCE_TYPE_LABELS,
  defaultProfiles,
  formatTimestamp,
  type Resource,
  type ResourceList,
  type ResourceType,
  type SourceStatus,
} from '../lib/resources';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

// While any source is syncing, reload every 5 s, for up to 15 minutes
// (docs/design-rag.md §7.5). The backend's `syncing` flag says when a sync
// has ended, so there is no clock comparison with the server.
const POLL_INTERVAL_MS = 5000;
const POLL_LIMIT_MS = 15 * 60 * 1000;

const selectClass =
  'w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 ' +
  'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent';
const fileClass =
  'block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 ' +
  'file:bg-slate-700 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-slate-100 ' +
  'hover:file:bg-slate-600';

function errorText(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback;
}

export default function ResourcesPage() {
  const { courseId } = useCourse();
  const [data, setData] = useState<ResourceList | null>(null);
  const [loadError, setLoadError] = useState('');
  const [stalled, setStalled] = useState(false);

  async function load() {
    if (!courseId) return;
    try {
      setData(await api.get<ResourceList>(`/courses/${courseId}/resources`));
      setLoadError('');
    } catch (err) {
      setLoadError(errorText(err, 'Failed to load resources'));
    }
  }

  useEffect(() => {
    setData(null);
    setStalled(false);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  const anySyncing = Boolean(
    data && (data.historical_qa.syncing || data.resources.some((r) => r.syncing))
  );

  useEffect(() => {
    if (!anySyncing) return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (Date.now() - started > POLL_LIMIT_MS) {
        window.clearInterval(timer);
        setStalled(true);
        return;
      }
      void load();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anySyncing, courseId]);

  // After any action: a fresh 15-minute window and the new state.
  async function changed() {
    setStalled(false);
    await load();
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold text-slate-100 mb-2">Course Resources</h2>
      <p className="text-slate-400 text-sm mb-6">
        Material the AI answers from. Each source is split into chunks and indexed under one or more
        ingestion profiles; students' questions are answered with the live profile
        {data && (
          <>
            {' '}
            (<span className="text-slate-200">{data.live_profile}</span>)
          </>
        )}
        .
      </p>

      {loadError && <p className="text-red-400 text-sm mb-4">{loadError}</p>}
      {stalled && anySyncing && (
        <p className="flex items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-600/10 px-4 py-2 mb-4 text-sm text-amber-300">
          <AlertTriangle size={14} /> No result yet. Check back or re-sync.
        </p>
      )}

      {data && courseId && (
        <>
          <AddResourceCard courseId={courseId} list={data} onChanged={changed} />
          <div className="space-y-4 mb-6">
            {data.resources.length === 0 && (
              <p className="text-slate-400 text-sm">No resources yet.</p>
            )}
            {data.resources.map((r) => (
              <ResourceCard key={r.id} courseId={courseId} resource={r} list={data} onChanged={changed} />
            ))}
          </div>
          <HistoricalQACard courseId={courseId} list={data} onChanged={changed} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared pieces
// ---------------------------------------------------------------------------

function ProfilePicker({
  list,
  value,
  onChange,
}: {
  list: ResourceList;
  value: string[];
  onChange: (profiles: string[]) => void;
}) {
  function toggle(name: string) {
    onChange(value.includes(name) ? value.filter((p) => p !== name) : [...value, name]);
  }
  return (
    <fieldset className="flex flex-wrap gap-x-4 gap-y-1">
      <legend className="text-sm text-slate-400 mb-1">Profiles</legend>
      {list.profiles.map((name) => (
        <label key={name} className="flex items-center gap-1.5 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={value.includes(name)}
            onChange={() => toggle(name)}
            className="accent-indigo-500"
          />
          {name}
          {name === list.live_profile && <span className="text-xs text-slate-400">(live)</span>}
        </label>
      ))}
    </fieldset>
  );
}

function SyncTable({ source, live }: { source: SourceStatus; live: string }) {
  if (source.syncs.length === 0) {
    return <p className="text-slate-400 text-sm">Not indexed under any profile yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-400">
            <th className="py-1 pr-4 font-medium">Profile</th>
            <th className="py-1 pr-4 font-medium">Last synced</th>
            <th className="py-1 pr-4 font-medium">Chunks</th>
            <th className="py-1 font-medium">Last error</th>
          </tr>
        </thead>
        <tbody>
          {source.syncs.map((s) => (
            <tr key={s.profile} className="border-t border-slate-700 align-top">
              <td className="py-1.5 pr-4 text-slate-200 whitespace-nowrap">
                {s.profile}
                {s.profile === live && <span className="ml-1 text-xs text-slate-400">(live)</span>}
              </td>
              <td className="py-1.5 pr-4 text-slate-300 whitespace-nowrap">
                {formatTimestamp(s.last_synced_at)}
              </td>
              <td className="py-1.5 pr-4 text-slate-300 whitespace-nowrap">
                {s.chunk_count}
                {s.truncated_chunk_count > 0 && (
                  <span className="ml-1 text-amber-300" title="Chunks cut short by the model's token limit">
                    ({s.truncated_chunk_count} truncated)
                  </span>
                )}
              </td>
              <td className="py-1.5 text-red-300">
                {s.last_error ? (
                  <>
                    {s.last_error}
                    <span className="block text-xs text-slate-400">{formatTimestamp(s.last_error_at)}</span>
                  </>
                ) : (
                  <span className="text-slate-500">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceFlags({ source }: { source: SourceStatus }) {
  return (
    <>
      {source.syncing && (
        <Badge variant="default">
          <Loader2 size={12} className="mr-1 animate-spin" /> Syncing
        </Badge>
      )}
      {source.version_mismatch && (
        <Badge variant="warning" title="The profiles hold different versions of this source. Re-sync them together.">
          Versions differ
        </Badge>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Add a resource
// ---------------------------------------------------------------------------

function AddResourceCard({
  courseId,
  list,
  onChanged,
}: {
  courseId: number;
  list: ResourceList;
  onChanged: () => Promise<void>;
}) {
  const [mode, setMode] = useState<'URL' | 'UPLOAD'>('URL');
  const [type, setType] = useState<ResourceType>('SYLLABUS');
  const [title, setTitle] = useState('');
  const [fetchUrl, setFetchUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [linkBaseUrl, setLinkBaseUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [profiles, setProfiles] = useState<string[]>([list.live_profile]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      if (mode === 'URL') {
        await api.post(`/courses/${courseId}/resources`, {
          type,
          title,
          fetch_url: fetchUrl,
          repo_branch: type === 'REPO' ? branch : null,
          profiles,
        });
      } else {
        if (!file) throw new Error('Choose a file to upload');
        const form = new FormData();
        form.append('type', type);
        form.append('title', title);
        form.append('link_base_url', linkBaseUrl);
        form.append('profiles', profiles.join(','));
        form.append('file', file);
        await api.postForm(`/courses/${courseId}/resources/upload`, form);
      }
      setTitle('');
      setFetchUrl('');
      setLinkBaseUrl('');
      setFile(null);
      setFileKey((k) => k + 1);
      await onChanged();
    } catch (err) {
      setError(errorText(err, 'Failed to add the resource'));
    } finally {
      setSaving(false);
    }
  }

  const tabClass = (active: boolean) =>
    `whitespace-nowrap px-3 py-1.5 text-sm rounded-lg ${active ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'}`;

  return (
    <Card className="mb-6">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-slate-100">Add a resource</h3>
          <div className="flex gap-1" role="tablist">
            <button type="button" role="tab" aria-selected={mode === 'URL'} className={tabClass(mode === 'URL')} onClick={() => setMode('URL')}>
              From a URL
            </button>
            <button type="button" role="tab" aria-selected={mode === 'UPLOAD'} className={tabClass(mode === 'UPLOAD')} onClick={() => setMode('UPLOAD')}>
              Upload a file
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select
              aria-label="Type"
              value={type}
              onChange={(e) => setType(e.target.value as ResourceType)}
              className={selectClass}
            >
              {(Object.keys(RESOURCE_TYPE_LABELS) as ResourceType[]).map((t) => (
                <option key={t} value={t}>
                  {RESOURCE_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
            <Input
              className="sm:col-span-2"
              placeholder="Title, e.g. Syllabus"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={255}
              required
            />
          </div>

          {mode === 'URL' ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Input
                className={type === 'REPO' ? 'sm:col-span-2' : 'sm:col-span-3'}
                type="url"
                placeholder={type === 'REPO' ? 'GitLab project URL' : 'Page URL, e.g. https://…/syllabus.html'}
                value={fetchUrl}
                onChange={(e) => setFetchUrl(e.target.value)}
                required
              />
              {type === 'REPO' && (
                <Input
                  placeholder="Branch"
                  aria-label="Branch"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  required
                />
              )}
            </div>
          ) : (
            <>
              <input
                key={fileKey}
                type="file"
                aria-label="File"
                accept={type === 'REPO' ? '.zip,.md,.pdf' : '.html,.htm'}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className={fileClass}
                required
              />
              <div>
                <Input
                  type="url"
                  placeholder="Where can people view this? e.g. https://…/syllabus.html"
                  aria-label="Where can people view this?"
                  value={linkBaseUrl}
                  onChange={(e) => setLinkBaseUrl(e.target.value)}
                  required
                />
                <p className="mt-1 text-xs text-slate-400">
                  The file itself isn't stored. AI citations link here instead
                  {type === 'REPO' ? ', followed by each file\'s path inside the zip' : ''}.
                </p>
              </div>
            </>
          )}

          <ProfilePicker list={list} value={profiles} onChange={setProfiles} />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <Button type="submit" disabled={saving || profiles.length === 0}>
            <span className="flex items-center gap-1.5">
              {mode === 'URL' ? <Plus size={16} /> : <Upload size={16} />}
              {saving ? 'Adding…' : mode === 'URL' ? 'Add and sync' : 'Upload and sync'}
            </span>
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// One resource
// ---------------------------------------------------------------------------

function ResourceCard({
  courseId,
  resource,
  list,
  onChanged,
}: {
  courseId: number;
  resource: Resource;
  list: ResourceList;
  onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState<'sync' | 'replace' | null>(null);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const base = `/courses/${courseId}/resources/${resource.id}`;
  const link = resource.origin === 'URL' ? resource.fetch_url : resource.link_base_url;

  function openPanel(panel: 'sync' | 'replace') {
    setOpen(open === panel ? null : panel);
    setProfiles(defaultProfiles(resource, list.live_profile));
    setFile(null);
    setError('');
  }

  async function run(action: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    setError('');
    try {
      await action();
      setOpen(null);
      await onChanged();
    } catch (err) {
      setError(errorText(err, fallback));
    } finally {
      setBusy(false);
    }
  }

  function handleSync(e: React.FormEvent) {
    e.preventDefault();
    void run(() => api.post(`${base}/sync`, { profiles }), 'Failed to start the sync');
  }

  function handleReplace(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    form.append('profiles', profiles.join(','));
    void run(() => api.putForm(`${base}/upload`, form), 'Failed to replace the upload');
  }

  function handleDelete() {
    if (!window.confirm(`Delete "${resource.title}" and remove it from the AI's index?`)) return;
    void run(() => api.delete(base), 'Failed to delete the resource');
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-100">{resource.title}</span>
              <Badge variant="outline">{RESOURCE_TYPE_LABELS[resource.type]}</Badge>
              <Badge variant="outline">{resource.origin === 'URL' ? 'URL' : 'Upload'}</Badge>
              <SourceFlags source={resource} />
            </div>
            {link && (
              <a
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex max-w-full items-center gap-1 text-sm text-indigo-300 hover:text-indigo-200 underline break-all"
              >
                <ExternalLink size={12} className="shrink-0" /> {link}
              </a>
            )}
            {resource.repo_branch && (
              <p className="text-xs text-slate-400">Branch: {resource.repo_branch}</p>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            {resource.origin === 'URL' ? (
              <Button variant="outline" size="sm" disabled={busy || resource.syncing} onClick={() => openPanel('sync')}>
                <span className="flex items-center gap-1.5">
                  <RefreshCw size={14} /> Re-sync
                </span>
              </Button>
            ) : (
              <Button variant="outline" size="sm" disabled={busy || resource.syncing} onClick={() => openPanel('replace')}>
                <span className="flex items-center gap-1.5">
                  <Upload size={14} /> Replace upload
                </span>
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={busy || resource.syncing}
              onClick={handleDelete}
              aria-label={`Delete ${resource.title}`}
            >
              <Trash2 size={14} />
            </Button>
          </div>
        </div>

        {open === 'sync' && (
          <form onSubmit={handleSync} className="rounded-lg border border-slate-700 p-3 space-y-3">
            <ProfilePicker list={list} value={profiles} onChange={setProfiles} />
            <Button type="submit" size="sm" disabled={busy || profiles.length === 0}>
              {busy ? 'Starting…' : 'Start sync'}
            </Button>
          </form>
        )}
        {open === 'replace' && (
          <form onSubmit={handleReplace} className="rounded-lg border border-slate-700 p-3 space-y-3">
            <input
              type="file"
              aria-label="New file"
              accept={resource.type === 'REPO' ? '.zip,.md,.pdf' : '.html,.htm'}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className={fileClass}
              required
            />
            <ProfilePicker list={list} value={profiles} onChange={setProfiles} />
            <Button type="submit" size="sm" disabled={busy || !file || profiles.length === 0}>
              {busy ? 'Uploading…' : 'Upload and sync'}
            </Button>
          </form>
        )}
        {error && <p className="text-red-400 text-sm">{error}</p>}

        <SyncTable source={resource} live={list.live_profile} />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Historical Q&A
// ---------------------------------------------------------------------------

function HistoricalQACard({
  courseId,
  list,
  onChanged,
}: {
  courseId: number;
  list: ResourceList;
  onChanged: () => Promise<void>;
}) {
  const source = list.historical_qa;
  const [open, setOpen] = useState(false);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  function toggle() {
    setOpen(!open);
    setProfiles(defaultProfiles(source, list.live_profile));
    setError('');
  }

  async function handleReindex(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.post(`/courses/${courseId}/historical-qa/sync`, { profiles });
      setOpen(false);
      await onChanged();
    } catch (err) {
      setError(errorText(err, 'Failed to start the re-index'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-100">Past Q&amp;A</span>
              <SourceFlags source={source} />
            </div>
            <p className="text-sm text-slate-400">
              Threads with a staff-verified human answer. Un-verifying an answer removes its thread
              right away; newly verified answers are added only when you re-index.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 self-start"
            disabled={busy || source.syncing}
            onClick={toggle}
          >
            <span className="flex items-center gap-1.5">
              <RefreshCw size={14} /> Re-index
            </span>
          </Button>
        </div>
        {open && (
          <form onSubmit={handleReindex} className="rounded-lg border border-slate-700 p-3 space-y-3">
            <ProfilePicker list={list} value={profiles} onChange={setProfiles} />
            <Button type="submit" size="sm" disabled={busy || profiles.length === 0}>
              {busy ? 'Starting…' : 'Start re-index'}
            </Button>
          </form>
        )}
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <SyncTable source={source} live={list.live_profile} />
      </CardContent>
    </Card>
  );
}

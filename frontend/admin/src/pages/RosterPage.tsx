import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';

interface RosterEntry {
  id: number;
  course_id: number;
  netid: string;
  full_name: string;
  email: string;
  is_active: boolean;
  imported_at: string;
}

interface RosterUploadResult {
  imported: number;
  updated: number;
  deactivated: number;
  errors: string[];
}

interface StaffMember {
  id: string;
  username: string | null;
  netid: string | null;
  display_name: string | null;
  email: string | null;
}

interface StaffUploadResult {
  accounts_created: number;
  access_granted: number;
  already_staff: number;
  errors: string[];
}

export default function RosterPage() {
  const { courseId } = useParams();
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [rosterResult, setRosterResult] = useState<RosterUploadResult | null>(null);
  const [rosterError, setRosterError] = useState('');
  const [rosterUploading, setRosterUploading] = useState(false);
  const rosterFileInput = useRef<HTMLInputElement>(null);

  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [staffResult, setStaffResult] = useState<StaffUploadResult | null>(null);
  const [staffError, setStaffError] = useState('');
  const [staffUploading, setStaffUploading] = useState(false);
  const staffFileInput = useRef<HTMLInputElement>(null);

  async function loadRoster() {
    const data = await api.get<RosterEntry[]>(`/admin/courses/${courseId}/roster`);
    setRoster(data);
  }

  async function loadStaff() {
    const data = await api.get<StaffMember[]>(`/admin/courses/${courseId}/staff`);
    setStaff(data);
  }

  useEffect(() => {
    void loadRoster();
    void loadStaff();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  async function handleRosterUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setRosterUploading(true);
    setRosterError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.postForm<RosterUploadResult>(
        `/admin/courses/${courseId}/roster`,
        form
      );
      setRosterResult(res);
      await loadRoster();
    } catch (err) {
      setRosterError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setRosterUploading(false);
      if (rosterFileInput.current) rosterFileInput.current.value = '';
    }
  }

  async function toggleActive(entry: RosterEntry) {
    await api.patch(`/admin/courses/${courseId}/roster/${entry.id}`, {
      is_active: !entry.is_active,
    });
    await loadRoster();
  }

  async function handleStaffUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStaffUploading(true);
    setStaffError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.postForm<StaffUploadResult>(
        `/admin/courses/${courseId}/staff`,
        form
      );
      setStaffResult(res);
      await loadStaff();
    } catch (err) {
      setStaffError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setStaffUploading(false);
      if (staffFileInput.current) staffFileInput.current.value = '';
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <h2 className="text-2xl font-bold text-slate-100 mb-6">Roster &amp; Staff</h2>

      <h3 className="text-lg font-semibold text-slate-100 mb-3">Student Roster</h3>

      <Card className="mb-6">
        <CardHeader>
          <h4 className="text-base font-semibold text-slate-100">Upload Canvas Gradebook CSV</h4>
          <p className="text-slate-400 text-sm mt-1">
            Expects a 'Student' and 'SIS Login ID' column. Re-uploading deactivates any netid
            missing from the new file. Access is granted automatically the next time a listed
            netid logs in — no separate step needed.
          </p>
        </CardHeader>
        <CardContent>
          <label className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 cursor-pointer hover:bg-slate-700">
            <Upload size={16} /> {rosterUploading ? 'Uploading…' : 'Choose CSV file'}
            <input
              ref={rosterFileInput}
              type="file"
              accept=".csv"
              onChange={handleRosterUpload}
              className="hidden"
              disabled={rosterUploading}
            />
          </label>
          {rosterError && <p className="text-red-400 text-sm mt-2">{rosterError}</p>}
          {rosterResult && (
            <div className="text-sm text-slate-300 mt-3">
              <p>
                Imported {rosterResult.imported}, updated {rosterResult.updated}, deactivated{' '}
                {rosterResult.deactivated}.
              </p>
              {rosterResult.errors.length > 0 && (
                <ul className="text-amber-400 list-disc list-inside mt-1">
                  {rosterResult.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {roster.length === 0 ? (
        <p className="text-slate-400 mb-8">No roster entries yet.</p>
      ) : (
        <div className="space-y-2 mb-8">
          {roster.map((r) => (
            <Card key={r.id} className="flex items-center justify-between px-6 py-3">
              <div>
                <p className="font-medium text-slate-100">
                  {r.full_name} <span className="text-slate-400">({r.netid})</span>
                </p>
                <p className="text-slate-500 text-sm">{r.email}</p>
              </div>
              <Button
                size="sm"
                variant={r.is_active ? 'outline' : 'default'}
                onClick={() => toggleActive(r)}
              >
                {r.is_active ? 'Active' : 'Inactive'}
              </Button>
            </Card>
          ))}
        </div>
      )}

      <h3 className="text-lg font-semibold text-slate-100 mb-3">Course Staff</h3>

      <Card className="mb-6">
        <CardHeader>
          <h4 className="text-base font-semibold text-slate-100">Upload Staff CSV</h4>
          <p className="text-slate-400 text-sm mt-1">
            Expects 'netid', 'full_name', and 'email' columns. Unlike the roster, this takes
            effect immediately — an account is created for any netid that doesn't have one yet,
            and STAFF access to this course is granted right away.
          </p>
        </CardHeader>
        <CardContent>
          <label className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 cursor-pointer hover:bg-slate-700">
            <Upload size={16} /> {staffUploading ? 'Uploading…' : 'Choose CSV file'}
            <input
              ref={staffFileInput}
              type="file"
              accept=".csv"
              onChange={handleStaffUpload}
              className="hidden"
              disabled={staffUploading}
            />
          </label>
          {staffError && <p className="text-red-400 text-sm mt-2">{staffError}</p>}
          {staffResult && (
            <div className="text-sm text-slate-300 mt-3">
              <p>
                {staffResult.accounts_created} account(s) created, {staffResult.access_granted}{' '}
                staff grant(s) added, {staffResult.already_staff} already staff.
              </p>
              {staffResult.errors.length > 0 && (
                <ul className="text-amber-400 list-disc list-inside mt-1">
                  {staffResult.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {staff.length === 0 ? (
        <p className="text-slate-400">No staff granted for this course yet.</p>
      ) : (
        <div className="space-y-2">
          {staff.map((s) => (
            <Card key={s.id} className="px-6 py-3">
              <p className="font-medium text-slate-100">
                {s.display_name || s.username || s.netid}
              </p>
              <p className="text-slate-500 text-sm">
                {s.username ? `@${s.username}` : s.netid} · {s.email ?? 'no email'}
              </p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

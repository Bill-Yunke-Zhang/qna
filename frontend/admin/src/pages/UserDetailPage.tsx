import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';

interface Course {
  id: number;
  name: string;
  semester: string;
}

interface UserWithAccess {
  id: string;
  username: string | null;
  netid: string | null;
  display_name: string | null;
  email: string | null;
  role: string;
  course_access: { course_id: number; role: string }[];
}

export default function UserDetailPage() {
  const { userId } = useParams();
  const [user, setUser] = useState<UserWithAccess | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourse, setSelectedCourse] = useState('');
  const [selectedRole, setSelectedRole] = useState<'STUDENT' | 'STAFF'>('STUDENT');
  const [error, setError] = useState('');

  async function load() {
    const [u, c] = await Promise.all([
      api.get<UserWithAccess>(`/admin/users/${userId}`),
      api.get<Course[]>('/admin/courses'),
    ]);
    setUser(u);
    setCourses(c);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function grantAccess(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedCourse) return;
    setError('');
    try {
      await api.post(`/admin/users/${userId}/course-access`, {
        course_id: Number(selectedCourse),
        role: selectedRole,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to grant access');
    }
  }

  async function revokeAccess(courseId: number) {
    await api.delete(`/admin/users/${userId}/course-access/${courseId}`);
    await load();
  }

  if (!user) return <p className="p-8 text-slate-400">Loading…</p>;

  const courseName = (id: number) => courses.find((c) => c.id === id)?.name ?? `Course ${id}`;

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-2xl font-bold text-slate-100 mb-1">
        {user.display_name || user.username || user.netid}
      </h2>
      <p className="text-slate-400 text-sm mb-6">
        {user.username ? `@${user.username}` : user.netid} · {user.email ?? 'no email'} ·{' '}
        {user.role}
      </p>

      <Card className="mb-6">
        <CardHeader>
          <h3 className="text-lg font-semibold text-slate-100">Grant Course Access</h3>
        </CardHeader>
        <CardContent>
          <form onSubmit={grantAccess} className="flex gap-3 flex-wrap items-center">
            <select
              value={selectedCourse}
              onChange={(e) => setSelectedCourse(e.target.value)}
              className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 flex-1 min-w-40"
            >
              <option value="">Select a course…</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.semester})
                </option>
              ))}
            </select>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value as 'STUDENT' | 'STAFF')}
              className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100"
            >
              <option value="STUDENT">Student</option>
              <option value="STAFF">Staff</option>
            </select>
            <Button type="submit">Grant</Button>
          </form>
          {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
        </CardContent>
      </Card>

      <h3 className="text-lg font-semibold text-slate-100 mb-3">Course Access</h3>
      {user.course_access.length === 0 ? (
        <p className="text-slate-400">No course access granted yet.</p>
      ) : (
        <div className="space-y-2">
          {user.course_access.map((access) => (
            <Card key={access.course_id} className="flex items-center justify-between px-6 py-3">
              <div>
                <p className="font-medium text-slate-100">{courseName(access.course_id)}</p>
                <p className="text-slate-500 text-sm">{access.role}</p>
              </div>
              <Button variant="outline" size="sm" onClick={() => revokeAccess(access.course_id)}>
                <Trash2 size={14} />
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

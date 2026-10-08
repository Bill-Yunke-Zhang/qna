import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Users, Pencil } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface Course {
  id: number;
  name: string;
  semester: string;
  created_at: string;
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [semester, setSemester] = useState('');
  const [saving, setSaving] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [editName, setEditName] = useState('');
  const [editSemester, setEditSemester] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const navigate = useNavigate();

  async function load() {
    try {
      const data = await api.get<Course[]>('/admin/courses');
      setCourses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load courses');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/admin/courses', { name, semester });
      setName('');
      setSemester('');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create course');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(c: Course) {
    setEditingCourse(c);
    setEditName(c.name);
    setEditSemester(c.semester);
    setShowForm(false);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCourse) return;
    setEditSaving(true);
    setError('');
    try {
      await api.put(`/admin/courses/${editingCourse.id}`, { name: editName, semester: editSemester });
      setEditingCourse(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update course');
    } finally {
      setEditSaving(false);
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-slate-100">Courses</h2>
        <Button onClick={() => { setShowForm(!showForm); setEditingCourse(null); }} size="sm">
          <Plus size={16} className="mr-1" /> New Course
        </Button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {showForm && (
        <Card className="mb-6">
          <CardHeader><h3 className="text-lg font-semibold text-slate-100">Create Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name (e.g. CS 537)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester (e.g. Fall 2026)"
                value={semester}
                onChange={(e) => setSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create'}</Button>
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {editingCourse && (
        <Card className="mb-6">
          <CardHeader><h3 className="text-lg font-semibold text-slate-100">Edit Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleEdit} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester"
                value={editSemester}
                onChange={(e) => setEditSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Button type="submit" disabled={editSaving}>{editSaving ? 'Saving…' : 'Save'}</Button>
              <Button type="button" variant="ghost" onClick={() => setEditingCourse(null)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : courses.length === 0 ? (
        <p className="text-slate-400">No courses yet. Create one above.</p>
      ) : (
        <div className="space-y-3">
          {courses.map((c) => (
            <Card key={c.id} className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="font-semibold text-slate-100">{c.name}</p>
                <p className="text-slate-400 text-sm">{c.semester}</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => startEdit(c)}>
                  <Pencil size={14} />
                </Button>
                <Button variant="outline" size="sm" onClick={() => navigate(`/courses/${c.id}/roster`)}>
                  <Users size={14} className="mr-1" /> Roster
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

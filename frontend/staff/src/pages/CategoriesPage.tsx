import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import type { Category } from '../lib/types';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';

export default function CategoriesPage() {
  const { courseId } = useCourse();
  const [categories, setCategories] = useState<Category[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function load() {
    if (!courseId) return;
    const data = await api.get<Category[]>(`/courses/${courseId}/categories`);
    setCategories(data);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId) return;
    setSaving(true);
    setError('');
    try {
      await api.post(`/courses/${courseId}/categories`, { name, description });
      setName('');
      setDescription('');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create category');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(categoryId: number) {
    if (!courseId) return;
    await api.delete(`/courses/${courseId}/categories/${categoryId}`);
    await load();
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold text-slate-100 mb-6">Categories</h2>

      <Card className="mb-6">
        <CardHeader>
          <h3 className="text-lg font-semibold text-slate-100">New Category</h3>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="space-y-3">
            <Input
              placeholder="Category name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <Textarea
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <Button type="submit" disabled={saving}>
              <span className="flex items-center gap-1.5">
                <Plus size={16} /> {saving ? 'Creating…' : 'Create'}
              </span>
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {categories.map((c) => (
          <Card key={c.id} className="px-6 py-4 flex items-center justify-between">
            <div>
              <p className="font-semibold text-slate-100">{c.name}</p>
              {c.description && <p className="text-slate-400 text-sm">{c.description}</p>}
            </div>
            <Button variant="outline" size="sm" onClick={() => handleDelete(c.id)}>
              <Trash2 size={14} />
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}

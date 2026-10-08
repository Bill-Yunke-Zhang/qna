import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import type { Category, QuestionDetail } from '../lib/types';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Card, CardContent, CardHeader } from '../components/ui/card';

export default function AskQuestionPage() {
  const { courseId } = useCourse();
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!courseId) return;
    api.get<Category[]>(`/courses/${courseId}/categories`).then(setCategories);
  }, [courseId]);

  function toggleCategory(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId) return;
    if (selected.size === 0) {
      setError('Select at least one category.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const question = await api.post<QuestionDetail>(`/courses/${courseId}/questions`, {
        title,
        body,
        category_ids: Array.from(selected),
      });
      navigate(`/questions/${question.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to post question');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <Card>
        <CardHeader>
          <h2 className="text-xl font-bold text-slate-100">Ask a Question</h2>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              placeholder="Question title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
            <Textarea
              placeholder="Describe your question in detail…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              required
            />
            {categories.length > 0 ? (
              <div>
                <p className="text-sm text-slate-400 mb-2">Categories (select at least one)</p>
                <div className="flex flex-wrap gap-2">
                  {categories.map((c) => (
                    <button
                      type="button"
                      key={c.id}
                      onClick={() => toggleCategory(c.id)}
                      className={`rounded-full px-3 py-1 text-sm border transition-colors ${
                        selected.has(c.id)
                          ? 'bg-indigo-600 border-indigo-600 text-white'
                          : 'border-slate-600 text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-amber-400 text-sm">
                This course has no categories yet — ask course staff to add one before you can
                post a question.
              </p>
            )}
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <div className="flex gap-3">
              <Button type="submit" disabled={saving || categories.length === 0}>
                {saving ? 'Posting…' : 'Post Question'}
              </Button>
              <Button type="button" variant="ghost" onClick={() => navigate('/questions')}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

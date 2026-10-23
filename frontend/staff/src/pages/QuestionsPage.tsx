import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, CheckCircle2, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import type { Category, QuestionSummary } from '../lib/types';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';

export default function QuestionsPage() {
  const { courseId } = useCourse();
  const [questions, setQuestions] = useState<QuestionSummary[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [q, setQ] = useState('');
  // AI answers are only checked by staff after posting, so make the
  // unchecked ones easy to find (docs/design-rag.md §4.4).
  const [aiUnverifiedOnly, setAiUnverifiedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!courseId) return;
    api.get<Category[]>(`/courses/${courseId}/categories`).then(setCategories);
  }, [courseId]);

  useEffect(() => {
    if (!courseId) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (categoryId) params.set('category_id', categoryId);
    if (status) params.set('status', status);
    if (q) params.set('q', q);
    api
      .get<QuestionSummary[]>(`/courses/${courseId}/questions?${params.toString()}`)
      .then(setQuestions)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load questions'))
      .finally(() => setLoading(false));
  }, [courseId, categoryId, status, q]);

  const shown = aiUnverifiedOnly
    ? questions.filter((x) => x.has_ai_answer && !x.has_accepted_answer)
    : questions;

  if (!courseId) {
    return <p className="p-8 text-ink-muted">You aren't enrolled in any course yet.</p>;
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-ink">Questions</h2>
        <Link
          to="/questions/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-base font-semibold text-on-accent transition-colors hover:bg-accent-hover"
        >
          <Plus size={16} /> Ask a Question
        </Link>
      </div>

      <div className="flex flex-wrap gap-3 mb-6">
        <div className="relative flex-1 min-w-48">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" />
          <Input
            placeholder="Search questions…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="rounded-lg border border-line-strong bg-surface-raised px-3 py-2 text-ink"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-line-strong bg-surface-raised px-3 py-2 text-ink"
        >
          <option value="">Open + closed</option>
          <option value="OPEN">Open</option>
          <option value="CLOSED">Closed</option>
        </select>
        <select
          value={aiUnverifiedOnly ? 'ai' : ''}
          onChange={(e) => setAiUnverifiedOnly(e.target.value === 'ai')}
          className="rounded-lg border border-line-strong bg-surface-raised px-3 py-2 text-ink"
        >
          <option value="">All answers</option>
          <option value="ai">AI answered, not verified</option>
        </select>
      </div>

      {error && <p className="text-danger-ink mb-4 text-sm">{error}</p>}

      {loading ? (
        <p className="text-ink-muted">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="text-ink-muted">No questions match your filters.</p>
      ) : (
        <div className="space-y-3">
          {shown.map((question) => (
            <Link key={question.id} to={`/questions/${question.id}`}>
              <Card className="px-6 py-4 hover:border-accent transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-ink flex items-center gap-2">
                      {question.title}
                      {question.has_accepted_answer && (
                        <CheckCircle2 size={16} className="text-success-ink" />
                      )}
                    </p>
                    <p className="text-ink-muted text-sm mt-1">
                      {question.author.display_name} · {question.post_count} repl
                      {question.post_count === 1 ? 'y' : 'ies'}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <div className="flex gap-1">
                      {question.has_ai_answer && (
                        <Badge variant="ai">
                          <Sparkles size={12} className="mr-1" /> AI answered
                        </Badge>
                      )}
                      <Badge variant={question.status === 'OPEN' ? 'success' : 'outline'}>
                        {question.status}
                      </Badge>
                    </div>
                    <div className="flex gap-1 flex-wrap justify-end">
                      {question.categories.map((c) => (
                        <Badge key={c.id} variant="default">
                          {c.name}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

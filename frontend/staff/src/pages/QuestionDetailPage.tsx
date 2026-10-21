import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, EyeOff, Lock, LockOpen, ShieldCheck } from 'lucide-react';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import type { QuestionDetail } from '../lib/types';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { AiCitations } from '../components/AiCitations';

export default function QuestionDetailPage() {
  const { courseId } = useCourse();
  const { questionId } = useParams();
  const [question, setQuestion] = useState<QuestionDetail | null>(null);
  const [kind, setKind] = useState<'ANSWER' | 'FOLLOWUP'>('ANSWER');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [posting, setPosting] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!courseId) return;
    const data = await api.get<QuestionDetail>(`/courses/${courseId}/questions/${questionId}`);
    setQuestion(data);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, questionId]);

  async function handlePost(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId) return;
    setPosting(true);
    setError('');
    try {
      const updated = await api.post<QuestionDetail>(
        `/courses/${courseId}/questions/${questionId}/posts`,
        { kind, body }
      );
      setQuestion(updated);
      setBody('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to post');
    } finally {
      setPosting(false);
    }
  }

  async function toggleAccepted(postId: number, next: boolean) {
    if (!courseId) return;
    setBusy(true);
    try {
      const updated = await api.patch<QuestionDetail>(
        `/courses/${courseId}/questions/${questionId}/posts/${postId}/accept`,
        { is_accepted: next }
      );
      setQuestion(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update');
    } finally {
      setBusy(false);
    }
  }

  // Soft-hides a wrong AI answer: students stop seeing it, staff see it
  // collapsed, and it's un-accepted (docs/design-rag.md §4.7).
  async function retract(postId: number) {
    if (!courseId) return;
    if (!window.confirm('Retract this AI answer? Students will no longer see it.')) return;
    setBusy(true);
    try {
      const updated = await api.patch<QuestionDetail>(
        `/courses/${courseId}/questions/${questionId}/posts/${postId}/retract`
      );
      setQuestion(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retract');
    } finally {
      setBusy(false);
    }
  }

  async function toggleThreadOpen() {
    if (!courseId || !question) return;
    setBusy(true);
    try {
      const action = question.status === 'OPEN' ? 'close' : 'reopen';
      const updated = await api.post<QuestionDetail>(
        `/courses/${courseId}/questions/${questionId}/${action}`
      );
      setQuestion(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update thread status');
    } finally {
      setBusy(false);
    }
  }

  if (!question) return <p className="p-8 text-slate-400">Loading…</p>;

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-6">
      <Link
        to="/questions"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-100"
      >
        <ArrowLeft size={16} /> Back to Questions
      </Link>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-xl font-bold text-slate-100">{question.title}</h2>
            <div className="flex items-center gap-2">
              <Badge variant={question.status === 'OPEN' ? 'success' : 'outline'}>
                {question.status}
              </Badge>
              <Button size="sm" variant="outline" disabled={busy} onClick={toggleThreadOpen}>
                {question.status === 'OPEN' ? (
                  <span className="flex items-center gap-1.5">
                    <Lock size={14} /> Close thread
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <LockOpen size={14} /> Reopen
                  </span>
                )}
              </Button>
            </div>
          </div>
          <p className="text-slate-400 text-sm mt-1">Asked by {question.author.display_name}</p>
          <p className="text-slate-200 mt-4 whitespace-pre-wrap">{question.body}</p>
          <div className="flex gap-1.5 mt-4 flex-wrap">
            {question.categories.map((c) => (
              <Badge key={c.id}>{c.name}</Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="space-y-3">
        {question.posts.map((post) =>
          post.retracted_at ? (
            // Not counted as a reply; kept so staff can see what the AI said.
            <details
              key={post.id}
              className="rounded-xl border border-dashed border-slate-700 px-6 py-3 text-sm"
            >
              <summary className="flex cursor-pointer items-center gap-2 text-slate-400">
                <EyeOff size={14} /> AI answer retracted by{' '}
                {post.retracted_by?.display_name ?? 'staff'}
              </summary>
              <p className="mt-3 text-slate-400 whitespace-pre-wrap">{post.body}</p>
              {post.citations && post.citations.length > 0 && (
                <AiCitations citations={post.citations} />
              )}
            </details>
          ) : (
            <Card key={post.id} className={post.is_accepted ? 'border-emerald-500' : ''}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    {post.author && (
                      <span className="font-semibold text-slate-100">
                        {post.author.display_name}
                      </span>
                    )}
                    {post.author_role === 'AI' ? (
                      <Badge variant="ai">AI-generated</Badge>
                    ) : (
                      <Badge variant={post.author_role === 'STAFF' ? 'default' : 'outline'}>
                        {post.author_role === 'STAFF' ? 'Course Staff' : 'Student'}
                      </Badge>
                    )}
                    <Badge variant="outline">
                      {post.kind === 'ANSWER' ? 'Answer' : 'Follow-up'}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    {post.author_role === 'AI' && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => retract(post.id)}
                      >
                        <span className="flex items-center gap-1.5">
                          <EyeOff size={14} /> Retract
                        </span>
                      </Button>
                    )}
                    {post.kind === 'ANSWER' && (
                      <Button
                        size="sm"
                        variant={post.is_accepted ? 'default' : 'outline'}
                        disabled={busy}
                        onClick={() => toggleAccepted(post.id, !post.is_accepted)}
                      >
                        <span className="flex items-center gap-1.5">
                          {post.is_accepted ? <CheckCircle2 size={14} /> : <ShieldCheck size={14} />}
                          {post.is_accepted ? 'Verified' : 'Mark verified'}
                        </span>
                      </Button>
                    )}
                  </div>
                </div>
                <p className="text-slate-200 whitespace-pre-wrap">{post.body}</p>
                {post.citations && post.citations.length > 0 && (
                  <AiCitations citations={post.citations} />
                )}
              </CardContent>
            </Card>
          )
        )}
      </div>

      {question.status === 'OPEN' ? (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handlePost} className="space-y-3">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setKind('ANSWER')}
                  className={`rounded-lg px-3 py-1.5 text-sm border ${
                    kind === 'ANSWER'
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'border-slate-600 text-slate-300'
                  }`}
                >
                  Answer
                </button>
                <button
                  type="button"
                  onClick={() => setKind('FOLLOWUP')}
                  className={`rounded-lg px-3 py-1.5 text-sm border ${
                    kind === 'FOLLOWUP'
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'border-slate-600 text-slate-300'
                  }`}
                >
                  Follow-up
                </button>
              </div>
              <Textarea
                placeholder={kind === 'ANSWER' ? 'Write an answer…' : 'Add a follow-up…'}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={4}
                required
              />
              <Button type="submit" disabled={posting}>
                {posting ? 'Posting…' : 'Post'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <p className="flex items-center gap-2 text-slate-500 text-sm">
          <Lock size={14} /> This thread is closed. Reopen it above to add more posts.
        </p>
      )}
    </div>
  );
}

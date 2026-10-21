import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Loader2, Lock } from 'lucide-react';
import { api } from '../lib/api';
import { useCourse } from '../lib/CourseContext';
import type { QuestionDetail } from '../lib/types';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { AiCitations } from '../components/AiCitations';

// After asking, poll for the AI answer every 5 s for ~3 minutes: twice the
// slowest live answer (docs/design-rag.md §4.5). Never computed from
// created_at, which the browser would misread as local time.
const POLL_INTERVAL_MS = 5000;
const POLL_ATTEMPTS = 36;

export default function QuestionDetailPage() {
  const { courseId } = useCourse();
  const { questionId } = useParams();
  const location = useLocation();
  const justAsked = Boolean((location.state as { justAsked?: boolean } | null)?.justAsked);
  const [question, setQuestion] = useState<QuestionDetail | null>(null);
  const [kind, setKind] = useState<'ANSWER' | 'FOLLOWUP'>('FOLLOWUP');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [posting, setPosting] = useState(false);
  const [polling, setPolling] = useState(false);

  async function load() {
    if (!courseId) return null;
    const data = await api.get<QuestionDetail>(`/courses/${courseId}/questions/${questionId}`);
    setQuestion(data);
    return data;
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, questionId]);

  // Only right after asking (AskQuestionPage passes { justAsked: true });
  // opening the thread later from the list doesn't poll.
  useEffect(() => {
    if (!courseId || !justAsked) return;
    let attempts = 0;
    let stopped = false;
    setPolling(true);
    const timer = window.setInterval(async () => {
      attempts += 1;
      try {
        const data = await load();
        if (stopped) return;
        if (data?.posts.some((p) => p.author_role === 'AI') || attempts >= POLL_ATTEMPTS) {
          stopped = true;
          window.clearInterval(timer);
          setPolling(false);
        }
      } catch {
        // A failed poll is retried on the next tick.
      }
    }, POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, questionId, justAsked]);

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
            <Badge variant={question.status === 'OPEN' ? 'success' : 'outline'}>
              {question.status}
            </Badge>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Asked by {question.author.display_name}
          </p>
          <p className="text-slate-200 mt-4 whitespace-pre-wrap">{question.body}</p>
          <div className="flex gap-1.5 mt-4 flex-wrap">
            {question.categories.map((c) => (
              <Badge key={c.id}>{c.name}</Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {question.posts.map((post) => (
          <Card key={post.id} className={post.is_accepted ? 'border-emerald-500' : ''}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                  {post.author && (
                    <span className="font-semibold text-slate-100">{post.author.display_name}</span>
                  )}
                  {post.author_role === 'AI' ? (
                    <Badge variant="ai">AI-generated</Badge>
                  ) : (
                    <Badge variant={post.author_role === 'STAFF' ? 'default' : 'outline'}>
                      {post.author_role === 'STAFF' ? 'Course Staff' : 'Student'}
                    </Badge>
                  )}
                  <Badge variant="outline">{post.kind === 'ANSWER' ? 'Answer' : 'Follow-up'}</Badge>
                </div>
                {post.is_accepted && (
                  <span className="flex items-center gap-1 text-emerald-400 text-sm">
                    <CheckCircle2 size={16} /> Verified by staff
                  </span>
                )}
              </div>
              <p className="text-slate-200 whitespace-pre-wrap">{post.body}</p>
              {post.citations && post.citations.length > 0 && (
                <AiCitations citations={post.citations} />
              )}
            </CardContent>
          </Card>
        ))}
        {polling && (
          <p className="flex items-center gap-2 text-slate-400 text-sm" role="status">
            <Loader2 size={14} className="animate-spin" />
            If course materials cover this question, an AI answer will appear here shortly.
          </p>
        )}
      </div>

      {question.status === 'OPEN' ? (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handlePost} className="space-y-3">
              <div className="flex gap-2">
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
              </div>
              <Textarea
                placeholder={kind === 'ANSWER' ? 'Write an answer…' : 'Add a follow-up…'}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={4}
                required
              />
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <Button type="submit" disabled={posting}>
                {posting ? 'Posting…' : 'Post'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <p className="flex items-center gap-2 text-slate-500 text-sm">
          <Lock size={14} /> This thread was closed by course staff and no longer accepts new posts.
        </p>
      )}
    </div>
  );
}

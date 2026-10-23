import { Link } from 'react-router-dom';
import { ExternalLink, MessageSquare } from 'lucide-react';
import type { Citation } from '../lib/types';

// The sources an AI answer was given (docs/design-rag.md §3.3). We only know
// they went into the prompt, not which ones the answer used, so the heading
// claims no more than that; the first is tagged "best match".
export function AiCitations({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted mb-2">
        Top sources given to the AI
      </p>
      <ol className="space-y-1.5">
        {citations.map((c) => (
          <li key={c.rank} className="flex items-center gap-2 text-sm">
            <CitationLink citation={c} />
            {c.rank === 1 && (
              <span className="rounded-full bg-ai-soft px-2 py-0.5 text-xs text-ai-ink">
                best match
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function CitationLink({ citation }: { citation: Citation }) {
  const className = 'inline-flex items-center gap-1.5 text-accent-ink hover:text-ink underline';
  if (citation.resource_type === 'historical_qa' && citation.question_id) {
    // Relative to this app, so each app opens its own thread page.
    return (
      <Link to={`/questions/${citation.question_id}`} className={className}>
        <MessageSquare size={14} /> {citation.label}
      </Link>
    );
  }
  const url = citation.citation_url ?? '';
  if (!/^https?:\/\//i.test(url)) {
    return <span className="text-ink-secondary">{citation.label}</span>;
  }
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={className}>
      <ExternalLink size={14} /> {citation.label}
    </a>
  );
}

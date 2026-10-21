export interface MyCourse {
  id: number;
  name: string;
  semester: string;
  role: 'STUDENT' | 'STAFF';
}

export interface Category {
  id: number;
  course_id: number;
  name: string;
  description: string;
  created_at: string;
}

export interface AuthorSummary {
  id: string;
  display_name: string;
}

export interface QuestionSummary {
  id: number;
  course_id: number;
  title: string;
  status: 'OPEN' | 'CLOSED';
  author: AuthorSummary;
  categories: Category[];
  // Retracted AI answers aren't counted.
  post_count: number;
  has_accepted_answer: boolean;
  // A non-retracted AI answer exists.
  has_ai_answer: boolean;
  created_at: string;
  updated_at: string;
}

// A source an AI answer was given (docs/design-rag.md §3.1, §3.3). Historical
// Q&A has no citation_url: link to this app's thread page from question_id.
export interface Citation {
  rank: number;
  label: string;
  resource_type: 'syllabus' | 'schedule' | 'repo_markdown' | 'repo_pdf' | 'historical_qa';
  citation_url?: string;
  question_id?: number;
  similarity_score: number;
}

export interface Post {
  id: number;
  question_id: number;
  // null for AI posts, which have no author user.
  author: AuthorSummary | null;
  author_role: 'STUDENT' | 'STAFF' | 'AI';
  kind: 'ANSWER' | 'FOLLOWUP';
  body: string;
  is_accepted: boolean;
  accepted_by: AuthorSummary | null;
  accepted_at: string | null;
  created_at: string;
  citations: Citation[] | null;
  // Only staff ever receive retracted posts. retracted_by is null if that
  // staff user was deleted.
  retracted_at: string | null;
  retracted_by: AuthorSummary | null;
}

export interface QuestionDetail {
  id: number;
  course_id: number;
  title: string;
  body: string;
  status: 'OPEN' | 'CLOSED';
  author: AuthorSummary;
  categories: Category[];
  posts: Post[];
  closed_by: AuthorSummary | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

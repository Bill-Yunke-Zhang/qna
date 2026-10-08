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
  post_count: number;
  has_accepted_answer: boolean;
  created_at: string;
  updated_at: string;
}

export interface Post {
  id: number;
  question_id: number;
  author: AuthorSummary;
  author_role: 'STUDENT' | 'STAFF';
  kind: 'ANSWER' | 'FOLLOWUP';
  body: string;
  is_accepted: boolean;
  accepted_by: AuthorSummary | null;
  accepted_at: string | null;
  created_at: string;
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

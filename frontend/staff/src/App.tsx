import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom';
import { Library, LogOut, MessageSquare, Tags } from 'lucide-react';
import { CourseProvider, useCourse } from './lib/CourseContext';
import { ThemeToggle } from './components/ThemeToggle';
import LoginPage from './pages/LoginPage';
import QuestionsPage from './pages/QuestionsPage';
import AskQuestionPage from './pages/AskQuestionPage';
import QuestionDetailPage from './pages/QuestionDetailPage';
import CategoriesPage from './pages/CategoriesPage';
import ResourcesPage from './pages/ResourcesPage';

function RequireAuth() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function Layout() {
  const navigate = useNavigate();
  const { courses, courseId, setCourseId, refresh } = useCourse();

  function logout() {
    localStorage.removeItem('token');
    void refresh(); // clears course state so it doesn't leak into the next login
    navigate('/login');
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 text-sm ${isActive ? 'text-accent-ink' : 'text-ink-secondary hover:text-ink'}`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="max-w-3xl mx-auto px-8 py-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <span className="flex items-center gap-2.5 text-ink font-bold">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-soft text-accent-ink">
                <MessageSquare size={18} aria-hidden />
              </span>
              Course Q&amp;A — Staff
            </span>
            <nav className="flex items-center gap-4">
              <NavLink to="/questions" className={linkClass}>
                Questions
              </NavLink>
              <NavLink to="/categories" className={linkClass}>
                <Tags size={14} /> Categories
              </NavLink>
              <NavLink to="/resources" className={linkClass}>
                <Library size={14} /> Resources
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {courses.length > 1 && (
              <label className="flex items-center gap-1.5 text-sm text-ink-muted">
                Course:
                <select
                  value={courseId ?? ''}
                  onChange={(e) => setCourseId(Number(e.target.value))}
                  className="rounded-lg border border-line-strong bg-surface-raised px-2 py-1.5 text-sm text-ink"
                >
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.semester})
                    </option>
                  ))}
                </select>
              </label>
            )}
            <ThemeToggle />
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm text-ink-secondary hover:text-ink"
            >
              <LogOut size={16} /> Logout
            </button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <CourseProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route path="/questions" element={<QuestionsPage />} />
              <Route path="/questions/new" element={<AskQuestionPage />} />
              <Route path="/questions/:questionId" element={<QuestionDetailPage />} />
              <Route path="/categories" element={<CategoriesPage />} />
              <Route path="/resources" element={<ResourcesPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/questions" replace />} />
        </Routes>
      </CourseProvider>
    </BrowserRouter>
  );
}

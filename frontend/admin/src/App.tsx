import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, NavLink } from 'react-router-dom';
import { BookOpen, Users, LogOut, Shield } from 'lucide-react';
import { ThemeToggle } from './components/ThemeToggle';
import LoginPage from './pages/LoginPage';
import CoursesPage from './pages/CoursesPage';
import RosterPage from './pages/RosterPage';
import UsersPage from './pages/UsersPage';
import UserDetailPage from './pages/UserDetailPage';

function RequireAdmin() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function AdminLayout() {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
      isActive ? 'bg-accent text-on-accent' : 'text-ink-secondary hover:bg-surface-hover hover:text-ink'
    }`;

  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 bg-surface border-r border-line flex flex-col">
        <div className="px-6 py-5 border-b border-line">
          <h1 className="flex items-center gap-2.5 text-lg font-bold text-ink">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-soft text-accent-ink">
              <Shield size={18} aria-hidden />
            </span>
            QnA Admin
          </h1>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/courses" className={linkClass}>
            <BookOpen size={16} /> Courses
          </NavLink>
          <NavLink to="/users" className={linkClass}>
            <Users size={16} /> Users
          </NavLink>
        </nav>
        <div className="p-3 border-t border-line flex items-center gap-2">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink flex-1 transition-colors"
          >
            <LogOut size={16} /> Logout
          </button>
          <ThemeToggle />
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/courses/:courseId/roster" element={<RosterPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:userId" element={<UserDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/courses" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

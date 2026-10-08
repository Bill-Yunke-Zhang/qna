import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from './api';
import type { MyCourse } from './types';

interface CourseContextValue {
  courses: MyCourse[];
  courseId: number | null;
  setCourseId: (id: number) => void;
  loading: boolean;
  /** Re-fetch course membership — call this right after login/logout, since
   *  CourseProvider stays mounted across the /login <-> /questions
   *  navigation and won't otherwise notice the token changed. */
  refresh: () => Promise<void>;
}

const CourseContext = createContext<CourseContextValue | null>(null);

export function CourseProvider({ children }: { children: ReactNode }) {
  const [courses, setCourses] = useState<MyCourse[]>([]);
  const [courseId, setCourseIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem('course_id');
    return stored ? Number(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  async function refresh() {
    if (!localStorage.getItem('token')) {
      setCourses([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await api.get<MyCourse[]>('/courses/mine');
      setCourses(data);
      setCourseIdState((current) => {
        if (current && data.some((c) => c.id === current)) return current;
        return data[0]?.id ?? null;
      });
    } catch {
      // Token invalid/expired — RequireAuth redirects once the request fails.
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setCourseId(id: number) {
    setCourseIdState(id);
    localStorage.setItem('course_id', String(id));
  }

  return (
    <CourseContext.Provider value={{ courses, courseId, setCourseId, loading, refresh }}>
      {children}
    </CourseContext.Provider>
  );
}

export function useCourse() {
  const ctx = useContext(CourseContext);
  if (!ctx) throw new Error('useCourse must be used within a CourseProvider');
  return ctx;
}

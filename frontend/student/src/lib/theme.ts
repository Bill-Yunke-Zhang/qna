import { useEffect, useState } from 'react';

// Light/dark theme (T8). The theme is `data-theme` on <html>; the colors are
// the tokens in index.css. index.html applies the starting theme before the
// first paint; this module keeps it in sync after that. The key is shared
// by the three apps, which run on one origin in production.
export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'qna-theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null; // storage blocked: follow the OS
  }
}

function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

function apply(theme: Theme) {
  const root = document.documentElement;
  if (root.dataset.theme === theme) return;
  // Switch every color at once: with transitions on, elements would
  // animate from the old theme (and stall there in a background tab).
  root.classList.add('theme-switching');
  root.dataset.theme = theme;
  // Reading layout makes the browser apply the new colors now, while
  // transitions are off; only then are they turned back on.
  void document.body.offsetHeight;
  root.classList.remove('theme-switching');
}

/**
 * The current theme and a setter that saves the choice. Until the user picks
 * one, it follows the OS preference, including changes while the page is open.
 */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(() => savedTheme() ?? systemTheme());

  useEffect(() => {
    apply(theme);
  }, [theme]);

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const follow = () => {
      if (!savedTheme()) setThemeState(systemTheme());
    };
    media.addEventListener('change', follow);
    return () => media.removeEventListener('change', follow);
  }, []);

  function setTheme(next: Theme) {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not saved; it still applies for this page
    }
    setThemeState(next);
  }

  return [theme, setTheme];
}

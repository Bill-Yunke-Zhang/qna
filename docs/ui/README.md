# UI theming (T8)

All three apps (student, staff, admin) share one theme system: semantic
color tokens with a light and a dark theme, and a toggle in every app.

## How it works

- **Tokens.** Each app's `src/index.css` defines the tokens as CSS variables
  (`R G B` values) for `:root[data-theme='light']` and
  `:root[data-theme='dark']`. `tailwind.config.ts` **replaces** Tailwind's
  color palette with these tokens instead of extending it, so a raw utility
  like `bg-slate-800` doesn't exist in the build and can't creep back in.
  No hex or palette color appears anywhere else in the frontends.
- **Toggle.** A sun/moon button (`components/ThemeToggle.tsx`) in each app's
  header (the sidebar in admin) and on every login page. Its label names the
  theme it switches to.
- **Default and persistence.** On the first visit the theme follows the OS
  (`prefers-color-scheme`), and keeps following it while the user hasn't
  chosen. A choice is saved in `localStorage` (`qna-theme`, shared by the
  three apps, which run on one origin in production). A small script in each
  `index.html` applies the theme before the first paint, so there's no flash
  of the other theme on reload.
- **Switching.** `lib/theme.ts` turns transitions off for the instant the
  theme changes, so every color switches at once instead of animating from
  the old theme.

## Tokens

| Token | Used for |
|---|---|
| `canvas` | Page background |
| `surface`, `surface-raised`, `surface-hover` | Cards, header and sidebar; form fields; hover and selected states |
| `line`, `line-strong` | Dividers and card borders; form-control and outline-button borders |
| `ink`, `ink-secondary`, `ink-muted`, `ink-subtle` | Text, from primary to least prominent |
| `accent`, `accent-hover`, `on-accent` | Primary buttons and the active nav item, and the text on them |
| `accent-soft`, `accent-ink` | Tinted badges and the brand mark; links |
| `danger`, `success`, `warning` (`-soft`, `-ink`) | Destructive buttons and errors; open/verified states; truncation and version warnings |
| `ai-soft`, `ai-ink` | The "AI-generated" badge and "best match" tag |
| `focus` | The focus ring and the global `:focus-visible` outline |

## Accessibility

- Every text/background pair the tokens are used in meets WCAG 2.1 AA
  (4.5:1) in both themes, and control borders and the focus ring meet the
  3:1 non-text minimum. The palette was checked with a contrast script
  before use (lowest text pair 4.77:1 light, 4.63:1 dark).
- An in-page audit then measured every visible text element against its
  actual background on every page of the three apps, in both themes
  (student: questions, ask, thread, login; staff: questions, ask, thread,
  categories, resources, login; admin: courses, roster, users, user detail,
  login). No element was below 4.5:1; the lowest was 5.32:1.
- Everything focusable gets a 2px `focus` outline on keyboard focus
  (`:focus-visible`), in addition to the buttons' own focus rings.

### Independent check (2026-10-23, ygoel3)

A second pass with different tools, on 12 pages × 2 themes (student:
login, questions, thread, ask; staff: login, questions, thread with an AI
answer and a retracted one expanded, resources, categories; admin: login,
courses, users), with the API answered by fixtures:

- **axe-core 4.10** (WCAG 2.1 A + AA rules) on each page: no
  `color-contrast` violations in either theme. The token pairs were also
  recomputed independently and agree with the numbers above.
- **Keyboard:** Tab through each page; every focused element showed a
  visible outline or ring. Every `focus:outline-none` in the three apps has
  a `focus:ring` replacing it.
- **Names (fixed in this change, not theme regressions; they predate T8):**
  axe flagged 7 filter/form `<select>`s with no accessible name and 3
  icon-only buttons (edit course, revoke access, delete category). Each now
  has an `aria-label`. After the fix: 24/24 page-theme combinations pass.
- **Noted, not a failure:** in dark mode, `line-strong` against
  `surface-hover` is 2.91:1. It only meets when an outline button is
  hovered, where the comparison that WCAG 1.4.11 asks for (the border
  against the page around the control) still passes.

## Screenshots

`before/` is the starter UI (dark only), taken on 2026-10-23 before any
theming change. `after/` is the same screens in both themes.

| Screen | Before | After (light) | After (dark) |
|---|---|---|---|
| Student: question list | [before](before/student-questions.jpg) | [light](after/student-questions-light.jpg) | [dark](after/student-questions-dark.jpg) |
| Student: thread with an AI answer and citations | [before](before/student-thread-ai-answer.jpg) | [light](after/student-thread-ai-answer-light.jpg) | [dark](after/student-thread-ai-answer-dark.jpg) |
| Staff: thread with Retract / Mark verified | [before](before/staff-thread-ai-answer.jpg) | [light](after/staff-thread-ai-answer-light.jpg) | [dark](after/staff-thread-ai-answer-dark.jpg) |
| Staff: Resources page (T4) | [before](before/staff-resources.jpg) | [light](after/staff-resources-light.jpg) | [dark](after/staff-resources-dark.jpg) |
| Staff: login | [before](before/staff-login.jpg) | [light](after/staff-login-light.jpg) | [dark](after/staff-login-dark.jpg) |
| Admin: courses | [before](before/admin-courses.jpg) | [light](after/admin-courses-light.jpg) | [dark](after/admin-courses-dark.jpg) |
| Admin: users | [before](before/admin-users.jpg) | [light](after/admin-users-light.jpg) | [dark](after/admin-users-dark.jpg) |

The screenshots use local development data (the `demo`, `devstaff` and
`devadmin` accounts and a hand-made AI answer), not production data.

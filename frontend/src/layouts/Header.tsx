import { Moon, Sun } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

export default function Header() {
  const { isAuthenticated } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const isLight = theme === 'light'

  return (
    <header className="flex min-h-20 items-center justify-between gap-4 border-b border-border bg-background px-8 py-4">
      <div>
        <h2 className="text-xl font-semibold text-white">TenderAI</h2>
        <p className="mt-1 text-xs text-muted">
          {isAuthenticated
            ? 'Your private procurement workspace.'
            : 'Public preview · Private data stays hidden until sign-in.'}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
          aria-pressed={isLight}
          title={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-surface text-muted transition hover:bg-surface-hover hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {isLight ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        <span className="rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-xs font-medium text-success">
          {isAuthenticated ? 'Authenticated workspace' : 'Public preview'}
        </span>
      </div>
    </header>
  )
}

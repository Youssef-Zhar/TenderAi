import { Menu, Moon, Sun } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useTheme } from '../context/ThemeContext'

interface HeaderProps {
  onMenuClick: () => void
  isMenuOpen: boolean
}

const pageContent: Record<string, { title: string; description: string }> = {
  '/dashboard': {
    title: 'Dashboard',
    description: 'Your procurement overview, updated from the TenderAI API.',
  },
  '/tenders': {
    title: 'Tenders',
    description: 'Browse and manage your procurement opportunities.',
  },
  '/analysis': {
    title: 'AI Analysis',
    description: 'Review AI-powered tender analysis and extracted insights.',
  },
}

export default function Header({ onMenuClick, isMenuOpen }: HeaderProps) {
  const { theme, toggleTheme } = useTheme()
  const { pathname } = useLocation()
  const currentPage = pageContent[pathname] ?? pageContent['/dashboard']

  return (
    <header className="flex min-h-20 shrink-0 items-center justify-between gap-3 border-b border-border bg-background px-4 py-4 sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          aria-controls="dashboard-sidebar"
          aria-expanded={isMenuOpen}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-surface text-muted transition hover:border-primary/50 hover:bg-surface-hover hover:text-primary lg:hidden"
        >
          <Menu size={19} />
        </button>

        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold text-white sm:text-xl">
            {currentPage.title}
          </h2>
          <p className="mt-1 hidden truncate text-xs text-muted sm:block">
            {currentPage.description}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        <span className="hidden rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-xs font-medium text-success xl:inline-flex">
          API-connected workspace
        </span>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface text-muted transition hover:border-primary/50 hover:bg-surface-hover hover:text-primary"
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
    </header>
  )
}

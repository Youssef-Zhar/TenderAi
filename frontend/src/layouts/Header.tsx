
import { Bell, Search, ChevronDown } from 'lucide-react'

export default function Header() {
  return (
    <header className="flex h-20 items-center justify-between border-b border-border bg-background px-8">
      {/* Page title */}
      <div>
        <h2 className="text-xl font-semibold text-white">
          Dashboard
        </h2>
        <p className="mt-1 text-xs text-muted">
          Welcome back! Here's your procurement overview.
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-5">
        {/* Search */}
        <div className="flex w-64 items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2.5">
          <Search size={17} className="text-muted" />

          <input
            type="search"
            placeholder="Search anything..."
            className="w-full bg-transparent text-sm text-white outline-none placeholder:text-muted"
          />
        </div>

        {/* Notifications */}
        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-lg p-2.5 text-muted transition hover:bg-surface-hover hover:text-white"
        >
          <Bell size={20} />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-danger" />
        </button>

        {/* Profile */}
        <button
          type="button"
          className="flex items-center gap-2 border-l border-border pl-5"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 text-sm font-bold text-primary">
            YZ
          </div>

          <ChevronDown size={16} className="text-muted" />
        </button>
      </div>
    </header>
  )
}

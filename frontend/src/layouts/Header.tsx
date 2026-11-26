import { useAuth } from '../context/AuthContext'

export default function Header() {
  const { isAuthenticated } = useAuth()

  return (
    <header className="flex min-h-20 items-center justify-between border-b border-border bg-background px-8 py-4">
      <div>
        <h2 className="text-xl font-semibold text-white">TenderAI</h2>
        <p className="mt-1 text-xs text-muted">
          {isAuthenticated
            ? 'Your private procurement workspace.'
            : 'Public preview · Private data stays hidden until sign-in.'}
        </p>
      </div>
      <span className="rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-xs font-medium text-success">
        {isAuthenticated ? 'Authenticated workspace' : 'Public preview'}
      </span>
    </header>
  )
}

export default function Header() {
  return (
    <header className="flex min-h-20 items-center justify-between border-b border-border bg-background px-8 py-4">
      <div>
        <h2 className="text-xl font-semibold text-white">Dashboard</h2>
        <p className="mt-1 text-xs text-muted">
          Your procurement overview, updated from the TenderAI API.
        </p>
      </div>
      <span className="rounded-full border border-success/30 bg-success/10 px-3 py-1.5 text-xs font-medium text-success">
        API-connected workspace
      </span>
    </header>
  )
}

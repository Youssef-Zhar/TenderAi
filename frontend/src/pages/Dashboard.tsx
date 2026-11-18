import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  CalendarClock,
  FileText,
  RefreshCw,
  Wallet,
} from 'lucide-react'
import { getApiErrorMessage } from '../lib/api'
import { tenderService, type Tender } from '../services/tenders'

function formatBudget(value: number | null): string {
  if (value === null) return 'Not specified'

  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDate(value: string | null): string {
  if (!value) return 'Not specified'

  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

export default function Dashboard() {
  const [tenders, setTenders] = useState<Tender[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchTenders = useCallback(async () => {
    try {
      const records = await tenderService.list(0, 20)
      setTenders(records)
      setError('')
    } catch (loadError) {
      setError(getApiErrorMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const loadTenders = useCallback(async () => {
    setIsLoading(true)
    await fetchTenders()
  }, [fetchTenders])

  useEffect(() => {
    // This effect starts an external request; state updates happen when it settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTenders()
  }, [fetchTenders])

  const summary = useMemo(() => {
    const knownBudgets = tenders
      .map((tender) => tender.estimated_budget)
      .filter((budget): budget is number => budget !== null)

    const totalBudget = knownBudgets.reduce((total, budget) => total + budget, 0)
    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const upcoming = tenders
      .filter((tender) => {
        if (!tender.deadline) return false
        const deadline = new Date(`${tender.deadline}T00:00:00`)
        return !Number.isNaN(deadline.getTime()) && deadline >= today
      })
      .sort((a, b) => (a.deadline || '').localeCompare(b.deadline || ''))

    return {
      totalBudget,
      budgetCount: knownBudgets.length,
      upcoming,
    }
  }, [tenders])

  const stats = [
    {
      label: 'My Tenders',
      value: String(tenders.length),
      description: 'Records returned by the API',
      icon: FileText,
      color: 'text-primary',
      bg: 'bg-primary/10',
    },
    {
      label: 'Estimated Budget',
      value: formatBudget(summary.totalBudget),
      description: `${summary.budgetCount} records with a budget`,
      icon: Wallet,
      color: 'text-amber-400',
      bg: 'bg-amber-400/10',
    },
    {
      label: 'Upcoming Deadlines',
      value: String(summary.upcoming.length),
      description: 'Based on saved tender deadlines',
      icon: CalendarClock,
      color: 'text-success',
      bg: 'bg-success/10',
    },
  ]

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Overview</h1>
          <p className="mt-2 text-sm text-muted">
            Live procurement records from your TenderAI account.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadTenders()}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-surface-hover disabled:opacity-50"
        >
          <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-red-300">
          <p className="font-semibold">Could not load your tenders</p>
          <p className="mt-1">{error}</p>
          <p className="mt-2 text-xs text-red-200/80">
            Confirm the backend is running and VITE_API_BASE_URL points to it.
          </p>
        </div>
      )}

      <section className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {stats.map((stat) => {
          const Icon = stat.icon

          return (
            <div
              key={stat.label}
              className="rounded-xl border border-border bg-surface p-5 transition hover:border-primary/40"
            >
              <div className="flex items-center justify-between">
                <div className={`rounded-lg p-3 ${stat.bg}`}>
                  <Icon size={21} className={stat.color} />
                </div>
                <Activity size={17} className="text-muted" />
              </div>

              <p className="mt-5 text-sm text-muted">{stat.label}</p>
              <h2 className="mt-1 break-words text-2xl font-bold text-white">
                {isLoading ? '—' : stat.value}
              </h2>
              <p className="mt-2 text-xs text-muted">{stat.description}</p>
            </div>
          )
        })}
      </section>

      <section className="overflow-hidden rounded-xl border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <div>
            <h2 className="font-semibold text-white">Your Recent Tenders</h2>
            <p className="mt-1 text-xs text-muted">
              Latest records belonging to your account
            </p>
          </div>
          <span className="text-xs text-muted">Up to 20 records</span>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-sm text-muted">Loading tenders...</div>
        ) : tenders.length === 0 && !error ? (
          <div className="p-10 text-center">
            <FileText size={30} className="mx-auto text-muted" />
            <h3 className="mt-3 font-semibold text-white">No tenders yet</h3>
            <p className="mt-2 text-sm text-muted">
              Your saved tenders will appear here after you create one or analyse a PDF.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-background/50 text-xs text-muted">
                <tr>
                  <th className="px-6 py-4 font-medium">Tender</th>
                  <th className="px-6 py-4 font-medium">Estimated budget</th>
                  <th className="px-6 py-4 font-medium">Deadline</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tenders.map((tender) => (
                  <tr key={tender.id} className="transition hover:bg-surface-hover/50">
                    <td className="max-w-lg px-6 py-4">
                      <p className="text-sm font-medium text-white">{tender.title}</p>
                      <p className="mt-1 line-clamp-2 text-xs text-muted">
                        #{tender.id} · {tender.description}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-white">
                      {formatBudget(tender.estimated_budget)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-muted">
                      {formatDate(tender.deadline)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {summary.upcoming[0] && (
        <section className="rounded-xl border border-border bg-surface p-6">
          <div className="flex items-center gap-2">
            <CalendarClock size={18} className="text-amber-400" />
            <h2 className="font-semibold text-white">Next deadline</h2>
          </div>
          <p className="mt-4 text-sm text-muted">{summary.upcoming[0].title}</p>
          <p className="mt-2 text-xl font-bold text-white">
            {formatDate(summary.upcoming[0].deadline)}
          </p>
        </section>
      )}
    </div>
  )
}

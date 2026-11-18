
import {
  FileText,
  Activity,
  BrainCircuit,
  Wallet,
  ArrowUpRight,
  Plus,
  Upload,
  Search,
  Clock,
} from 'lucide-react'

const stats = [
  {
    label: 'Total Tenders',
    value: '248',
    change: '+12.5%',
    icon: FileText,
    color: 'text-primary',
    bg: 'bg-primary/10',
  },
  {
    label: 'Active Tenders',
    value: '36',
    change: '+8.2%',
    icon: Activity,
    color: 'text-success',
    bg: 'bg-success/10',
  },
  {
    label: 'Analyzed Tenders',
    value: '184',
    change: '+18.4%',
    icon: BrainCircuit,
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
  },
  {
    label: 'Total Budget',
    value: '12.8M MAD',
    change: '+5.7%',
    icon: Wallet,
    color: 'text-amber-400',
    bg: 'bg-amber-400/10',
  },
]

const recentTenders = [
  {
    id: 'AO-2026-001',
    title: 'Digital Transformation Platform',
    organization: 'Ministry of Digital Transition',
    status: 'Active',
    budget: '850,000 MAD',
    deadline: 'Nov 25, 2026',
  },
  {
    id: 'AO-2026-002',
    title: 'IT Infrastructure Modernization',
    organization: 'Regional Council',
    status: 'Under Review',
    budget: '1,200,000 MAD',
    deadline: 'Nov 28, 2026',
  },
  {
    id: 'AO-2026-003',
    title: 'Enterprise Management System',
    organization: 'Public Administration',
    status: 'Analyzed',
    budget: '640,000 MAD',
    deadline: 'Dec 02, 2026',
  },
]

export default function Dashboard() {
  return (
    <div className="space-y-8">
      {/* Page introduction */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Overview
          </h1>
          <p className="mt-2 text-sm text-muted">
            Track your procurement activity and tender performance.
          </p>
        </div>

        <button className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-primary-hover">
          <Plus size={18} />
          New Tender
        </button>
      </div>

      {/* Statistics */}
      <section className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
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

                <span className="flex items-center gap-1 text-xs font-semibold text-success">
                  <ArrowUpRight size={15} />
                  {stat.change}
                </span>
              </div>

              <p className="mt-5 text-sm text-muted">{stat.label}</p>
              <h2 className="mt-1 text-2xl font-bold text-white">
                {stat.value}
              </h2>
            </div>
          )
        })}
      </section>

      {/* Main content */}
      <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Recent tenders */}
        <div className="overflow-hidden rounded-xl border border-border bg-surface xl:col-span-2">
          <div className="flex items-center justify-between border-b border-border px-6 py-5">
            <div>
              <h2 className="font-semibold text-white">Recent Tenders</h2>
              <p className="mt-1 text-xs text-muted">
                Your latest procurement opportunities
              </p>
            </div>

            <button className="text-sm font-medium text-primary hover:text-primary-hover">
              View all
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-background/50 text-xs text-muted">
                <tr>
                  <th className="px-6 py-4 font-medium">Tender</th>
                  <th className="px-6 py-4 font-medium">Status</th>
                  <th className="px-6 py-4 font-medium">Budget</th>
                  <th className="px-6 py-4 font-medium">Deadline</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border">
                {recentTenders.map((tender) => (
                  <tr key={tender.id} className="transition hover:bg-surface-hover/50">
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-white">
                        {tender.title}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {tender.id} | {tender.organization}
                      </p>
                    </td>

                    <td className="px-6 py-4">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          tender.status === 'Active'
                            ? 'bg-success/10 text-success'
                            : tender.status === 'Analyzed'
                              ? 'bg-primary/10 text-primary'
                              : 'bg-amber-400/10 text-amber-400'
                        }`}
                      >
                        {tender.status}
                      </span>
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-sm text-white">
                      {tender.budget}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-sm text-muted">
                      {tender.deadline}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick actions */}
        <div className="space-y-6">
          <div className="rounded-xl border border-border bg-surface p-6">
            <h2 className="font-semibold text-white">Quick Actions</h2>
            <p className="mt-1 text-xs text-muted">
              Get started with TenderAI
            </p>

            <div className="mt-5 space-y-3">
              <button className="flex w-full items-center gap-3 rounded-lg border border-border p-4 text-left transition hover:border-primary/50 hover:bg-surface-hover">
                <div className="rounded-lg bg-primary/10 p-2.5">
                  <Upload size={19} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Analyze PDF</p>
                  <p className="mt-1 text-xs text-muted">Extract tender requirements</p>
                </div>
              </button>

              <button className="flex w-full items-center gap-3 rounded-lg border border-border p-4 text-left transition hover:border-primary/50 hover:bg-surface-hover">
                <div className="rounded-lg bg-success/10 p-2.5">
                  <Plus size={19} className="text-success" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Create Tender</p>
                  <p className="mt-1 text-xs text-muted">Add a new opportunity</p>
                </div>
              </button>

              <button className="flex w-full items-center gap-3 rounded-lg border border-border p-4 text-left transition hover:border-primary/50 hover:bg-surface-hover">
                <div className="rounded-lg bg-blue-400/10 p-2.5">
                  <Search size={19} className="text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Browse Tenders</p>
                  <p className="mt-1 text-xs text-muted">Explore all opportunities</p>
                </div>
              </button>
            </div>
          </div>

          {/* Upcoming deadline */}
          <div className="rounded-xl border border-border bg-surface p-6">
            <div className="flex items-center gap-2">
              <Clock size={18} className="text-amber-400" />
              <h2 className="font-semibold text-white">Upcoming Deadline</h2>
            </div>

            <p className="mt-4 text-sm text-muted">
              Digital Transformation Platform
            </p>

            <p className="mt-2 text-xl font-bold text-white">
              November 25, 2026
            </p>

            <p className="mt-2 text-xs text-amber-400">
              Tender deadline approaching
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

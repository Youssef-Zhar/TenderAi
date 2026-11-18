
import {
  LayoutDashboard,
  FileText,
  BrainCircuit,
  ChartNoAxesCombined,
  Settings,
  ChevronLeft,
  ShieldCheck,
} from 'lucide-react'

const navigation = [
  {
    title: 'WORKSPACE',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
      { label: 'Tenders', icon: FileText, href: '/tenders' },
      { label: 'AI Analysis', icon: BrainCircuit, href: '/analysis' },
      { label: 'Reports', icon: ChartNoAxesCombined, href: '/reports' },
    ],
  },
]

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-surface">
      {/* Brand */}
      <div className="flex h-20 items-center justify-between border-b border-border px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary">
            <ShieldCheck size={23} className="text-white" />
          </div>

          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">
              Tender<span className="text-primary">AI</span>
            </h1>
            <p className="text-xs text-muted">Intelligent Procurement</p>
          </div>
        </div>

        <button
          type="button"
          aria-label="Collapse sidebar"
          className="rounded-lg p-2 text-muted transition hover:bg-surface-hover hover:text-white"
        >
          <ChevronLeft size={18} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-8 px-4 py-7">
        {navigation.map((group) => (
          <div key={group.title}>
            <p className="mb-4 px-3 text-[10px] font-bold tracking-[0.15em] text-muted">
              {group.title}
            </p>

            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon

                return (
                  <a
                    key={item.label}
                    href={item.href}
                    className={`group flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition ${
                      item.label === 'Dashboard'
                        ? 'bg-primary/15 text-primary'
                        : 'text-muted hover:bg-surface-hover hover:text-white'
                    }`}
                  >
                    <Icon size={19} />
                    <span>{item.label}</span>

                    {item.label === 'Dashboard' && (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                    )}
                  </a>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Settings */}
      <div className="border-t border-border p-4">
        <a
          href="/settings"
          className="flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-white"
        >
          <Settings size={19} />
          Settings
        </a>
      </div>

      {/* User profile */}
      <div className="border-t border-border p-4">
        <div className="flex items-center gap-3 rounded-lg p-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20 text-sm font-bold text-primary">
            YZ
          </div>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              Workspace User
            </p>
            <p className="text-xs text-muted">Free Plan</p>
          </div>

          <Settings size={17} className="text-muted" />
        </div>
      </div>
    </aside>
  )
}

import {
  BrainCircuit,
  FileText,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
} from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const navigation = [
  { label: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
  { label: 'Tenders', icon: FileText, href: '/tenders' },
  { label: 'AI Analysis', icon: BrainCircuit, href: '/analysis' },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-20 items-center gap-3 border-b border-border px-6">
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

      <nav className="flex-1 space-y-2 px-4 py-7">
        <p className="mb-4 px-3 text-[10px] font-bold tracking-[0.15em] text-muted">
          WORKSPACE
        </p>
        {navigation.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.href}
              to={item.href}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition ${
                  isActive
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted hover:bg-surface-hover hover:text-white'
                }`
              }
            >
              <Icon size={19} />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="border-t border-border p-4">
        <div className="mb-3 flex items-center gap-3 rounded-lg p-2">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/20 text-sm font-bold uppercase text-primary">
            {user?.email.slice(0, 2) || 'TA'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">
              {user?.email || 'TenderAI user'}
            </p>
            <p className="text-xs text-muted">Authenticated account</p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium text-muted transition hover:bg-surface-hover hover:text-white"
        >
          <LogOut size={18} />
          Sign out
        </button>
      </div>
    </aside>
  )
}

import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, FileText, ClipboardList,
  ScrollText, Activity, LogOut, Flower2, Paperclip, UserCheck, Users as UsersIcon, Briefcase
} from 'lucide-react'
import { clearToken } from '../api/client'
import clsx from 'clsx'

const nav = [
  { to: '/krsna/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/krsna/sessions', icon: MessageSquare, label: 'Sessions' },
  { to: '/krsna/enquiries', icon: ClipboardList, label: 'Enquiries' },
  { to: '/krsna/presales', icon: UserCheck, label: 'Pre-sales' },
  { to: '/krsna/users', icon: UsersIcon, label: 'Users' },
  { to: '/krsna/vendor-leads', icon: Briefcase, label: 'Vendor Leads' },
  { to: '/krsna/summaries', icon: FileText, label: 'Summaries' },
  { to: '/krsna/logs', icon: ScrollText, label: 'Logs' },
  { to: '/krsna/files', icon: Paperclip, label: 'Files' },
  { to: '/krsna/system', icon: Activity, label: 'System Health' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()

  const handleLogout = () => {
    clearToken()
    navigate('/krsna')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 bg-navy-800 border-r border-slate-700/50 flex flex-col flex-shrink-0">
        {/* Brand */}
        <div className="px-5 py-5 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600/20 rounded-lg flex items-center justify-center">
              <Flower2 className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-200">Aadhya</p>
              <p className="text-xs text-slate-500">Krsna Admin Panel</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx('nav-item', isActive && 'active')
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-3 py-4 border-t border-slate-700/50">
          <span className="text-xs text-slate-500 px-3">TatvaOps · v1.0</span>
          <button onClick={handleLogout} className="nav-item w-full mt-2">
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-navy-900">
        {children}
      </main>
    </div>
  )
}

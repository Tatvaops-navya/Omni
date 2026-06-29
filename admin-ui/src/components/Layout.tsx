import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, ClipboardList,
  ScrollText, Activity, LogOut, Flower2, UserCheck, Users as UsersIcon,
  Briefcase, UserCircle,
} from 'lucide-react'
import { clearToken, getUser, isAdminUser, isPresalesUser, isRmUser } from '../api/client'
import clsx from 'clsx'

const adminNav = [
  { to: '/krsna/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/krsna/sessions', icon: MessageSquare, label: 'Sessions' },
  { to: '/krsna/enquiries', icon: ClipboardList, label: 'Enquiries' },
  { to: '/krsna/presales', icon: UserCheck, label: 'Pre-sales' },
  { to: '/krsna/users', icon: UsersIcon, label: 'Users' },
  { to: '/krsna/vendor-leads', icon: Briefcase, label: 'Vendor Leads' },
  { to: '/krsna/logs', icon: ScrollText, label: 'Logs' },
  { to: '/krsna/system', icon: Activity, label: 'System Health' },
]

const presalesNav = [
  { to: '/krsna/enquiries', icon: ClipboardList, label: 'Enquiries' },
  { to: '/krsna/my-leads', icon: UserCircle, label: 'My Leads' },
]

const rmNav = [
  { to: '/krsna/enquiries', icon: ClipboardList, label: 'Enquiries' },
  { to: '/krsna/my-leads', icon: UserCircle, label: 'My Leads' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const user = getUser()
  const nav = isPresalesUser() && !isAdminUser()
    ? presalesNav
    : isRmUser() && !isAdminUser()
      ? rmNav
      : adminNav

  const handleLogout = () => {
    clearToken()
    navigate('/krsna')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-60 bg-navy-800 border-r border-slate-700/50 flex flex-col flex-shrink-0">
        <div className="px-5 py-5 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600/20 rounded-lg flex items-center justify-center">
              <Flower2 className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-200">Aadhya</p>
              <p className="text-xs text-slate-500">Krsna Admin Panel</p>
              {user?.name && (
                <p className="text-[10px] text-indigo-400 mt-0.5 truncate">{user.name}</p>
              )}
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => clsx('nav-item', isActive && 'active')}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-slate-700/50">
          <span className="text-xs text-slate-500 px-3">TatvaOps ┬╖ v1.0</span>
          <button onClick={handleLogout} className="nav-item w-full mt-2">
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-navy-900">{children}</main>
    </div>
  )
}

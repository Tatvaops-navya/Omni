import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Activity, LogOut, Flower2, UserCheck, Users as UsersIcon,
  Briefcase, UserCircle, FolderKanban, BadgeCheck, Percent, Megaphone,
} from 'lucide-react'
import {
  clearToken,
  getUser,
  isAdminUser,
  isCampaignOwnerUser,
  isPresalesUser,
  isRmUser,
} from '../api/client'
import clsx from 'clsx'
import ThemeToggle from './ThemeToggle'

const adminNav = [
  { to: '/krsna/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/krsna/presales', icon: UserCheck, label: 'Pre-sales' },
  { to: '/krsna/users', icon: UsersIcon, label: 'Users' },
  { to: '/krsna/vendor-leads', icon: Briefcase, label: 'Vendor Leads' },
  { to: '/krsna/vendors', icon: BadgeCheck, label: 'Vendors' },
  { to: '/krsna/incentive-management', icon: Percent, label: 'Incentive management' },
  { to: '/krsna/system', icon: Activity, label: 'System Health' },
]

const presalesNav = [
  { to: '/krsna/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/krsna/my-leads', icon: UserCircle, label: 'My Leads' },
  { to: '/krsna/my-projects', icon: FolderKanban, label: 'My Projects' },
  { to: '/krsna/incentive-management', icon: Percent, label: 'My Incentive' },
]

const rmNav = [
  { to: '/krsna/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/krsna/my-leads', icon: UserCircle, label: 'My Leads' },
  { to: '/krsna/my-projects', icon: FolderKanban, label: 'My Projects' },
  { to: '/krsna/incentive-management', icon: Percent, label: 'My Incentive' },
]

const campaignOwnerNav = [
  { to: '/krsna/campaign-leads', icon: Megaphone, label: 'My Leads' },
  { to: '/krsna/incentive-management', icon: Percent, label: 'My Incentive' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const user = getUser()
  const nav = isPresalesUser() && !isAdminUser()
    ? presalesNav
    : isRmUser() && !isAdminUser()
      ? rmNav
      : isCampaignOwnerUser() && !isAdminUser()
        ? campaignOwnerNav
        : adminNav

  const handleLogout = () => {
    clearToken()
    navigate('/krsna')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-60 app-sidebar flex flex-col flex-shrink-0">
        <div className="px-5 py-5 border-b border-slate-200/80 dark:border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--accent-soft)]">
              <Flower2 className="w-4 h-4 text-[var(--accent)]" />
            </div>
            <div>
              <p className="text-sm font-semibold text-theme-primary">CRM admin</p>
              {user?.name && (
                <p className="text-[10px] text-[var(--accent)] mt-0.5 truncate">{user.name}</p>
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

        <div className="px-3 py-4 border-t border-slate-200/80 dark:border-slate-700/50">
          <span className="text-xs text-slate-500 px-3">TatvaOps · v1.0</span>
          <button onClick={handleLogout} className="nav-item w-full mt-2">
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="app-topbar flex items-center justify-between gap-3 px-5 py-3 shrink-0">
          <div className="flex items-center min-w-0">
            <img
              src={`${import.meta.env.BASE_URL}tatvaops-logo.png`}
              alt="tatvaOps"
              className="h-8 w-auto max-w-[180px] object-contain object-left"
            />
          </div>
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-y-auto app-main">{children}</main>
      </div>
    </div>
  )
}

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import {
  isAuthenticated,
  isCampaignOwnerUser,
  isPresalesUser,
  isRmUser,
} from './api/client'
import AppToaster from './components/AppToaster'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import SystemHealth from './pages/SystemHealth'
import Presales from './pages/Presales'
import Users from './pages/Users'
import VendorLeads from './pages/VendorLeads'
import Vendors from './pages/Vendors'
import IncentiveManagement from './pages/IncentiveManagement'
import MyLeads from './pages/MyLeads'
import MyProjects from './pages/MyProjects'
import TeamDashboard from './pages/TeamDashboard'
import CampaignOwnerLeads from './pages/CampaignOwnerLeads'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/krsna" replace />
}


function HomeRedirect() {
  if (isCampaignOwnerUser()) {
    return <Navigate to="campaign-leads" replace />
  }
  if (isPresalesUser()) {
    return <Navigate to="dashboard" replace />
  }
  if (isRmUser()) {
    return <Navigate to="dashboard" replace />
  }
  return <Navigate to="dashboard" replace />
}

function DashboardRoute() {
  if (isCampaignOwnerUser()) {
    return <Navigate to="/krsna/campaign-leads" replace />
  }
  if (isPresalesUser() || isRmUser()) {
    return <TeamDashboard />
  }
  return <Dashboard />
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  if (isCampaignOwnerUser()) {
    return <Navigate to="/krsna/campaign-leads" replace />
  }
  if (isPresalesUser() || isRmUser()) {
    return <Navigate to="/krsna/my-leads" replace />
  }
  return <>{children}</>
}

function EnquiriesRedirect() {
  if (isCampaignOwnerUser()) {
    return <Navigate to="/krsna/campaign-leads" replace />
  }
  if (isPresalesUser() || isRmUser()) {
    return <Navigate to="/krsna/my-leads" replace />
  }
  return <Navigate to="/krsna/presales" replace />
}

function MyLeadsRoute() {
  return isCampaignOwnerUser()
    ? <CampaignOwnerLeads />
    : <MyLeads />
}

function CampaignOwnerRoute() {
  return isCampaignOwnerUser()
    ? <CampaignOwnerLeads />
    : <Navigate to="/krsna/my-leads" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AppToaster />
      <Routes>
        <Route path="/krsna" element={<Login />} />
        <Route path="/krsna/*" element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route index element={<HomeRedirect />} />
                <Route path="my-leads" element={<MyLeadsRoute />} />
                <Route path="campaign-leads" element={<CampaignOwnerRoute />} />
                <Route path="my-projects" element={<MyProjects />} />
                <Route path="dashboard" element={<DashboardRoute />} />
                <Route path="sessions" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="sessions/:id" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="enquiries" element={<EnquiriesRedirect />} />
                <Route path="presales" element={<AdminOnly><Presales /></AdminOnly>} />
                <Route path="team" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="users" element={<AdminOnly><Users /></AdminOnly>} />
                <Route path="vendor-leads" element={<AdminOnly><VendorLeads /></AdminOnly>} />
                <Route path="vendors" element={<AdminOnly><Vendors /></AdminOnly>} />
                <Route path="incentive-management" element={<IncentiveManagement />} />
                <Route path="summaries" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="logs" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="system" element={<AdminOnly><SystemHealth /></AdminOnly>} />
              </Routes>
            </Layout>
          </PrivateRoute>
        } />
        <Route path="*" element={<Navigate to="/krsna" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

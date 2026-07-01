import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { isAuthenticated, isPresalesUser, isRmUser } from './api/client'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import SystemHealth from './pages/SystemHealth'
import Presales from './pages/Presales'
import Users from './pages/Users'
import VendorLeads from './pages/VendorLeads'
import Vendors from './pages/Vendors'
import MyLeads from './pages/MyLeads'
import MyProjects from './pages/MyProjects'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/krsna" replace />
}


function HomeRedirect() {
  if (isPresalesUser()) {
    return <Navigate to="my-leads" replace />
  }
  if (isRmUser()) {
    return <Navigate to="my-leads" replace />
  }
  return <Navigate to="dashboard" replace />
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  if (isPresalesUser() || isRmUser()) {
    return <Navigate to="/krsna/my-leads" replace />
  }
  return <>{children}</>
}

function EnquiriesRedirect() {
  if (isPresalesUser() || isRmUser()) {
    return <Navigate to="/krsna/my-leads" replace />
  }
  return <Navigate to="/krsna/presales" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#111d35',
            color: '#e2e8f0',
            border: '1px solid rgba(99,102,241,0.3)',
          },
        }}
      />
      <Routes>
        <Route path="/krsna" element={<Login />} />
        <Route path="/krsna/*" element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route index element={<HomeRedirect />} />
                <Route path="my-leads" element={<MyLeads />} />
                <Route path="my-projects" element={<MyProjects />} />
                <Route path="dashboard" element={<AdminOnly><Dashboard /></AdminOnly>} />
                <Route path="sessions" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="sessions/:id" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="enquiries" element={<EnquiriesRedirect />} />
                <Route path="presales" element={<AdminOnly><Presales /></AdminOnly>} />
                <Route path="team" element={<Navigate to="/krsna/dashboard" replace />} />
                <Route path="users" element={<AdminOnly><Users /></AdminOnly>} />
                <Route path="vendor-leads" element={<AdminOnly><VendorLeads /></AdminOnly>} />
                <Route path="vendors" element={<AdminOnly><Vendors /></AdminOnly>} />
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

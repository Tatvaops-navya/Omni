import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { isAuthenticated } from './api/client'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Sessions from './pages/Sessions'
import SessionDetail from './pages/SessionDetail'
import Enquiries from './pages/Enquiries'
import Summaries from './pages/Summaries'
import Logs from './pages/Logs'
import SystemHealth from './pages/SystemHealth'
import Files from './pages/Files'
import Presales from './pages/Presales'
import Users from './pages/Users'
import VendorLeads from './pages/VendorLeads'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/krsna" replace />
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
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="sessions" element={<Sessions />} />
                <Route path="sessions/:id" element={<SessionDetail />} />
                <Route path="enquiries" element={<Enquiries />} />
                <Route path="presales" element={<Presales />} />
                <Route path="users" element={<Users />} />
                <Route path="vendor-leads" element={<VendorLeads />} />
                <Route path="summaries" element={<Summaries />} />
                <Route path="logs" element={<Logs />} />
                <Route path="files" element={<Files />} />
                <Route path="system" element={<SystemHealth />} />
                <Route index element={<Navigate to="dashboard" replace />} />
              </Routes>
            </Layout>
          </PrivateRoute>
        } />
        <Route path="*" element={<Navigate to="/krsna" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

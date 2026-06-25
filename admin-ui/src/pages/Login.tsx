import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flower2, Eye, EyeOff } from 'lucide-react'
import { api, setToken } from '../api/client'
import toast from 'react-hot-toast'
import clsx from 'clsx'

type LoginMode = 'admin' | 'team'

export default function Login() {
  const [mode, setMode] = useState<LoginMode>('admin')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = mode === 'admin'
        ? await api.login(password)
        : await api.crmLogin(email, password)
      if (res.token) {
        setToken(res.token, res.user)
        const role = res.user?.role || 'admin'
        navigate(role === 'presales' ? '/krsna/my-leads' : '/krsna/dashboard')
      } else {
        toast.error('Login failed')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed'
      toast.error(message.includes('Failed to fetch') ? 'Cannot reach API' : message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-indigo-600/20 rounded-2xl flex items-center justify-center mx-auto mb-4 ring-1 ring-indigo-500/30">
            <Flower2 className="w-8 h-8 text-indigo-400" />
          </div>
          <h1 className="text-2xl font-semibold text-slate-200">Krsna Panel</h1>
          <p className="text-slate-500 text-sm mt-1">EVA AI Operations_TatvaOps</p>
        </div>

        <div className="flex gap-2 mb-4">
          {(['admin', 'team'] as LoginMode[]).map(key => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              className={clsx(
                'flex-1 py-2 text-sm rounded-lg border transition-colors',
                mode === key
                  ? 'border-indigo-500 bg-indigo-600/10 text-indigo-300'
                  : 'border-slate-700 text-slate-500 hover:text-slate-300',
              )}
            >
              {key === 'admin' ? 'Admin' : 'Team'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          {mode === 'team' && (
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1.5 block">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@tatvaops.com"
                className="input"
                required
              />
            </div>
          )}
          <div>
            <label className="text-xs text-slate-400 font-medium mb-1.5 block">
              {mode === 'admin' ? 'Admin Password' : 'Password'}
            </label>
            <div className="relative">
              <input
                type={show ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={mode === 'admin' ? 'Enter admin password' : 'Enter password'}
                className="input pr-10"
                required
                autoFocus={mode === 'admin'}
              />
              <button
                type="button"
                onClick={() => setShow(s => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full justify-center flex">
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}

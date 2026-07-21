import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flower2, Eye, EyeOff } from 'lucide-react'
import { api, setToken } from '../api/client'
import ThemeToggle from '../components/ThemeToggle'
import { normalizePhone } from '../utils/phone'
import toast from 'react-hot-toast'
import clsx from 'clsx'

type LoginMode = 'admin' | 'team'

const OTP_RESEND_SECONDS = 30

function formatPhoneDisplay(phone: string): string {
  const digits = normalizePhone(phone)
  if (digits.length === 10) return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`
  return phone.trim()
}

export default function Login() {
  const [mode, setMode] = useState<LoginMode>('team')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sendingOtp, setSendingOtp] = useState(false)
  const [resendIn, setResendIn] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (resendIn <= 0) return undefined
    const id = window.setInterval(() => {
      setResendIn(prev => (prev <= 1 ? 0 : prev - 1))
    }, 1000)
    return () => window.clearInterval(id)
  }, [resendIn])

  const phoneDigits = normalizePhone(phone)
  const phoneValid = phoneDigits.length === 10

  const resetTeamOtpState = () => {
    setOtp('')
    setOtpSent(false)
    setResendIn(0)
  }

  const handleModeChange = (next: LoginMode) => {
    setMode(next)
    setPassword('')
    setOtp('')
    setShow(false)
    if (next === 'admin') resetTeamOtpState()
  }

  const handleSendOtp = async () => {
    if (!phoneValid) {
      toast.error('Enter a valid 10-digit mobile number')
      return
    }
    setSendingOtp(true)
    try {
      await api.sendTeamOtp(phoneDigits)
      setOtpSent(true)
      setResendIn(OTP_RESEND_SECONDS)
      toast.success('OTP sent to your mobile number')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send OTP'
      toast.error(message.includes('Failed to fetch') ? 'Cannot reach API' : message)
    } finally {
      setSendingOtp(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = mode === 'admin'
        ? await api.login(email, password)
        : await api.verifyTeamOtp(phoneDigits, otp.trim())
      if (res.token) {
        const tatvaAccessToken =
          (typeof res.tatvaAccessToken === 'string' && res.tatvaAccessToken) ||
          (typeof res.accessToken === 'string' && res.accessToken) ||
          null
        setToken(res.token, res.user, { tatvaAccessToken })
        navigate(
          res.user?.role === 'campaign_owner'
            ? '/krsna/campaign-leads'
            : '/krsna/dashboard',
        )
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
    <div className="min-h-screen bg-slate-50 dark:bg-navy-900 flex items-center justify-center p-4 relative transition-colors duration-300">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-indigo-100 dark:bg-indigo-600/20 rounded-2xl flex items-center justify-center mx-auto mb-4 ring-1 ring-indigo-200 dark:ring-indigo-500/30">
            <Flower2 className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
          </div>
          <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-200">CRM admin panel</h1>
          <p className="text-slate-500 text-sm mt-1">EVA AI Operations_TatvaOps</p>
        </div>

        <div className="flex gap-2 mb-4">
          {(['admin', 'team'] as LoginMode[]).map(key => (
            <button
              key={key}
              type="button"
              onClick={() => handleModeChange(key)}
              className={clsx(
                'flex-1 py-2 text-sm rounded-lg border transition-colors',
                mode === key
                  ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-600/10 dark:text-indigo-300'
                  : 'border-slate-200 text-slate-500 hover:text-slate-700 dark:border-slate-700 dark:text-slate-500 dark:hover:text-slate-300',
              )}
            >
              {key === 'admin' ? 'Admin' : 'Team'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          {mode === 'admin' ? (
            <>
              <div>
                <label className="text-xs text-slate-400 font-medium mb-1.5 block">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="superadmin@tatvaops.com"
                  className="input"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 font-medium mb-1.5 block">Password</label>
                <div className="relative">
                  <input
                    type={show ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Enter password"
                    className="input pr-10"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShow(s => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                  >
                    {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full justify-center flex">
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </>
          ) : (
            <>
              <div>
                <label className="text-xs text-slate-400 font-medium mb-1.5 block">Mobile Number</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-500 pointer-events-none">
                    +91
                  </span>
                  <input
                    type="tel"
                    inputMode="numeric"
                    autoComplete="tel"
                    value={phone}
                    onChange={e => {
                      const digits = e.target.value.replace(/\D/g, '').slice(0, 10)
                      setPhone(digits)
                      if (otpSent) resetTeamOtpState()
                    }}
                    placeholder="9876543210"
                    className="input pl-12 tracking-wide"
                    required
                    autoFocus
                  />
                </div>
              </div>

              {!otpSent ? (
                <button
                  type="button"
                  disabled={sendingOtp || !phoneValid}
                  onClick={handleSendOtp}
                  className="btn-primary w-full justify-center flex"
                >
                  {sendingOtp ? 'Sending OTP...' : 'Send OTP'}
                </button>
              ) : (
                <>
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs text-slate-400 font-medium">OTP</label>
                      <button
                        type="button"
                        disabled={sendingOtp || resendIn > 0}
                        onClick={handleSendOtp}
                        className="text-xs text-indigo-400 hover:text-indigo-300 disabled:text-slate-600 disabled:cursor-not-allowed"
                      >
                        {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend OTP'}
                      </button>
                    </div>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={otp}
                      onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="Enter 6-digit OTP"
                      className="input tracking-[0.35em] text-center text-lg"
                      required
                      minLength={4}
                      maxLength={6}
                      autoFocus
                    />
                    <p className="text-[11px] text-slate-500 mt-1.5">
                      OTP sent to {formatPhoneDisplay(phoneDigits)}
                    </p>
                  </div>
                  <button
                    type="submit"
                    disabled={loading || otp.trim().length < 4}
                    className="btn-primary w-full justify-center flex"
                  >
                    {loading ? 'Verifying...' : 'Verify & Sign In'}
                  </button>
                </>
              )}
            </>
          )}
        </form>
      </div>
    </div>
  )
}

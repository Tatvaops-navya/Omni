import { useEffect, useState } from 'react'
import { api, CrmUser } from '../api/client'
import toast from 'react-hot-toast'

export default function Team() {
  const [users, setUsers] = useState<CrmUser[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('presales')
  const [loading, setLoading] = useState(true)

  const load = () => {
    api.crmUsers().then(d => setUsers(d.users || [])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api.createCrmUser({ name, email, password, role })
      toast.success('Team member created')
      setName('')
      setEmail('')
      setPassword('')
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create user')
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-200">Team</h1>
        <p className="text-sm text-slate-500 mt-1">Presales and RM users for lead assignment</p>
      </div>

      <form onSubmit={handleCreate} className="card grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-slate-500 block mb-1">Name</label>
          <input className="input" value={name} onChange={e => setName(e.target.value)} required />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Email</label>
          <input type="email" className="input" value={email} onChange={e => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Password</label>
          <input type="password" className="input" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Role</label>
          <select className="input" value={role} onChange={e => setRole(e.target.value)}>
            <option value="presales">Presales</option>
            <option value="rm">RM</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <button type="submit" className="btn-primary">Add team member</button>
        </div>
      </form>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase">
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Role</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-500">Loading...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-500">No team members yet.</td></tr>
            ) : users.map(u => (
              <tr key={u.id || u.email || ''} className="border-b border-slate-700/30">
                <td className="px-4 py-3 text-slate-200">{u.name}</td>
                <td className="px-4 py-3 text-slate-400">{u.email}</td>
                <td className="px-4 py-3 text-slate-400 capitalize">{u.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

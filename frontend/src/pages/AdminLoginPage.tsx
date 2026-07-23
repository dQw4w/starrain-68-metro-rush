import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { saveAdminSession } from '../lib/adminSession'

/** Super admin only — team admins get a private link (see AdminLinkPage), no login form. */
export default function AdminLoginPage() {
  const navigate = useNavigate()
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const session = await api.login(pin)
      saveAdminSession(session)
      navigate('/superadmin')
    } catch (e: any) {
      setError(e.message || '登入失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="bg-slate-800 rounded-2xl p-6 w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-2xl font-black text-center">Metro Rush 總管理員登入</h1>
        <p className="text-white/50 text-sm text-center">
          隨隊管理員請使用總管理員提供的專屬連結，不需在此登入。
        </p>

        <input
          type="password"
          inputMode="numeric"
          placeholder="PIN 碼"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          required
          autoFocus
          className="bg-white/10 rounded-lg px-3 py-2.5"
        />

        {error && <p className="text-rose-400 text-sm">{error}</p>}

        <button disabled={busy} type="submit" className="bg-emerald-600 disabled:opacity-40 font-bold rounded-lg py-2.5">
          登入
        </button>
      </form>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { saveAdminSession } from '../lib/adminSession'

/**
 * Landing page for a team admin's private link (/admin/link/:token). The
 * token itself is the credential — no PIN, no form. Exchanges it for a
 * normal session (same shape a PIN login would produce) and continues on to
 * the regular admin dashboard. Revisiting this same bookmarked link later
 * (e.g. after the session expires) just mints a fresh session again.
 */
export default function AdminLinkPage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    api
      .loginByLink(token)
      .then((session) => {
        saveAdminSession(session)
        navigate(`/admin/team/${session.team_id}`, { replace: true })
      })
      .catch((e: any) => setError(e.message || '此連結無效或已被停用'))
  }, [token, navigate])

  return (
    <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-4">
      <div className="text-center">
        {error ? (
          <>
            <p className="text-rose-400 font-bold mb-2">{error}</p>
            <p className="text-white/50 text-sm">請向總管理員確認連結是否正確或已更新。</p>
          </>
        ) : (
          <p className="text-white/60">登入中…</p>
        )}
      </div>
    </div>
  )
}

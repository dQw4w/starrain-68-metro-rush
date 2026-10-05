import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import SuperAdminPage from './pages/SuperAdminPage'
import TeamAdminPage from './pages/TeamAdminPage'
import TeamPage from './pages/TeamPage'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/team/:token" element={<TeamPage />} />
          {/* Same token, view-only. Not a security boundary — anyone here can
              drop the /view and act. It exists so one team member drives and
              everyone else can follow along without racing them into the same
              claim or challenge. */}
          <Route path="/team/:token/view" element={<TeamPage readOnly />} />
          {/* :idOrToken is a numeric team_id (super admin, uses their own Bearer
              session) OR a team's permanent admin_share_token (works on its own,
              no login) — TeamAdminPage figures out which. */}
          <Route path="/admin/team/:idOrToken" element={<TeamAdminPage />} />
          {/* Super admin login is a PIN form inlined on this page itself, not a
              separate route — see SuperAdminPage.tsx. */}
          <Route path="/superadmin" element={<SuperAdminPage />} />
          <Route path="*" element={<Navigate to="/superadmin" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

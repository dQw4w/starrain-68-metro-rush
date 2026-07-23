import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLoginPage from './pages/AdminLoginPage'
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
          <Route path="/admin/login" element={<AdminLoginPage />} />
          {/* :idOrToken is a numeric team_id (super admin, uses their own Bearer
              session) OR a team's permanent admin_share_token (works on its own,
              no login) — TeamAdminPage figures out which. */}
          <Route path="/admin/team/:idOrToken" element={<TeamAdminPage />} />
          <Route path="/superadmin" element={<SuperAdminPage />} />
          <Route path="*" element={<Navigate to="/admin/login" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLinkPage from './pages/AdminLinkPage'
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
          <Route path="/admin/link/:token" element={<AdminLinkPage />} />
          <Route path="/admin/team/:teamId" element={<TeamAdminPage />} />
          <Route path="/superadmin" element={<SuperAdminPage />} />
          <Route path="*" element={<Navigate to="/admin/login" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

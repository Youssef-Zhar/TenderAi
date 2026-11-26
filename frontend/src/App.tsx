import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import DashboardLayout from './layouts/DashboardLayout'
import Analysis from './pages/Analysis'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Tenders from './pages/Tenders'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Public shell: visitors can explore the interface without seeing account data. */}
      <Route element={<DashboardLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/tenders" element={<Tenders />} />
      </Route>

      {/* Uploading and analysing a PDF always requires an authenticated account. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/analysis" element={<Analysis />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default App

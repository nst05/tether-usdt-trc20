import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Header } from './components/layout/Header'
import { Footer } from './components/layout/Footer'
import { Home } from './pages/Home'
import { Catalog } from './pages/Catalog'
import { EquipmentDetail } from './pages/EquipmentDetail'
import { ProjectWizard } from './pages/ProjectWizard'
import { Booking } from './pages/Booking'
import { About } from './pages/About'
import { Contact } from './pages/Contact'
import { AdminLayout } from './pages/admin/AdminLayout'
import { Dashboard } from './pages/admin/Dashboard'
import { EquipmentManagement } from './pages/admin/EquipmentManagement'
import { OrdersManagement } from './pages/admin/OrdersManagement'
import { ClientsManagement } from './pages/admin/ClientsManagement'
import { Analytics } from './pages/admin/Analytics'
import { Settings } from './pages/admin/Settings'

const PublicLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="min-h-screen flex flex-col">
    <Header />
    <main className="flex-1">{children}</main>
    <Footer />
  </div>
)

function App() {
  return (
    <BrowserRouter basename="/tether-usdt-trc20">
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<PublicLayout><Home /></PublicLayout>} />
        <Route path="/catalog" element={<PublicLayout><Catalog /></PublicLayout>} />
        <Route path="/catalog/:id" element={<PublicLayout><EquipmentDetail /></PublicLayout>} />
        <Route path="/wizard" element={<PublicLayout><ProjectWizard /></PublicLayout>} />
        <Route path="/booking" element={<PublicLayout><Booking /></PublicLayout>} />
        <Route path="/about" element={<PublicLayout><About /></PublicLayout>} />
        <Route path="/contact" element={<PublicLayout><Contact /></PublicLayout>} />

        {/* Admin routes */}
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="equipment" element={<EquipmentManagement />} />
          <Route path="orders" element={<OrdersManagement />} />
          <Route path="clients" element={<ClientsManagement />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

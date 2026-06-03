import React, { useEffect, useState } from 'react'
import { Plus, Search, Trash2, X, Check } from 'lucide-react'
import { useAdminStore } from '../../store/adminStore'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { Equipment } from '../../types'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

const STATUS_OPTIONS = [
  { value: 'available', label: 'Доступно' },
  { value: 'rented', label: 'Арендовано' },
  { value: 'maintenance', label: 'На обслуживании' },
]

const EMPTY_EQUIPMENT: Omit<Equipment, 'id'> = {
  name: '',
  category: 'Экскаваторы',
  subcategory: '',
  image: '',
  specs: {},
  pricePerDay: 0,
  pricePerWeek: 0,
  pricePerMonth: 0,
  availability: 'available',
  location: '',
  rating: 5.0,
  reviewCount: 0,
  description: '',
  features: [],
  weight: 0,
  power: '',
  tags: [],
}

const CATEGORIES = ['Экскаваторы', 'Краны', 'Бульдозеры', 'Погрузчики', 'Дорожная техника', 'Буровая техника']

export const EquipmentManagement: React.FC = () => {
  const { equipment, updateEquipmentStatus, deleteEquipment, addEquipment } = useAdminStore()

  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('Все')
  const [showModal, setShowModal] = useState(false)
  const [editForm, setEditForm] = useState<Omit<Equipment, 'id'>>(EMPTY_EQUIPMENT)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  useEffect(() => {
    document.title = 'Управление техникой — Админ'
  }, [])

  const filtered = equipment.filter((e) => {
    const q = search.toLowerCase()
    const matchesSearch = !q || e.name.toLowerCase().includes(q) || e.category.toLowerCase().includes(q)
    const matchesCategory = categoryFilter === 'Все' || e.category === categoryFilter
    return matchesSearch && matchesCategory
  })

  const handleAdd = () => {
    const id = `eq-${Date.now()}`
    addEquipment({ ...editForm, id })
    setShowModal(false)
    setEditForm(EMPTY_EQUIPMENT)
  }

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-black text-white">Управление техникой</h1>
          <p className="text-gray-500 text-sm">Всего: {equipment.length} единиц</p>
        </div>
        <Button onClick={() => setShowModal(true)} className="gap-2">
          <Plus size={16} />
          Добавить технику
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию..."
            className="w-full bg-gray-900 border border-gray-700 text-gray-100 rounded-lg pl-9 pr-4 py-2.5 text-sm outline-none focus:border-amber-500 transition placeholder:text-gray-600"
          />
        </div>
        <div className="flex gap-2">
          {['Все', ...CATEGORIES].map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                categoryFilter === cat
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'bg-gray-900 border border-gray-700 text-gray-500 hover:border-gray-600'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Техника</th>
              <th className="text-left px-5 py-3 hidden md:table-cell">Категория</th>
              <th className="text-left px-5 py-3 hidden lg:table-cell">Цена/день</th>
              <th className="text-left px-5 py-3">Статус</th>
              <th className="text-right px-5 py-3">Действия</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((eq) => (
              <tr key={eq.id} className="border-b border-gray-800/50 last:border-0 hover:bg-gray-800/30 transition-colors">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-3">
                    <img src={eq.image} alt={eq.name} className="w-12 h-9 object-cover rounded" />
                    <div>
                      <div className="text-sm font-medium text-gray-200">{eq.name}</div>
                      <div className="text-xs text-gray-600">{eq.location}</div>
                    </div>
                  </div>
                </td>
                <td className="px-5 py-3 hidden md:table-cell">
                  <span className="text-xs text-gray-400">{eq.category}</span>
                </td>
                <td className="px-5 py-3 hidden lg:table-cell">
                  <span className="text-sm font-medium text-amber-400">{formatPrice(eq.pricePerDay)} ₽</span>
                </td>
                <td className="px-5 py-3">
                  <select
                    value={eq.availability}
                    onChange={(e) => updateEquipmentStatus(eq.id, e.target.value as Equipment['availability'])}
                    className="bg-gray-800 border border-gray-700 text-gray-300 rounded-md px-2 py-1 text-xs outline-none cursor-pointer focus:border-amber-500 transition"
                  >
                    {STATUS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </td>
                <td className="px-5 py-3">
                  <div className="flex items-center justify-end gap-2">
                    {deleteConfirm === eq.id ? (
                      <>
                        <button
                          onClick={() => { deleteEquipment(eq.id); setDeleteConfirm(null) }}
                          className="p-1.5 text-red-400 hover:bg-red-500/10 rounded transition-colors cursor-pointer"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="p-1.5 text-gray-500 hover:bg-gray-800 rounded transition-colors cursor-pointer"
                        >
                          <X size={14} />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setDeleteConfirm(eq.id)}
                        className="p-1.5 text-gray-600 hover:text-red-400 hover:bg-red-500/10 rounded transition-all cursor-pointer"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-10 text-gray-600">Ничего не найдено</div>
        )}
      </div>

      {/* Add modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-gray-800">
              <h2 className="font-bold text-gray-200">Добавить технику</h2>
              <button onClick={() => setShowModal(false)} className="text-gray-500 hover:text-gray-300 cursor-pointer">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <Input label="Название *" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Экскаватор CAT 320" />
              <div className="grid grid-cols-2 gap-4">
                <Select
                  label="Категория"
                  options={CATEGORIES.map((c) => ({ value: c, label: c }))}
                  value={editForm.category}
                  onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                />
                <Input label="Подкатегория" value={editForm.subcategory} onChange={(e) => setEditForm({ ...editForm, subcategory: e.target.value })} />
              </div>
              <Input label="URL изображения" value={editForm.image} onChange={(e) => setEditForm({ ...editForm, image: e.target.value })} placeholder="https://images.unsplash.com/..." />
              <div className="grid grid-cols-3 gap-3">
                <Input label="Цена/день (₽)" type="number" value={editForm.pricePerDay || ''} onChange={(e) => setEditForm({ ...editForm, pricePerDay: Number(e.target.value) })} />
                <Input label="Цена/неделя (₽)" type="number" value={editForm.pricePerWeek || ''} onChange={(e) => setEditForm({ ...editForm, pricePerWeek: Number(e.target.value) })} />
                <Input label="Цена/месяц (₽)" type="number" value={editForm.pricePerMonth || ''} onChange={(e) => setEditForm({ ...editForm, pricePerMonth: Number(e.target.value) })} />
              </div>
              <Input label="Местоположение" value={editForm.location} onChange={(e) => setEditForm({ ...editForm, location: e.target.value })} placeholder="Москва, склад №1" />
              <Input label="Мощность" value={editForm.power} onChange={(e) => setEditForm({ ...editForm, power: e.target.value })} placeholder="150 л.с." />
              <div>
                <label className="text-sm font-medium text-gray-300 mb-1.5 block">Описание</label>
                <textarea
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  rows={3}
                  className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-amber-500 transition resize-none placeholder:text-gray-600"
                />
              </div>
            </div>
            <div className="p-5 border-t border-gray-800 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setShowModal(false)}>Отмена</Button>
              <Button onClick={handleAdd} disabled={!editForm.name}>Добавить</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

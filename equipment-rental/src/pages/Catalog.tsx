import React, { useEffect, useState, useMemo } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, SlidersHorizontal, Grid3X3, List, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { EquipmentCard } from '../components/EquipmentCard'
import { equipmentData } from '../data/equipment'
import { Select } from '../components/ui/Select'
import { Equipment } from '../types'
import { useCartStore } from '../store/cartStore'

const ITEMS_PER_PAGE = 9

const CATEGORIES = ['Все', 'Экскаваторы', 'Краны', 'Бульдозеры', 'Погрузчики', 'Дорожная техника', 'Буровая техника']
const AVAILABILITY_OPTIONS = [
  { value: 'Все', label: 'Все статусы' },
  { value: 'available', label: 'Доступно' },
  { value: 'rented', label: 'Арендовано' },
  { value: 'maintenance', label: 'На обслуживании' },
]

const SORT_OPTIONS = [
  { value: 'name_asc', label: 'По названию (А–Я)' },
  { value: 'name_desc', label: 'По названию (Я–А)' },
  { value: 'price_asc', label: 'Цена: по возрастанию' },
  { value: 'price_desc', label: 'Цена: по убыванию' },
  { value: 'rating_desc', label: 'По рейтингу' },
]

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

const EquipmentListItem: React.FC<{ equipment: Equipment }> = ({ equipment }) => {
  const { addItem, items } = useCartStore()
  const isInCart = items.some((i) => i.equipment.id === equipment.id)

  const today = new Date()
  const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
  const startDate = today.toISOString().split('T')[0]
  const endDate = nextWeek.toISOString().split('T')[0]

  const statusColor = {
    available: 'bg-emerald-500/15 text-emerald-400',
    rented: 'bg-red-500/15 text-red-400',
    maintenance: 'bg-yellow-500/15 text-yellow-400',
  }[equipment.availability]

  const statusLabel = {
    available: 'Доступно',
    rented: 'Арендовано',
    maintenance: 'Обслуживание',
  }[equipment.availability]

  return (
    <div className="bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden hover:border-blue-500/30 transition-all flex">
      <div className="w-48 shrink-0 overflow-hidden">
        <img src={equipment.image} alt={equipment.name} className="w-full h-full object-cover" />
      </div>
      <div className="p-5 flex flex-col justify-between flex-1">
        <div>
          <div className="flex items-start justify-between gap-3 mb-2">
            <h3 className="font-bold text-gray-100">{equipment.name}</h3>
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium shrink-0 ${statusColor}`}>
              {statusLabel}
            </span>
          </div>
          <p className="text-sm text-gray-500 line-clamp-2 mb-3">{equipment.description}</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(equipment.specs).slice(0, 3).map(([k, v]) => (
              <span key={k} className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
                {k}: {v}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between mt-4">
          <div>
            <span className="text-xl font-bold text-blue-400">{formatPrice(equipment.pricePerDay)}</span>
            <span className="text-gray-500 text-sm"> ₽/день</span>
          </div>
          <div className="flex gap-2">
            <Link to={`/catalog/${equipment.id}`}>
              <button className="px-4 py-2 border border-blue-500 text-blue-500 rounded-lg text-sm font-medium hover:bg-blue-500/10 transition-all cursor-pointer">
                Подробнее
              </button>
            </Link>
            <button
              onClick={() => !isInCart && equipment.availability === 'available' && addItem(equipment, startDate, endDate)}
              disabled={equipment.availability !== 'available' || isInCart}
              className="px-4 py-2 bg-blue-500 text-gray-900 rounded-lg text-sm font-bold hover:bg-amber-400 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              {isInCart ? 'В корзине' : 'В корзину'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export const Catalog: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState(searchParams.get('category') || 'Все')
  const [availability, setAvailability] = useState('Все')
  const [sortBy, setSortBy] = useState('name_asc')
  const [priceMax, setPriceMax] = useState(100000)
  const [page, setPage] = useState(1)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    document.title = 'Каталог техники — ТЕХПРОКАТ'
    const cat = searchParams.get('category')
    if (cat) setCategory(cat)
  }, [searchParams])

  const maxPrice = useMemo(() => Math.max(...equipmentData.map((e) => e.pricePerDay)), [])

  const filtered = useMemo(() => {
    let result = [...equipmentData]

    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          e.category.toLowerCase().includes(q) ||
          e.tags.some((t) => t.toLowerCase().includes(q))
      )
    }
    if (category !== 'Все') result = result.filter((e) => e.category === category)
    if (availability !== 'Все') result = result.filter((e) => e.availability === availability)
    result = result.filter((e) => e.pricePerDay <= priceMax)

    result.sort((a, b) => {
      switch (sortBy) {
        case 'name_asc': return a.name.localeCompare(b.name)
        case 'name_desc': return b.name.localeCompare(a.name)
        case 'price_asc': return a.pricePerDay - b.pricePerDay
        case 'price_desc': return b.pricePerDay - a.pricePerDay
        case 'rating_desc': return b.rating - a.rating
        default: return 0
      }
    })
    return result
  }, [search, category, availability, sortBy, priceMax])

  const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE)
  const paginated = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE)

  const handleCategoryChange = (cat: string) => {
    setCategory(cat)
    setPage(1)
    if (cat !== 'Все') setSearchParams({ category: cat })
    else setSearchParams({})
  }

  const resetFilters = () => {
    setSearch('')
    setCategory('Все')
    setAvailability('Все')
    setSortBy('name_asc')
    setPriceMax(maxPrice)
    setPage(1)
    setSearchParams({})
  }

  const activeFiltersCount = [
    search !== '',
    category !== 'Все',
    availability !== 'Все',
    priceMax < maxPrice,
  ].filter(Boolean).length

  return (
    <PageTransition>
    <div className="min-h-screen pt-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-black text-white mb-2">
            Каталог <span className="gradient-text">техники</span>
          </h1>
          <p className="text-gray-500">
            Найдено: <span className="text-blue-400 font-medium">{filtered.length}</span> единиц
          </p>
        </div>

        <div className="flex gap-8">
          {/* Sidebar */}
          <aside className={`w-72 shrink-0 ${sidebarOpen ? 'block' : 'hidden'} lg:block`}>
            <div className="bg-gray-900 border border-gray-700/50 rounded-xl p-5 sticky top-20">
              <div className="flex items-center justify-between mb-5">
                <h2 className="font-bold text-gray-200">Фильтры</h2>
                {activeFiltersCount > 0 && (
                  <button
                    onClick={resetFilters}
                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 cursor-pointer"
                  >
                    <X size={12} />
                    Сбросить ({activeFiltersCount})
                  </button>
                )}
              </div>

              {/* Search */}
              <div className="mb-5">
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Поиск</label>
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                    placeholder="Название, тег..."
                    className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg pl-9 pr-4 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-600/20 transition placeholder:text-gray-600"
                  />
                </div>
              </div>

              {/* Categories */}
              <div className="mb-5">
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Категория</label>
                <div className="space-y-1">
                  {CATEGORIES.map((cat) => (
                    <button
                      key={cat}
                      onClick={() => handleCategoryChange(cat)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
                        category === cat
                          ? 'bg-blue-500/15 text-blue-400 font-medium'
                          : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Availability */}
              <div className="mb-5">
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Статус</label>
                <div className="space-y-1">
                  {AVAILABILITY_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => { setAvailability(opt.value); setPage(1) }}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
                        availability === opt.value
                          ? 'bg-blue-500/15 text-blue-400 font-medium'
                          : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Price range */}
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Цена до (₽/день)</label>
                <input
                  type="range"
                  min={5000}
                  max={maxPrice}
                  step={1000}
                  value={priceMax}
                  onChange={(e) => { setPriceMax(Number(e.target.value)); setPage(1) }}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>5 000 ₽</span>
                  <span className="text-blue-400 font-medium">{formatPrice(priceMax)} ₽</span>
                </div>
              </div>
            </div>
          </aside>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            {/* Toolbar */}
            <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden flex items-center gap-2 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 hover:border-blue-500/40 transition-all cursor-pointer"
              >
                <SlidersHorizontal size={16} />
                Фильтры
                {activeFiltersCount > 0 && (
                  <span className="bg-blue-500 text-gray-900 text-xs font-bold w-5 h-5 rounded-full flex items-center justify-center">
                    {activeFiltersCount}
                  </span>
                )}
              </button>

              <div className="flex items-center gap-3 ml-auto">
                <Select
                  options={SORT_OPTIONS}
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="text-sm w-52"
                />

                <div className="flex border border-gray-700 rounded-lg overflow-hidden">
                  <button
                    onClick={() => setViewMode('grid')}
                    className={`p-2 transition-colors cursor-pointer ${viewMode === 'grid' ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
                  >
                    <Grid3X3 size={16} />
                  </button>
                  <button
                    onClick={() => setViewMode('list')}
                    className={`p-2 transition-colors cursor-pointer ${viewMode === 'list' ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
                  >
                    <List size={16} />
                  </button>
                </div>
              </div>
            </div>

            {/* Results */}
            {paginated.length === 0 ? (
              <div className="text-center py-20 text-gray-500">
                <Search size={40} className="mx-auto mb-4 opacity-30" />
                <p className="text-lg">Ничего не найдено</p>
                <p className="text-sm mt-1">Попробуйте изменить параметры фильтров</p>
                <button
                  onClick={resetFilters}
                  className="mt-4 text-blue-400 text-sm hover:underline cursor-pointer"
                >
                  Сбросить все фильтры
                </button>
              </div>
            ) : (
              <div className={
                viewMode === 'grid'
                  ? 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5'
                  : 'space-y-4'
              }>
                {paginated.map((eq) =>
                  viewMode === 'grid' ? (
                    <EquipmentCard key={eq.id} equipment={eq} />
                  ) : (
                    <EquipmentListItem key={eq.id} equipment={eq} />
                  )
                )}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-8">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:border-blue-500/40 hover:text-blue-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer"
                >
                  <ChevronLeft size={16} />
                </button>
                {Array.from({ length: totalPages }).map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setPage(i + 1)}
                    className={`w-9 h-9 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                      page === i + 1
                        ? 'bg-blue-500 text-gray-900'
                        : 'border border-gray-700 text-gray-400 hover:border-blue-500/40 hover:text-blue-400'
                    }`}
                  >
                    {i + 1}
                  </button>
                ))}
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:border-blue-500/40 hover:text-blue-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
    </PageTransition>
  )
}

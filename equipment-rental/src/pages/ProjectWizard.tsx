import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, ChevronLeft, Zap, Check, X, ShoppingCart } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { equipmentData } from '../data/equipment'
import { useCartStore } from '../store/cartStore'
import { WizardData, RecommendedPackage } from '../types'

const PROJECT_TYPES = [
  { id: 'construction', label: 'Строительство', icon: '🏗', desc: 'Жилые и коммерческие объекты' },
  { id: 'demolition', label: 'Демонтаж', icon: '💥', desc: 'Снос и разборка конструкций' },
  { id: 'earthworks', label: 'Земляные работы', icon: '⛏', desc: 'Котлованы, траншеи, планировка' },
  { id: 'road', label: 'Дорожные работы', icon: '🛣', desc: 'Строительство и ремонт дорог' },
  { id: 'utility', label: 'Коммунальные работы', icon: '🔧', desc: 'Прокладка коммуникаций' },
]

const TERRAIN_OPTIONS = [
  { value: '', label: 'Выберите тип грунта' },
  { value: 'soft', label: 'Мягкий грунт (песок, суглинок)' },
  { value: 'medium', label: 'Средний грунт (глина, суглинок)' },
  { value: 'hard', label: 'Твёрдый грунт (скала, мёрзлый)' },
  { value: 'mixed', label: 'Смешанный грунт' },
]

const ACCESS_OPTIONS = [
  { value: '', label: 'Выберите тип доступа' },
  { value: 'open', label: 'Открытая площадка' },
  { value: 'limited', label: 'Ограниченное пространство' },
  { value: 'urban', label: 'Городская застройка' },
  { value: 'remote', label: 'Удалённый объект' },
]

const BUDGET_OPTIONS = [
  { value: '', label: 'Выберите бюджет' },
  { value: 'small', label: 'до 500 000 ₽' },
  { value: 'medium', label: '500 000 – 2 000 000 ₽' },
  { value: 'large', label: '2 000 000 – 5 000 000 ₽' },
  { value: 'unlimited', label: 'Без ограничений' },
]

const SCAN_MESSAGES = [
  'Анализ параметров проекта...',
  'Расчёт нагрузки на грунт...',
  'Подбор оптимальной конфигурации...',
  'Проверка доступности техники...',
  'Расчёт эффективности пакета...',
  'Формирование пакетного предложения...',
  'Оптимизация стоимости...',
  'Финализация рекомендаций...',
]

function recommendEquipment(data: WizardData): RecommendedPackage[] {
  const today = new Date()
  const endDate = data.endDate || new Date(today.getTime() + (parseInt(data.volume) || 14) * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  const startDate = data.startDate || today.toISOString().split('T')[0]
  const days = Math.max(7, Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24)))

  const packages: RecommendedPackage[] = []

  const addEquip = (id: string, reason: string) => {
    const eq = equipmentData.find((e) => e.id === id && e.availability === 'available')
    if (eq) {
      const subtotal = days >= 30
        ? Math.floor(days / 30) * eq.pricePerMonth + (days % 30) * eq.pricePerDay
        : days >= 7
        ? Math.floor(days / 7) * eq.pricePerWeek + (days % 7) * eq.pricePerDay
        : days * eq.pricePerDay
      packages.push({ equipment: eq, reason, quantity: 1, days, subtotal })
    }
  }

  if (data.projectType === 'construction' || data.projectType === 'earthworks') {
    addEquip('exc-320', 'Основная землеройная машина для рытья котлована и траншей')
    if (parseInt(data.area) > 5000) {
      addEquip('bull-d6t', 'Бульдозер для планировки и перемещения грунта на большой площади')
    }
    addEquip('loader-cat-950', 'Погрузчик для перемещения строительных материалов')
  }

  if (data.projectType === 'demolition') {
    addEquip('exc-long-reach', 'Экскаватор с удлинённой рукоятью для безопасного демонтажа')
    addEquip('loader-jcb-3cx', 'Экскаватор-погрузчик для уборки и вывоза мусора')
  }

  if (data.projectType === 'road') {
    addEquip('road-grader', 'Грейдер для профилирования и выравнивания дорожного основания')
    addEquip('road-compactor', 'Каток для уплотнения грунтового основания')
    addEquip('paver-vogele', 'Асфальтоукладчик для финишного покрытия')
  }

  if (data.projectType === 'utility') {
    addEquip('exc-mini-kubota', 'Мини-экскаватор для работ в стеснённых условиях городской среды')
    addEquip('loader-jcb-3cx', 'Экскаватор-погрузчик для универсальных коммунальных работ')
  }

  if (data.terrain === 'hard' && !packages.some((p) => p.equipment.id === 'drilling-atlas')) {
    addEquip('drilling-atlas', 'Буровая установка для работы с твёрдым грунтом')
  }

  if (data.projectType === 'construction' && (parseInt(data.area) || 0) > 3000) {
    addEquip('crane-liebherr-ltm1100', 'Автокран для монтажных работ на крупном строительном объекте')
  }

  // Ensure at least 2 items
  if (packages.length < 2) {
    addEquip('exc-320', 'Универсальная землеройная машина для большинства задач проекта')
    addEquip('loader-jcb-3cx', 'Экскаватор-погрузчик для вспомогательных работ')
  }

  return packages.slice(0, 5)
}

export const ProjectWizard: React.FC = () => {
  const navigate = useNavigate()
  const { addItem, items } = useCartStore()

  const [step, setStep] = useState(1)
  const [wizardData, setWizardData] = useState<WizardData>({
    projectType: '',
    area: '',
    volume: '',
    startDate: '',
    endDate: '',
    terrain: '',
    access: '',
    budget: '',
  })
  const [scanProgress, setScanProgress] = useState(0)
  const [scanMsg, setScanMsg] = useState(0)
  const [recommendations, setRecommendations] = useState<RecommendedPackage[]>([])
  const [removedIds, setRemovedIds] = useState<string[]>([])

  useEffect(() => {
    document.title = 'Мастер подбора — ТЕХПРОКАТ'
  }, [])

  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const msgRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (step !== 5) return

    setScanProgress(0)
    setScanMsg(0)

    progressRef.current = setInterval(() => {
      setScanProgress((p) => {
        if (p >= 100) {
          clearInterval(progressRef.current!)
          setTimeout(() => {
            const recs = recommendEquipment(wizardData)
            setRecommendations(recs)
            setStep(6)
          }, 500)
          return 100
        }
        return p + 2.5
      })
    }, 100)

    msgRef.current = setInterval(() => {
      setScanMsg((m) => (m + 1) % SCAN_MESSAGES.length)
    }, 500)

    return () => {
      clearInterval(progressRef.current!)
      clearInterval(msgRef.current!)
    }
  }, [step])

  const activeRecs = recommendations.filter((r) => !removedIds.includes(r.equipment.id))
  const totalPackagePrice = activeRecs.reduce((s, r) => s + r.subtotal, 0)
  const individualPrice = activeRecs.reduce((s, r) => s + r.days * r.equipment.pricePerDay, 0)
  const savings = individualPrice - totalPackagePrice

  const handleBookPackage = () => {
    activeRecs.forEach((rec) => {
      if (items.every((i) => i.equipment.id !== rec.equipment.id)) {
        addItem(rec.equipment, wizardData.startDate || new Date().toISOString().split('T')[0], wizardData.endDate || new Date(Date.now() + rec.days * 86400000).toISOString().split('T')[0])
      }
    })
    navigate('/booking')
  }

  const today = new Date().toISOString().split('T')[0]

  return (
    <div className="min-h-screen pt-16 bg-gray-950">
      {/* Header */}
      {step !== 5 && (
        <div className="border-b border-gray-800/50 bg-gray-900/30">
          <div className="max-w-3xl mx-auto px-4 py-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-amber-500/20 border border-amber-500/40 rounded-lg flex items-center justify-center">
                <Zap size={16} className="text-amber-400" />
              </div>
              <h1 className="text-xl font-black text-white">Мастер подбора проектной конфигурации</h1>
            </div>

            {/* Steps indicator */}
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4].map((s) => (
                <React.Fragment key={s}>
                  <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold transition-all ${
                    step > s ? 'bg-amber-500 text-gray-900' :
                    step === s ? 'bg-amber-500/20 border border-amber-500 text-amber-400' :
                    'bg-gray-800 border border-gray-700 text-gray-600'
                  }`}>
                    {step > s ? <Check size={12} /> : s}
                  </div>
                  {s < 4 && <div className={`flex-1 h-px ${step > s ? 'bg-amber-500' : 'bg-gray-700'}`} />}
                </React.Fragment>
              ))}
            </div>

            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>Тип проекта</span>
              <span>Параметры</span>
              <span>Сроки</span>
              <span>Условия</span>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-3xl mx-auto px-4 py-10">
        {/* Step 1: Project type */}
        {step === 1 && (
          <div className="animate-fade-in">
            <h2 className="text-2xl font-black text-white mb-2">Тип проекта</h2>
            <p className="text-gray-500 mb-8">Выберите тип работ, которые необходимо выполнить</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {PROJECT_TYPES.map((pt) => (
                <button
                  key={pt.id}
                  onClick={() => { setWizardData(d => ({ ...d, projectType: pt.id })); setStep(2) }}
                  className={`group text-left p-5 rounded-xl border transition-all cursor-pointer ${
                    wizardData.projectType === pt.id
                      ? 'border-amber-500 bg-amber-500/10'
                      : 'border-gray-700/50 bg-gray-900 hover:border-amber-500/40 hover:bg-amber-500/5'
                  }`}
                >
                  <div className="text-3xl mb-3">{pt.icon}</div>
                  <div className="font-bold text-gray-100 group-hover:text-amber-400 transition-colors">{pt.label}</div>
                  <div className="text-sm text-gray-500 mt-1">{pt.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Parameters */}
        {step === 2 && (
          <div className="animate-fade-in">
            <h2 className="text-2xl font-black text-white mb-2">Параметры объекта</h2>
            <p className="text-gray-500 mb-8">Укажите масштаб проекта для точного подбора</p>
            <div className="space-y-5">
              <Input
                label="Площадь объекта (м²)"
                type="number"
                value={wizardData.area}
                onChange={(e) => setWizardData(d => ({ ...d, area: e.target.value }))}
                placeholder="Например: 5000"
              />
              <Input
                label="Объём работ (м³) — опционально"
                type="number"
                value={wizardData.volume}
                onChange={(e) => setWizardData(d => ({ ...d, volume: e.target.value }))}
                placeholder="Например: 2000"
              />
            </div>
            <div className="flex gap-3 mt-8">
              <Button variant="ghost" onClick={() => setStep(1)} className="gap-2">
                <ChevronLeft size={16} /> Назад
              </Button>
              <Button onClick={() => setStep(3)} className="gap-2 flex-1">
                Далее <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Timeline */}
        {step === 3 && (
          <div className="animate-fade-in">
            <h2 className="text-2xl font-black text-white mb-2">Сроки выполнения</h2>
            <p className="text-gray-500 mb-8">Укажите плановые даты начала и завершения работ</p>
            <div className="grid grid-cols-2 gap-5">
              <div>
                <label className="text-sm font-medium text-gray-300 mb-1.5 block">Дата начала</label>
                <input
                  type="date"
                  value={wizardData.startDate}
                  min={today}
                  onChange={(e) => setWizardData(d => ({ ...d, startDate: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-amber-500 transition"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-300 mb-1.5 block">Дата окончания</label>
                <input
                  type="date"
                  value={wizardData.endDate}
                  min={wizardData.startDate || today}
                  onChange={(e) => setWizardData(d => ({ ...d, endDate: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-amber-500 transition"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-8">
              <Button variant="ghost" onClick={() => setStep(2)} className="gap-2">
                <ChevronLeft size={16} /> Назад
              </Button>
              <Button onClick={() => setStep(4)} className="gap-2 flex-1">
                Далее <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Additional params */}
        {step === 4 && (
          <div className="animate-fade-in">
            <h2 className="text-2xl font-black text-white mb-2">Условия работы</h2>
            <p className="text-gray-500 mb-8">Уточните характеристики для более точного подбора</p>
            <div className="space-y-5">
              <Select
                label="Тип грунта"
                options={TERRAIN_OPTIONS}
                value={wizardData.terrain}
                onChange={(e) => setWizardData(d => ({ ...d, terrain: e.target.value }))}
              />
              <Select
                label="Условия доступа на объект"
                options={ACCESS_OPTIONS}
                value={wizardData.access}
                onChange={(e) => setWizardData(d => ({ ...d, access: e.target.value }))}
              />
              <Select
                label="Бюджет на аренду"
                options={BUDGET_OPTIONS}
                value={wizardData.budget}
                onChange={(e) => setWizardData(d => ({ ...d, budget: e.target.value }))}
              />
            </div>
            <div className="flex gap-3 mt-8">
              <Button variant="ghost" onClick={() => setStep(3)} className="gap-2">
                <ChevronLeft size={16} /> Назад
              </Button>
              <Button onClick={() => setStep(5)} className="gap-2 flex-1">
                <Zap size={16} />
                Запустить подбор
              </Button>
            </div>
          </div>
        )}

        {/* Step 5: Scanning animation */}
        {step === 5 && (
          <div className="fixed inset-0 bg-gray-950 flex flex-col items-center justify-center z-50">
            <div className="relative w-64 h-64 mb-12">
              {/* Pulsing rings */}
              <div className="absolute inset-0 rounded-full border border-amber-500/20 scanner-ping" />
              <div className="absolute inset-6 rounded-full border border-amber-500/30 scanner-ping-2" />
              <div className="absolute inset-12 rounded-full border border-amber-500/50 scanner-ping-3" />

              {/* Rotating ring */}
              <div
                className="absolute inset-0 rounded-full border-2 border-transparent scanner-rotate"
                style={{ borderTopColor: '#F59E0B', borderRightColor: 'rgba(245,158,11,0.3)' }}
              />

              {/* Center */}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-20 h-20 bg-amber-500/10 border border-amber-500/40 rounded-full flex items-center justify-center">
                  <Zap size={36} className="text-amber-400" />
                </div>
              </div>
            </div>

            <div className="text-center w-full max-w-sm px-4">
              <h2 className="text-2xl font-black text-white mb-3">Анализ проекта</h2>
              <p className="text-amber-400 text-sm font-medium mb-6 h-5 transition-all">
                {SCAN_MESSAGES[scanMsg]}
              </p>

              {/* Progress bar */}
              <div className="w-full bg-gray-800 rounded-full h-2 mb-2 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-600 to-amber-400 rounded-full transition-all duration-100"
                  style={{ width: `${scanProgress}%` }}
                />
              </div>
              <p className="text-gray-600 text-sm">{Math.round(scanProgress)}%</p>
            </div>
          </div>
        )}

        {/* Step 6: Results */}
        {step === 6 && (
          <div className="animate-fade-in">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-emerald-500/20 border border-emerald-500/40 rounded-xl flex items-center justify-center">
                <Check size={20} className="text-emerald-400" />
              </div>
              <div>
                <h2 className="text-2xl font-black text-white">Подбор завершён</h2>
                <p className="text-gray-500 text-sm">Рекомендуемый пакет техники для вашего проекта</p>
              </div>
            </div>

            {/* Savings banner */}
            {savings > 0 && (
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
                <Zap size={20} className="text-emerald-400 shrink-0" />
                <div>
                  <div className="text-sm font-bold text-emerald-400">
                    Экономия пакетного предложения: {new Intl.NumberFormat('ru-RU').format(savings)} ₽
                  </div>
                  <div className="text-xs text-gray-500">
                    По сравнению с раздельной арендой ({new Intl.NumberFormat('ru-RU').format(individualPrice)} ₽)
                  </div>
                </div>
              </div>
            )}

            {/* Equipment list */}
            <div className="space-y-4 mb-6">
              {recommendations.map((rec) => {
                const removed = removedIds.includes(rec.equipment.id)
                return (
                  <div
                    key={rec.equipment.id}
                    className={`bg-gray-900 border rounded-xl overflow-hidden transition-all ${
                      removed ? 'border-gray-800/30 opacity-50' : 'border-gray-700/50'
                    }`}
                  >
                    <div className="flex gap-0">
                      <div className="w-32 shrink-0">
                        <img
                          src={rec.equipment.image}
                          alt={rec.equipment.name}
                          className="w-full h-full object-cover"
                          style={{ minHeight: '100px' }}
                        />
                      </div>
                      <div className="p-4 flex-1 flex flex-col justify-between">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h3 className="font-bold text-gray-100 text-sm">{rec.equipment.name}</h3>
                            <p className="text-xs text-amber-400/80 mt-1 leading-relaxed">{rec.reason}</p>
                          </div>
                          <button
                            onClick={() => setRemovedIds((ids) =>
                              removed ? ids.filter((id) => id !== rec.equipment.id) : [...ids, rec.equipment.id]
                            )}
                            className={`shrink-0 p-1.5 rounded-lg transition-all cursor-pointer ${
                              removed
                                ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                                : 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                            }`}
                          >
                            {removed ? <Check size={14} /> : <X size={14} />}
                          </button>
                        </div>
                        <div className="flex items-center justify-between mt-3">
                          <span className="text-xs text-gray-500">{rec.days} дней</span>
                          <span className="font-bold text-amber-400">
                            {new Intl.NumberFormat('ru-RU').format(rec.subtotal)} ₽
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Total */}
            <div className="bg-gray-900 border border-amber-500/20 rounded-xl p-5 mb-6">
              <div className="flex justify-between items-center mb-2">
                <span className="text-gray-400">Единиц техники:</span>
                <span className="font-bold text-gray-200">{activeRecs.length}</span>
              </div>
              <div className="flex justify-between items-center mb-4">
                <span className="text-gray-400">Итоговая стоимость пакета:</span>
                <span className="text-2xl font-black text-amber-400">
                  {new Intl.NumberFormat('ru-RU').format(totalPackagePrice)} ₽
                </span>
              </div>
              <Button className="w-full gap-2 text-base" onClick={handleBookPackage}>
                <ShoppingCart size={18} />
                Забронировать весь пакет
              </Button>
            </div>

            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => { setStep(1); setRemovedIds([]); setWizardData({ projectType: '', area: '', volume: '', startDate: '', endDate: '', terrain: '', access: '', budget: '' }) }}>
                Начать заново
              </Button>
              <Button variant="secondary" onClick={() => navigate('/catalog')} className="flex-1">
                Смотреть весь каталог
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

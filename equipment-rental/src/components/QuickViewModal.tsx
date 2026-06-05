import React from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Star, MapPin, ShoppingCart } from 'lucide-react'
import { equipmentData } from '../data/equipment'
import { useQuickViewStore } from '../store/quickViewStore'
import { useCartStore } from '../store/cartStore'
import { Badge, statusLabels } from './ui/Badge'
import { Button } from './ui/Button'

function formatPrice(p: number) {
  return new Intl.NumberFormat('ru-RU').format(p)
}

export const QuickViewModal: React.FC = () => {
  const { equipmentId, close } = useQuickViewStore()
  const { addItem, items } = useCartStore()

  const equipment = equipmentId ? equipmentData.find((e) => e.id === equipmentId) : null

  const today = new Date()
  const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
  const startDate = today.toISOString().split('T')[0]
  const endDate = nextWeek.toISOString().split('T')[0]

  const isInCart = equipment ? items.some((i) => i.equipment.id === equipment.id) : false

  const handleAddToCart = () => {
    if (!equipment || equipment.availability !== 'available' || isInCart) return
    addItem(equipment, startDate, endDate)
  }

  return (
    <AnimatePresence>
      {equipment && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={close}
          />

          {/* Modal */}
          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4"
          >
            <div
              className="bg-[#111111] border border-white/10 rounded-2xl overflow-hidden w-full max-w-2xl pointer-events-auto shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-white/8">
                <span className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                  Быстрый просмотр
                </span>
                <button
                  onClick={close}
                  className="w-8 h-8 flex items-center justify-center rounded-full text-gray-500 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Content */}
              <div className="flex flex-col sm:flex-row">
                {/* Image */}
                <div className="sm:w-52 shrink-0 relative">
                  <img
                    src={equipment.image}
                    alt={equipment.name}
                    className="w-full h-48 sm:h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent sm:bg-gradient-to-r" />
                </div>

                {/* Info */}
                <div className="flex-1 p-5">
                  <div className="flex items-start gap-2 mb-3">
                    <h2 className="text-lg font-black text-white flex-1">{equipment.name}</h2>
                    <Badge variant={equipment.availability as 'available' | 'rented' | 'maintenance'}>
                      {statusLabels[equipment.availability]}
                    </Badge>
                  </div>

                  {/* Rating + location */}
                  <div className="flex items-center gap-3 mb-4 flex-wrap">
                    <div className="flex items-center gap-1">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Star
                          key={i}
                          size={12}
                          className={i < Math.floor(equipment.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-700'}
                        />
                      ))}
                      <span className="text-xs text-gray-400 ml-1 font-medium">{equipment.rating.toFixed(1)}</span>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-gray-500">
                      <MapPin size={11} />
                      {equipment.location}
                    </div>
                  </div>

                  {/* Key specs */}
                  <div className="grid grid-cols-2 gap-2 mb-4">
                    {Object.entries(equipment.specs).slice(0, 4).map(([key, value]) => (
                      <div key={key} className="bg-[#1A1A1A] rounded-md px-2.5 py-2 border border-white/4">
                        <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">{key}</div>
                        <div className="text-xs font-medium text-gray-300">{value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Price */}
                  <div className="flex items-end justify-between mb-4">
                    <div>
                      <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">от</div>
                      <div className="text-2xl font-black text-amber-400">
                        {formatPrice(equipment.pricePerDay)}
                        <span className="text-xs text-gray-500 font-normal ml-1">₽/день</span>
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-600">
                      <div>{formatPrice(equipment.pricePerWeek)} ₽/нед</div>
                      <div>{formatPrice(equipment.pricePerMonth)} ₽/мес</div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2">
                    <Link to={`/catalog/${equipment.id}`} onClick={close} className="flex-1">
                      <Button variant="secondary" size="sm" className="w-full text-xs gap-1.5">
                        Подробнее
                      </Button>
                    </Link>
                    <Button
                      variant="primary"
                      size="sm"
                      className="flex-1 text-xs gap-1.5"
                      onClick={handleAddToCart}
                      disabled={equipment.availability !== 'available' || isInCart}
                    >
                      <ShoppingCart size={13} />
                      {isInCart ? 'В корзине' : 'В корзину'}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Star, MapPin, ShoppingCart, Eye, Zap, ArrowUpRight } from 'lucide-react'
import { motion } from 'framer-motion'
import { Equipment } from '../types'
import { Badge, statusLabels } from './ui/Badge'
import { Button } from './ui/Button'
import { useCartStore } from '../store/cartStore'

interface EquipmentCardProps {
  equipment: Equipment
  index?: number
}

function formatPrice(price: number): string {
  return new Intl.NumberFormat('ru-RU').format(price)
}

export const EquipmentCard: React.FC<EquipmentCardProps> = ({ equipment, index = 0 }) => {
  const { addItem, items } = useCartStore()
  const isInCart = items.some((i) => i.equipment.id === equipment.id)
  const [imgError, setImgError] = useState(false)

  const today = new Date()
  const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
  const startDate = today.toISOString().split('T')[0]
  const endDate = nextWeek.toISOString().split('T')[0]

  const handleAddToCart = (e: React.MouseEvent) => {
    e.preventDefault()
    if (!isInCart && equipment.availability === 'available') {
      addItem(equipment, startDate, endDate)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 32 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06, ease: "easeOut" }}
      whileHover={{ y: -5, transition: { duration: 0.2 } }}
      className="group relative bg-[#111111] border border-white/6 rounded-xl overflow-hidden"
      style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.4)' }}
    >
      {/* Image */}
      <div className="relative overflow-hidden h-52">
        {!imgError ? (
          <motion.img
            src={equipment.image}
            alt={equipment.name}
            className="w-full h-full object-cover"
            whileHover={{ scale: 1.07 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full bg-[#1A1A1A] flex items-center justify-center">
            <div className="text-center">
              <div className="text-5xl mb-2 opacity-20">🏗</div>
              <span className="text-xs text-gray-700">{equipment.category}</span>
            </div>
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

        {/* Hover overlay */}
        <motion.div
          className="absolute inset-0 bg-amber-500/0 flex items-center justify-center"
          whileHover={{ backgroundColor: 'rgba(245,158,11,0.08)' }}
          transition={{ duration: 0.2 }}
        >
          <Link to={`/catalog/${equipment.id}`}>
            <motion.div
              className="bg-black/60 backdrop-blur-sm border border-white/20 rounded-full p-3 opacity-0 group-hover:opacity-100 transition-opacity"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.95 }}
            >
              <ArrowUpRight size={20} className="text-white" />
            </motion.div>
          </Link>
        </motion.div>

        {/* Category badge */}
        <div className="absolute top-3 left-3">
          <span className="bg-black/70 backdrop-blur-sm text-amber-400 text-xs font-semibold px-2.5 py-1 rounded-md border border-amber-500/30 uppercase tracking-wide">
            {equipment.category}
          </span>
        </div>

        {/* Availability */}
        <div className="absolute top-3 right-3">
          <Badge variant={equipment.availability as 'available' | 'rented' | 'maintenance'}>
            {statusLabels[equipment.availability]}
          </Badge>
        </div>

        {/* Power on hover */}
        {equipment.power && (
          <div className="absolute bottom-3 right-3 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-1 group-hover:translate-y-0">
            <span className="flex items-center gap-1 bg-black/70 backdrop-blur-sm text-amber-300 text-xs font-medium px-2 py-1 rounded-md">
              <Zap size={10} />
              {equipment.power}
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-100 mb-2 line-clamp-2 group-hover:text-amber-300 transition-colors duration-200 leading-snug">
          {equipment.name}
        </h3>

        <div className="flex items-center gap-1 mb-3">
          <MapPin size={11} className="text-gray-600 shrink-0" />
          <span className="text-xs text-gray-600 truncate">{equipment.location}</span>
        </div>

        {/* Rating */}
        <div className="flex items-center gap-1.5 mb-3">
          <div className="flex items-center gap-0.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Star
                key={i}
                size={11}
                className={i < Math.floor(equipment.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-700'}
              />
            ))}
          </div>
          <span className="text-xs text-gray-400 font-medium">{equipment.rating.toFixed(1)}</span>
          <span className="text-xs text-gray-600">({equipment.reviewCount})</span>
        </div>

        {/* Specs */}
        <div className="grid grid-cols-2 gap-1.5 mb-4">
          {Object.entries(equipment.specs).slice(0, 2).map(([key, value]) => (
            <div key={key} className="bg-[#1A1A1A] rounded-md px-2.5 py-1.5 border border-white/4">
              <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">{key}</div>
              <div className="text-xs font-medium text-gray-300 truncate">{value}</div>
            </div>
          ))}
        </div>

        {/* Price */}
        <div className="flex items-end justify-between mb-4 pb-4 border-b border-white/6">
          <div>
            <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">от</div>
            <div className="text-2xl font-black text-amber-400 leading-none">
              {formatPrice(equipment.pricePerDay)}
              <span className="text-xs text-gray-500 font-normal ml-1">₽/день</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-600">{formatPrice(equipment.pricePerWeek)} ₽/нед</div>
            <div className="text-xs text-gray-600">{formatPrice(equipment.pricePerMonth)} ₽/мес</div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Link to={`/catalog/${equipment.id}`} className="flex-1">
            <motion.div whileTap={{ scale: 0.97 }}>
              <Button variant="secondary" size="sm" className="w-full gap-1.5 text-xs">
                <Eye size={13} />
                Подробнее
              </Button>
            </motion.div>
          </Link>
          <motion.div className="flex-1" whileTap={{ scale: 0.97 }}>
            <Button
              variant="primary"
              size="sm"
              className="w-full gap-1.5 text-xs"
              onClick={handleAddToCart}
              disabled={equipment.availability !== 'available' || isInCart}
            >
              <ShoppingCart size={13} />
              {isInCart ? 'В корзине' : 'В корзину'}
            </Button>
          </motion.div>
        </div>
      </div>
    </motion.div>
  )
}

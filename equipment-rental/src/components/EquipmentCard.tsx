import React from 'react'
import { Link } from 'react-router-dom'
import { Star, MapPin, ShoppingCart, Eye } from 'lucide-react'
import { Equipment } from '../types'
import { Badge, statusLabels } from './ui/Badge'
import { Button } from './ui/Button'
import { useCartStore } from '../store/cartStore'

interface EquipmentCardProps {
  equipment: Equipment
}

function formatPrice(price: number): string {
  return new Intl.NumberFormat('ru-RU').format(price)
}

export const EquipmentCard: React.FC<EquipmentCardProps> = ({ equipment }) => {
  const { addItem, items } = useCartStore()
  const isInCart = items.some((i) => i.equipment.id === equipment.id)

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
    <div className="group relative bg-gray-900 border border-gray-700/50 rounded-xl overflow-hidden transition-all duration-300 hover:border-amber-500/40 hover:shadow-[0_0_20px_rgba(245,158,11,0.1),0_8px_32px_rgba(0,0,0,0.4)] hover:-translate-y-1">
      {/* Image */}
      <div className="relative overflow-hidden h-52">
        <img
          src={equipment.image}
          alt={equipment.name}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-gray-900/80 via-transparent to-transparent" />

        {/* Category badge */}
        <div className="absolute top-3 left-3">
          <span className="bg-amber-500/90 text-gray-900 text-xs font-bold px-2.5 py-1 rounded-md">
            {equipment.category}
          </span>
        </div>

        {/* Availability badge */}
        <div className="absolute top-3 right-3">
          <Badge variant={equipment.availability as 'available' | 'rented' | 'maintenance'}>
            {statusLabels[equipment.availability]}
          </Badge>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <h3 className="text-base font-semibold text-gray-100 mb-1 line-clamp-2 group-hover:text-amber-400 transition-colors">
          {equipment.name}
        </h3>

        <div className="flex items-center gap-1 mb-3">
          <MapPin size={12} className="text-gray-500 shrink-0" />
          <span className="text-xs text-gray-500 truncate">{equipment.location}</span>
        </div>

        {/* Rating */}
        <div className="flex items-center gap-1.5 mb-3">
          <div className="flex items-center gap-0.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Star
                key={i}
                size={12}
                className={i < Math.floor(equipment.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-600'}
              />
            ))}
          </div>
          <span className="text-xs text-gray-400">{equipment.rating.toFixed(1)}</span>
          <span className="text-xs text-gray-600">({equipment.reviewCount})</span>
        </div>

        {/* Specs preview */}
        <div className="grid grid-cols-2 gap-1.5 mb-4">
          {Object.entries(equipment.specs).slice(0, 2).map(([key, value]) => (
            <div key={key} className="bg-gray-800/60 rounded-md px-2 py-1">
              <div className="text-xs text-gray-500">{key}</div>
              <div className="text-xs font-medium text-gray-300 truncate">{value}</div>
            </div>
          ))}
        </div>

        {/* Price */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs text-gray-500">от</div>
            <div className="text-xl font-bold text-amber-400">
              {formatPrice(equipment.pricePerDay)} <span className="text-sm text-gray-400">₽/день</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-500">{formatPrice(equipment.pricePerWeek)} ₽/нед</div>
            <div className="text-xs text-gray-500">{formatPrice(equipment.pricePerMonth)} ₽/мес</div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Link to={`/catalog/${equipment.id}`} className="flex-1">
            <Button variant="secondary" size="sm" className="w-full gap-1.5">
              <Eye size={14} />
              Подробнее
            </Button>
          </Link>
          <Button
            variant="primary"
            size="sm"
            className="flex-1 gap-1.5"
            onClick={handleAddToCart}
            disabled={equipment.availability !== 'available' || isInCart}
          >
            <ShoppingCart size={14} />
            {isInCart ? 'В корзине' : 'В корзину'}
          </Button>
        </div>
      </div>
    </div>
  )
}

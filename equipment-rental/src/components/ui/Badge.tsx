import React from 'react'

type BadgeVariant = 'available' | 'rented' | 'maintenance' | 'pending' | 'confirmed' | 'active' | 'completed' | 'cancelled' | 'default'

interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  className?: string
}

const variantClasses: Record<BadgeVariant, string> = {
  available: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
  rented: 'bg-red-500/15 text-red-400 border border-red-500/30',
  maintenance: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  pending: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  confirmed: 'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  active: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
  completed: 'bg-gray-500/15 text-gray-400 border border-gray-500/30',
  cancelled: 'bg-red-500/15 text-red-400 border border-red-500/30',
  default: 'bg-gray-700/50 text-gray-300 border border-gray-600/30',
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'default', children, className = '' }) => {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${variantClasses[variant]} ${className}`}>
      {(variant === 'available' || variant === 'active') && (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      )}
      {variant === 'rented' && (
        <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
      )}
      {variant === 'maintenance' && (
        <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
      )}
      {children}
    </span>
  )
}

export const statusLabels: Record<string, string> = {
  available: 'Доступно',
  rented: 'Арендовано',
  maintenance: 'Обслуживание',
  pending: 'Ожидает',
  confirmed: 'Подтверждён',
  active: 'Активный',
  completed: 'Завершён',
  cancelled: 'Отменён',
}

import React, { useEffect } from 'react'
import { PageTransition } from '../components/PageTransition'
import { Link } from 'react-router-dom'
import { Heart } from 'lucide-react'
import { EquipmentCard } from '../components/EquipmentCard'
import { equipmentData } from '../data/equipment'
import { useFavoritesStore } from '../store/favoritesStore'

export const Favorites: React.FC = () => {
  const { ids } = useFavoritesStore()

  const favoriteItems = equipmentData.filter((e) => ids.includes(e.id))

  useEffect(() => {
    document.title = 'Избранное — ТЕХПРОКАТ'
  }, [])

  return (
    <PageTransition>
      <div className="min-h-screen pt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-8">
            <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
              <Heart size={28} className="text-amber-400" />
              Избранное
            </h1>
            {favoriteItems.length > 0 && (
              <p className="text-gray-500">
                Сохранено: <span className="text-amber-400 font-medium">{favoriteItems.length}</span> единиц
              </p>
            )}
          </div>

          {favoriteItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="w-20 h-20 rounded-full bg-amber-500/10 flex items-center justify-center mb-6">
                <Heart size={36} className="text-amber-400/50" />
              </div>
              <h2 className="text-xl font-bold text-gray-300 mb-2">Нет избранной техники</h2>
              <p className="text-gray-600 mb-6 max-w-sm">
                Добавляйте технику в избранное, нажимая на иконку сердца на карточке
              </p>
              <Link
                to="/catalog"
                className="inline-flex items-center gap-2 px-6 py-3 bg-amber-500 text-black font-bold rounded-lg hover:bg-amber-400 transition-colors"
              >
                Перейти в каталог
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
              {favoriteItems.map((eq, i) => (
                <EquipmentCard key={eq.id} equipment={eq} index={i} />
              ))}
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  )
}

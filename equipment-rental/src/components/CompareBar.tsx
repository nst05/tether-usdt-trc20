import React from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { GitCompare, X } from 'lucide-react'
import { useCompareStore } from '../store/compareStore'

export const CompareBar: React.FC = () => {
  const { ids, clear } = useCompareStore()

  return (
    <AnimatePresence>
      {ids.length > 0 && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="fixed bottom-0 left-0 right-0 z-50 bg-[#111111]/96 backdrop-blur-md border-t border-amber-500/20 shadow-2xl"
        >
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center">
                <GitCompare size={16} className="text-amber-400" />
              </div>
              <span className="text-sm text-gray-300 font-medium">
                Выбрано для сравнения:{' '}
                <span className="text-amber-400 font-bold">{ids.length}</span>
                <span className="text-gray-600 text-xs ml-1">(макс. 3)</span>
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={clear}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-all cursor-pointer"
              >
                <X size={12} />
                Очистить
              </button>
              <Link
                to="/compare"
                className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-black text-sm font-bold rounded-lg hover:bg-amber-400 transition-colors"
              >
                <GitCompare size={14} />
                Сравнить ({ids.length})
              </Link>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

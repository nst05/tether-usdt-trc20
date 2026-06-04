import React from 'react'
import { motion } from 'framer-motion'

const variants = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.38} },
  exit:    { opacity: 0, y: -10, transition: { duration: 0.22} },
}

export const PageTransition: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <motion.div variants={variants} initial="initial" animate="animate" exit="exit">
    {children}
  </motion.div>
)

/* Stagger container for lists */
export const staggerContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
}

export const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.45} },
}

export const fadeIn = {
  hidden: { opacity: 0 },
  show:   { opacity: 1, transition: { duration: 0.5 } },
}

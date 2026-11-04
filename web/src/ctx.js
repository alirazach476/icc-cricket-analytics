import { createContext, useContext } from 'react'

export const DashCtx = createContext(null)
export const useDash = () => useContext(DashCtx)

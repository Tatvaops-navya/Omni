import { Toaster } from 'react-hot-toast'
import { useTheme } from '../theme/ThemeProvider'

export default function AppToaster() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <Toaster
      position="top-right"
      toastOptions={{
        style: isDark
          ? {
              background: '#111d35',
              color: '#e2e8f0',
              border: '1px solid rgba(99,102,241,0.3)',
            }
          : {
              background: '#ffffff',
              color: '#1e293b',
              border: '1px solid rgba(226,232,240,0.9)',
              boxShadow: '0 4px 16px rgba(15,23,42,0.08)',
            },
      }}
    />
  )
}

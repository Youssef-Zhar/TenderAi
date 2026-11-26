import { useEffect, useState, type ReactNode } from 'react'
import { ThemeContext, type Theme } from './theme-context'

function getInitialTheme(): Theme {
  try {
    return window.localStorage.getItem('tenderai-theme') === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    document.documentElement.style.colorScheme = theme
    try {
      window.localStorage.setItem('tenderai-theme', theme)
    } catch {
      // The theme still works for the current session when storage is unavailable.
    }
  }, [theme])

  function toggleTheme() {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

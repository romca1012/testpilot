import { ref } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'testpilot-theme'

function themeInitial(): Theme {
  if (typeof document === 'undefined') return 'dark'
  return document.documentElement.classList.contains('light') ? 'light' : 'dark'
}

const theme = ref<Theme>(themeInitial())

function appliquerTheme(nouveauTheme: Theme) {
  theme.value = nouveauTheme
  if (typeof document === 'undefined') return
  const racine = document.documentElement
  racine.classList.toggle('dark', nouveauTheme === 'dark')
  racine.classList.toggle('light', nouveauTheme === 'light')
  racine.style.colorScheme = nouveauTheme
  try { localStorage.setItem(STORAGE_KEY, nouveauTheme) } catch { /* stockage indisponible */ }
}

export function useTheme() {
  return { theme, appliquerTheme }
}


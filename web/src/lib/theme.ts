const THEME_STORAGE = "argus_theme"

export function initTheme(): void {
  const stored = localStorage.getItem(THEME_STORAGE)
  const dark = stored ? stored === "dark" : true // dark by default
  document.documentElement.classList.toggle("dark", dark)
}

export function toggleTheme(): void {
  const dark = !document.documentElement.classList.contains("dark")
  document.documentElement.classList.toggle("dark", dark)
  localStorage.setItem(THEME_STORAGE, dark ? "dark" : "light")
}

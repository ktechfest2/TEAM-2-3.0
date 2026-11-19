import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { DEFAULT_LOCALE, languageByCode, readStoredLocale, storeLocale, type NigerianLanguage } from '@/i18n/languages'
import { translate, type MessageVars } from '@/i18n/messages'

type LocaleContextValue = {
  locale: string
  language: NigerianLanguage
  setLocale: (code: string) => void
  t: (key: string, vars?: MessageVars) => string
}

const fallbackLocale: LocaleContextValue = {
  locale: DEFAULT_LOCALE,
  language: languageByCode(DEFAULT_LOCALE),
  setLocale: () => {},
  t: (key, vars) => translate(DEFAULT_LOCALE, key, vars),
}

const LocaleContext = createContext<LocaleContextValue>(fallbackLocale)

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState(readStoredLocale)

  const setLocale = useCallback((code: string) => {
    setLocaleState(code)
    storeLocale(code)
  }, [])

  const language = languageByCode(locale)

  useEffect(() => {
    document.documentElement.lang = language.htmlLang
    const tag = language.htmlLang.replace('-', '_')
    let el = document.head.querySelector<HTMLMetaElement>('meta[property="og:locale"]')
    if (!el) {
      el = document.createElement('meta')
      el.setAttribute('property', 'og:locale')
      document.head.appendChild(el)
    }
    el.content = tag
  }, [language.htmlLang])

  const t = useCallback((key: string, vars?: MessageVars) => translate(locale, key, vars), [locale])

  const value = useMemo(() => ({ locale, language, setLocale, t }), [locale, language, setLocale, t])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useLocale() {
  return useContext(LocaleContext)
}

export function useT() {
  return useLocale().t
}

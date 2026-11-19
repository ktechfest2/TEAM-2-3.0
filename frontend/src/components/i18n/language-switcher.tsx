import { ChevronDownIcon } from 'lucide-react'
import { NigeriaFlag } from '@/components/i18n/nigeria-flag'
import { offeredLanguages, type NigerianLanguage } from '@/i18n/languages'
import { useLocale } from '@/i18n/locale-provider'

const LANGUAGES = offeredLanguages()

function optionLabel(language: NigerianLanguage) {
  return language.nativeName === language.name ? language.name : `${language.name} (${language.nativeName})`
}

export function LanguageSwitcher() {
  const { locale, language, setLocale, t } = useLocale()

  return (
    <label className="inline-flex h-10 shrink-0 items-center gap-2 rounded-[5px] px-2 text-navy hover:bg-muted">
      <NigeriaFlag />
      {/* Only the visible copy of the selected label sets the width. The select is absolutely positioned over it,
          so its longest option does not add empty space before the menu button. */}
      <span className="relative inline-block">
        <span
          aria-hidden
          className="invisible block max-w-[4.75rem] overflow-hidden pr-5 text-[13px] font-medium whitespace-nowrap sm:max-w-[11rem]"
        >
          {optionLabel(language)}
        </span>
        <select
          aria-label={t('Choose language')}
          value={locale}
          onChange={(event) => setLocale(event.target.value)}
          className="absolute inset-0 h-full w-full appearance-none bg-transparent text-[13px] font-medium text-navy outline-none"
        >
          {LANGUAGES.map((item) => (
            <option key={item.code} value={item.code}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
        <ChevronDownIcon
          className="pointer-events-none absolute top-1/2 right-0 size-3.5 -translate-y-1/2 text-navy/50"
          aria-hidden
        />
      </span>
    </label>
  )
}

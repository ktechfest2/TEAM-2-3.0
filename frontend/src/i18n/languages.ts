export type LanguageRegion =
  | 'Official'
  | 'Nationwide'
  | 'North West'
  | 'North East'
  | 'North Central'
  | 'South West'
  | 'South East'
  | 'South South'

export type NigerianLanguage = {
  code: string
  name: string
  nativeName: string
  region: LanguageRegion
  htmlLang: string
}

export const DEFAULT_LOCALE = 'en'
export const LOCALE_STORAGE_KEY = 'verivote.locale'

export const LANGUAGE_REGIONS: readonly LanguageRegion[] = [
  'Official',
  'Nationwide',
  'North West',
  'North East',
  'North Central',
  'South West',
  'South East',
  'South South',
]

/** Named languages of Nigeria used in civic, broadcast and education lists. */
export const NIGERIAN_LANGUAGES: readonly NigerianLanguage[] = [
  { code: 'en', name: 'English', nativeName: 'English', region: 'Official', htmlLang: 'en-NG' },
  { code: 'pcm', name: 'Nigerian Pidgin', nativeName: 'Naijá', region: 'Nationwide', htmlLang: 'pcm-NG' },
  { code: 'ha', name: 'Hausa', nativeName: 'Hausa', region: 'Nationwide', htmlLang: 'ha-NG' },
  { code: 'yo', name: 'Yoruba', nativeName: 'Yorùbá', region: 'Nationwide', htmlLang: 'yo-NG' },
  { code: 'ig', name: 'Igbo', nativeName: 'Igbo', region: 'Nationwide', htmlLang: 'ig-NG' },
  { code: 'ff', name: 'Fulfulde', nativeName: 'Fulfulde', region: 'Nationwide', htmlLang: 'ff-NG' },
  { code: 'gwn', name: 'Gwandara', nativeName: 'Gwandara', region: 'North West', htmlLang: 'gwn-NG' },
  { code: 'dri', name: "C'Lela", nativeName: 'CʼLela', region: 'North West', htmlLang: 'dri-NG' },
  { code: 'tsw', name: 'Tsishingini', nativeName: 'Tsishingini', region: 'North West', htmlLang: 'tsw-NG' },
  { code: 'kdl', name: 'Tsikimba', nativeName: 'Tsikimba', region: 'North West', htmlLang: 'kdl-NG' },
  { code: 'bzw', name: 'Basa', nativeName: 'Basa', region: 'North West', htmlLang: 'bzw-NG' },
  { code: 'res', name: 'Reshe', nativeName: 'Tsureshe', region: 'North West', htmlLang: 'res-NG' },
  { code: 'dud', name: 'Hun-Saare', nativeName: 'Hun-Saare', region: 'North West', htmlLang: 'dud-NG' },
  { code: 'bba', name: 'Baatonum', nativeName: 'Baatɔnum', region: 'North West', htmlLang: 'bba-NG' },
  { code: 'dje', name: 'Zarma', nativeName: 'Zarma', region: 'North West', htmlLang: 'dje-NG' },
  { code: 'shu', name: 'Shuwa Arabic', nativeName: 'Shuwa', region: 'North West', htmlLang: 'shu-NG' },
  { code: 'kr', name: 'Kanuri', nativeName: 'Kanuri', region: 'North East', htmlLang: 'kr-NG' },
  { code: 'bol', name: 'Bole', nativeName: 'Bòlè', region: 'North East', htmlLang: 'bol-NG' },
  { code: 'kai', name: 'Karekare', nativeName: 'Karekare', region: 'North East', htmlLang: 'kai-NG' },
  { code: 'ngi', name: 'Ngizim', nativeName: 'Ngizim', region: 'North East', htmlLang: 'ngi-NG' },
  { code: 'bde', name: 'Bade', nativeName: 'Bàdè', region: 'North East', htmlLang: 'bde-NG' },
  { code: 'tan', name: 'Tangale', nativeName: 'Tangale', region: 'North East', htmlLang: 'tan-NG' },
  { code: 'mzm', name: 'Mumuye', nativeName: 'Mumuye', region: 'North East', htmlLang: 'mzm-NG' },
  { code: 'bwr', name: 'Bura-Pabir', nativeName: 'Bura', region: 'North East', htmlLang: 'bwr-NG' },
  { code: 'mrt', name: 'Marghi', nativeName: 'Marghi', region: 'North East', htmlLang: 'mrt-NG' },
  { code: 'hig', name: 'Kamwe', nativeName: 'Kamwe', region: 'North East', htmlLang: 'hig-NG' },
  { code: 'kqm', name: 'Huba', nativeName: 'Huba', region: 'North East', htmlLang: 'kqm-NG' },
  { code: 'bcy', name: 'Bacama', nativeName: 'Bacama', region: 'North East', htmlLang: 'bcy-NG' },
  { code: 'lnu', name: 'Longuda', nativeName: 'Longuda', region: 'North East', htmlLang: 'lnu-NG' },
  { code: 'wja', name: 'Waja', nativeName: 'Waja', region: 'North East', htmlLang: 'wja-NG' },
  { code: 'tul', name: 'Tula', nativeName: 'Tula', region: 'North East', htmlLang: 'tul-NG' },
  { code: 'dbd', name: 'Dadiya', nativeName: 'Dadiya', region: 'North East', htmlLang: 'dbd-NG' },
  { code: 'ccg', name: 'Chamba Daka', nativeName: 'Chamba', region: 'North East', htmlLang: 'ccg-NG' },
  { code: 'ndi', name: 'Samba Leko', nativeName: 'Samba Leko', region: 'North East', htmlLang: 'ndi-NG' },
  { code: 'mzk', name: 'Mambila', nativeName: 'Mambila', region: 'North East', htmlLang: 'mzk-NG' },
  { code: 'fli', name: 'Fali', nativeName: 'Fali', region: 'North East', htmlLang: 'fli-NG' },
  { code: 'bta', name: 'Bata', nativeName: 'Bata', region: 'North East', htmlLang: 'bta-NG' },
  { code: 'gde', name: 'Gude', nativeName: 'Gude', region: 'North East', htmlLang: 'gde-NG' },
  { code: 'tiv', name: 'Tiv', nativeName: 'Tiv', region: 'North Central', htmlLang: 'tiv-NG' },
  { code: 'nup', name: 'Nupe', nativeName: 'Nupe', region: 'North Central', htmlLang: 'nup-NG' },
  { code: 'igl', name: 'Igala', nativeName: 'Igala', region: 'North Central', htmlLang: 'igl-NG' },
  { code: 'idu', name: 'Idoma', nativeName: 'Idoma', region: 'North Central', htmlLang: 'idu-NG' },
  { code: 'ige', name: 'Igede', nativeName: 'Igede', region: 'North Central', htmlLang: 'ige-NG' },
  { code: 'igb', name: 'Ebira', nativeName: 'Ebira', region: 'North Central', htmlLang: 'igb-NG' },
  { code: 'gbr', name: 'Gbagyi', nativeName: 'Gbagyi', region: 'North Central', htmlLang: 'gbr-NG' },
  { code: 'gby', name: 'Gbari', nativeName: 'Gbari', region: 'North Central', htmlLang: 'gby-NG' },
  { code: 'juk', name: 'Wapan', nativeName: 'Wapan', region: 'North Central', htmlLang: 'juk-NG' },
  { code: 'jbu', name: 'Jukun Takum', nativeName: 'Jukun', region: 'North Central', htmlLang: 'jbu-NG' },
  { code: 'kub', name: 'Kuteb', nativeName: 'Kuteb', region: 'North Central', htmlLang: 'kub-NG' },
  { code: 'bom', name: 'Berom', nativeName: 'Berom', region: 'North Central', htmlLang: 'bom-NG' },
  { code: 'yer', name: 'Tarok', nativeName: 'Tarok', region: 'North Central', htmlLang: 'yer-NG' },
  { code: 'ank', name: 'Goemai', nativeName: 'Goemai', region: 'North Central', htmlLang: 'ank-NG' },
  { code: 'kwl', name: 'Kofyar', nativeName: 'Kofyar', region: 'North Central', htmlLang: 'kwl-NG' },
  { code: 'ego', name: 'Eggon', nativeName: 'Eggon', region: 'North Central', htmlLang: 'ego-NG' },
  { code: 'mda', name: 'Mada', nativeName: 'Mada', region: 'North Central', htmlLang: 'mda-NG' },
  { code: 'ala', name: 'Alago', nativeName: 'Alago', region: 'North Central', htmlLang: 'ala-NG' },
  { code: 'afo', name: 'Eloyi', nativeName: 'Eloyi', region: 'North Central', htmlLang: 'afo-NG' },
  { code: 'jab', name: 'Hyam', nativeName: 'Hyam', region: 'North Central', htmlLang: 'jab-NG' },
  { code: 'kaj', name: 'Jju', nativeName: 'Jju', region: 'North Central', htmlLang: 'kaj-NG' },
  { code: 'kcg', name: 'Tyap', nativeName: 'Tyap', region: 'North Central', htmlLang: 'kcg-NG' },
  { code: 'kad', name: 'Adara', nativeName: 'Adara', region: 'North Central', htmlLang: 'kad-NG' },
  { code: 'iri', name: 'Irigwe', nativeName: 'Irigwe', region: 'North Central', htmlLang: 'iri-NG' },
  { code: 'izr', name: 'Izere', nativeName: 'Izere', region: 'North Central', htmlLang: 'izr-NG' },
  { code: 'sur', name: 'Mwaghavul', nativeName: 'Mwaghavul', region: 'North Central', htmlLang: 'sur-NG' },
  { code: 'cla', name: 'Ron', nativeName: 'Ron', region: 'North Central', htmlLang: 'cla-NG' },
  { code: 'anc', name: 'Ngas', nativeName: 'Ngas', region: 'North Central', htmlLang: 'anc-NG' },
  { code: 'yes', name: 'Yeskwa', nativeName: 'Yeskwa', region: 'North Central', htmlLang: 'yes-NG' },
  { code: 'nin', name: 'Ninzo', nativeName: 'Ninzo', region: 'North Central', htmlLang: 'nin-NG' },
  { code: 'ged', name: 'Gade', nativeName: 'Gade', region: 'North Central', htmlLang: 'ged-NG' },
  { code: 'its', name: 'Itsekiri', nativeName: 'Ìtsẹkírì', region: 'South West', htmlLang: 'its-NG' },
  { code: 'ikw', name: 'Ikwere', nativeName: 'Ikwere', region: 'South East', htmlLang: 'ikw-NG' },
  { code: 'ekp', name: 'Ekpeye', nativeName: 'Ekpeye', region: 'South East', htmlLang: 'ekp-NG' },
  { code: 'ogc', name: 'Ogba', nativeName: 'Ogba', region: 'South East', htmlLang: 'ogc-NG' },
  { code: 'ibb', name: 'Ibibio', nativeName: 'Ibibio', region: 'South South', htmlLang: 'ibb-NG' },
  { code: 'anw', name: 'Anaang', nativeName: 'Anaang', region: 'South South', htmlLang: 'anw-NG' },
  { code: 'efi', name: 'Efik', nativeName: 'Efik', region: 'South South', htmlLang: 'efi-NG' },
  { code: 'bin', name: 'Edo', nativeName: 'Ẹ̀dó', region: 'South South', htmlLang: 'bin-NG' },
  { code: 'ish', name: 'Esan', nativeName: 'Esan', region: 'South South', htmlLang: 'ish-NG' },
  { code: 'ets', name: 'Yekhee', nativeName: 'Yekhee', region: 'South South', htmlLang: 'ets-NG' },
  { code: 'ijc', name: 'Izon', nativeName: 'Ịzọn', region: 'South South', htmlLang: 'ijc-NG' },
  { code: 'ijn', name: 'Kalabari', nativeName: 'Kalabari', region: 'South South', htmlLang: 'ijn-NG' },
  { code: 'nms', name: 'Nembe', nativeName: 'Nembe', region: 'South South', htmlLang: 'nms-NG' },
  { code: 'okr', name: 'Kirike', nativeName: 'Kirike', region: 'South South', htmlLang: 'okr-NG' },
  { code: 'urh', name: 'Urhobo', nativeName: 'Urhobo', region: 'South South', htmlLang: 'urh-NG' },
  { code: 'iso', name: 'Isoko', nativeName: 'Isoko', region: 'South South', htmlLang: 'iso-NG' },
  { code: 'iby', name: 'Ibani', nativeName: 'Ibani', region: 'South South', htmlLang: 'iby-NG' },
  { code: 'ogo', name: 'Khana', nativeName: 'Khana', region: 'South South', htmlLang: 'ogo-NG' },
  { code: 'gkn', name: 'Gokana', nativeName: 'Gokana', region: 'South South', htmlLang: 'gkn-NG' },
  { code: 'elm', name: 'Eleme', nativeName: 'Eleme', region: 'South South', htmlLang: 'elm-NG' },
  { code: 'ogb', name: 'Ogbia', nativeName: 'Ogbia', region: 'South South', htmlLang: 'ogb-NG' },
  { code: 'abn', name: 'Abua', nativeName: 'Abua', region: 'South South', htmlLang: 'abn-NG' },
  { code: 'ann', name: 'Obolo', nativeName: 'Obolo', region: 'South South', htmlLang: 'ann-NG' },
  { code: 'epi', name: 'Epie', nativeName: 'Epie', region: 'South South', htmlLang: 'epi-NG' },
  { code: 'enn', name: 'Engenni', nativeName: 'Engenni', region: 'South South', htmlLang: 'enn-NG' },
  { code: 'odu', name: 'Odual', nativeName: 'Odual', region: 'South South', htmlLang: 'odu-NG' },
  { code: 'yaj', name: 'Yala', nativeName: 'Yala', region: 'South South', htmlLang: 'yaj-NG' },
  { code: 'bkv', name: 'Bekwarra', nativeName: 'Bekwarra', region: 'South South', htmlLang: 'bkv-NG' },
  { code: 'bky', name: 'Bokyi', nativeName: 'Bokyi', region: 'South South', htmlLang: 'bky-NG' },
  { code: 'etu', name: 'Ejagham', nativeName: 'Ejagham', region: 'South South', htmlLang: 'etu-NG' },
]

const LANGUAGE_BY_CODE = new Map(NIGERIAN_LANGUAGES.map((language) => [language.code, language]))

export const UI_LOCALES = ['en', 'pcm', 'ha', 'yo', 'ig', 'ff', 'kr', 'tiv', 'ibb', 'bin'] as const

/**
 * Languages offered in the switcher. English is the language of official notices.
 * Hausa, Igbo and Yoruba are the three largest. Nigerian Pidgin is the one people
 * use across regions. The longer catalogue is not offered: choosing it would show
 * another language's words and look translated when it is not.
 */
export const OFFERED_LOCALES = ['en', 'ha', 'ig', 'yo', 'pcm'] as const

export function offeredLanguages(): NigerianLanguage[] {
  return OFFERED_LOCALES.map((code) => languageByCode(code))
}

export function isLocaleCode(value: string): boolean {
  return LANGUAGE_BY_CODE.has(value)
}

export function languageByCode(code: string): NigerianLanguage {
  return LANGUAGE_BY_CODE.get(code) ?? LANGUAGE_BY_CODE.get(DEFAULT_LOCALE)!
}

export function readStoredLocale(): string {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored && (OFFERED_LOCALES as readonly string[]).includes(stored)) return stored
  } catch {
    /* private mode */
  }
  return DEFAULT_LOCALE
}

export function storeLocale(code: string) {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, code)
  } catch {
    /* private mode */
  }
}

import { lang, setLang } from '../i18n'

/** हिंदी / English switch for the retailer screens (large tap target). */
export function LanguageToggle() {
  return (
    <button type="button" onClick={() => setLang(lang === 'hi' ? 'en' : 'hi')} lang={lang === 'hi' ? 'en' : 'hi'}
      aria-label={lang === 'hi' ? 'Switch to English' : 'हिंदी में देखें'}
      className="min-h-11 rounded-lg px-3 text-sm font-bold text-leaf-700 ring-1 ring-gray-300 hover:bg-gray-50">
      {lang === 'hi' ? 'English' : 'हिंदी'}
    </button>
  )
}

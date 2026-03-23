import React, { createContext, useContext, useState, useCallback } from 'react';
import { translations, LANGUAGES } from '../i18n';

const I18nContext = createContext(null);

function detectBrowserLang() {
  const nav = navigator.language || navigator.languages?.[0] || 'en';
  const code = nav.split('-')[0].toLowerCase();
  if (translations[code]) return code;
  return 'en';
}

export const I18nProvider = ({ children }) => {
  const [lang, setLang] = useState(() => {
    const saved = localStorage.getItem('5812_lang');
    if (saved && translations[saved]) return saved;
    return detectBrowserLang();
  });

  const changeLang = useCallback((code) => {
    if (translations[code]) {
      setLang(code);
      localStorage.setItem('5812_lang', code);
    }
  }, []);

  const t = useCallback((path) => {
    const keys = path.split('.');
    let val = translations[lang];
    for (const k of keys) {
      if (!val || typeof val !== 'object') return path;
      val = val[k];
    }
    if (typeof val === 'string') return val;
    // Fallback to English
    let fallback = translations.en;
    for (const k of keys) {
      if (!fallback || typeof fallback !== 'object') return path;
      fallback = fallback[k];
    }
    return typeof fallback === 'string' ? fallback : path;
  }, [lang]);

  return (
    <I18nContext.Provider value={{ lang, changeLang, t, languages: LANGUAGES }}>
      {children}
    </I18nContext.Provider>
  );
};

export const useI18n = () => {
  const ctx = useContext(I18nContext);
  if (!ctx) return { lang: 'en', changeLang: () => {}, t: (k) => k, languages: LANGUAGES };
  return ctx;
};

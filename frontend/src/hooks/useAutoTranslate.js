import { useEffect, useState } from 'react';
import { useI18n } from '../context/I18nContext';
import api from '../services/api';

// Runtime translation for any English string on screen.
//
// Hand-keying thousands of labels into seven JSON files is the slow road, and
// until it is finished the language switcher appears to do nothing. So: ask for
// a batch of strings, serve whatever the backend has already cached (it caches
// in Mongo, so each phrase is translated once for the whole organisation), and
// keep English until an answer arrives. Static keys in src/i18n/*.json still
// win where they exist — use `t()` for those.
const memory = new Map();         // `${lang}|${text}` -> translated
const inflight = new Set();

export const useAutoTranslate = (texts) => {
  const { lang } = useI18n();
  const list = Array.from(new Set((texts || []).filter(t => typeof t === 'string' && t.trim())));
  const [, bump] = useState(0);

  useEffect(() => {
    if (!lang || lang === 'en' || list.length === 0) return;
    const missing = list.filter(t => !memory.has(`${lang}|${t}`) && !inflight.has(`${lang}|${t}`));
    if (missing.length === 0) return;
    missing.forEach(t => inflight.add(`${lang}|${t}`));
    let cancelled = false;
    (async () => {
      try {
        // the API caps a batch, so send in slices
        for (let i = 0; i < missing.length; i += 40) {
          const slice = missing.slice(i, i + 40);
          const res = await api.post('/translate', { lang, texts: slice });
          Object.entries(res.data?.translations || {}).forEach(([src, out]) => {
            memory.set(`${lang}|${src}`, out);
          });
        }
      } catch {
        // leave the English in place — a failed translation must not blank a screen
      } finally {
        missing.forEach(t => inflight.delete(`${lang}|${t}`));
        if (!cancelled) bump(n => n + 1);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, list.join('\u0001')]);

  return (text) => {
    if (!lang || lang === 'en' || !text) return text;
    return memory.get(`${lang}|${text}`) || text;
  };
};

export default useAutoTranslate;

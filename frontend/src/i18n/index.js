import en from './en.json';
import lg from './lg.json';
import sw from './sw.json';
import es from './es.json';
import th from './th.json';
import ht from './ht.json';
import fr from './fr.json';

export const LANGUAGES = [
  { code: 'en', name: 'English', flag: 'GB' },
  { code: 'lg', name: 'Luganda', flag: 'UG' },
  { code: 'sw', name: 'Kiswahili', flag: 'KE' },
  { code: 'es', name: 'Espanol', flag: 'ES' },
  { code: 'th', name: 'Thai', flag: 'TH' },
  { code: 'ht', name: 'Kreyol Ayisyen', flag: 'HT' },
  { code: 'fr', name: 'Francais', flag: 'FR' },
];

export const translations = { en, lg, sw, es, th, ht, fr };
export default translations;

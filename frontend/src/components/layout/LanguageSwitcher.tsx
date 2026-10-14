import { useId, useRef, useState } from 'react';
import { changeLanguage } from '../../i18n/controller';
import { languages, supportedLanguages } from '../../i18n/languages';
import { useAppTranslation } from '../../i18n/useAppTranslation';

export default function LanguageSwitcher() {
  const { t, locale } = useAppTranslation();
  const id = useId();
  const [failed, setFailed] = useState(false);
  const latestRequest = useRef(0);
  return <div className="max-w-full text-sm">
    <label className="sr-only" htmlFor={id}>{t('common:language')}</label>
    <select id={id} value={locale} className="max-w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-600"
      onChange={(event) => {
        const request = ++latestRequest.current;
        setFailed(false);
        void changeLanguage(event.target.value).then(
          (ok) => { if (request === latestRequest.current) setFailed(!ok); },
          () => { if (request === latestRequest.current) setFailed(true); },
        );
      }}>
      {supportedLanguages.map((language) => <option key={language} value={language} lang={language} dir={languages[language].direction}>{languages[language].nativeName}</option>)}
    </select>
    {failed && <p role="alert">{t('common:languageFailed')}</p>}
  </div>;
}

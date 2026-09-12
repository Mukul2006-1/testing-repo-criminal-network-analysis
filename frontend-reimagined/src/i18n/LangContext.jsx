import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { STRINGS, pick } from "./strings.js";

const LangContext = createContext({ lang: "en", setLang: () => {}, t: () => "" });

const STORAGE_KEY = "argus-lang";

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "hi" ? "hi" : "en";
    } catch {
      return "en";
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // storage unavailable — session-only language
    }
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
  }, [lang]);

  const setLang = useCallback((value) => {
    setLangState(value === "hi" ? "hi" : "en");
  }, []);

  const t = useCallback((key) => pick(key, lang), [lang]);

  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang() {
  return useContext(LangContext);
}

/** Translate a STRINGS key: <T k="nav_overview" /> */
export function T({ k }) {
  const { t } = useLang();
  return <>{t(STRINGS[k])}</>;
}

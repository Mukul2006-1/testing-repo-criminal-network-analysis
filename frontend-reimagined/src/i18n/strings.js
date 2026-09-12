/** UI strings: English + Hindi (Devanagari). Entity data (names, IDs,
 * evidence) is never translated — it is case evidence, not chrome.
 * NOTE: Hindi reviewed for simplicity, not native-checked. Get a native
 * speaker to review before stage use.
 */

export const STRINGS = {
  brand_sub: { en: "Network Intelligence", hi: "नेटवर्क इंटेलिजेंस" },
  demo_only: { en: "Synthetic demo data only", hi: "केवल सिंथेटिक डेमो डेटा" },
  search_entities: { en: "Search entities…", hi: "एंटिटी खोजें…" },
  nav_overview: { en: "Overview", hi: "अवलोकन" },
  nav_network: { en: "Network", hi: "नेटवर्क" },
  nav_atlas: { en: "Atlas", hi: "एटलस" },
  nav_compare: { en: "Rel. check", hi: "संबंध जांच" },
  nav_anomalies: { en: "Anomalies", hi: "विसंगतियां" },
  nav_users: { en: "Users", hi: "उपयोगकर्ता" },
  sign_out: { en: "Sign out", hi: "साइन आउट" },
  triage_note: { en: "Scores are triage signals, not verdicts.", hi: "स्कोर समीक्षा संकेत हैं, निर्णय नहीं।" },
  overview_title: { en: "Overview", hi: "अवलोकन" },
  overview_sub: { en: "Autonomous link analysis and live entity triage.", hi: "स्वचालित लिंक विश्लेषण और लाइव एंटिटी प्राथमिकता।" },
  refresh_scores: { en: "↻ Refresh scores", hi: "↻ स्कोर ताज़ा करें" },
  refreshing: { en: "Refreshing…", hi: "ताज़ा हो रहा है…" },
  kpi_entities: { en: "Entities", hi: "एंटिटी" },
  kpi_relationships: { en: "Relationships (est.)", hi: "संबंध (अनुमानित)" },
  kpi_anomalies: { en: "Anomalies", hi: "विसंगतियां" },
  kpi_communities: { en: "Communities", hi: "समूह" },
  needs_analytics: { en: "Requires an analytics run", hi: "एनालिटिक्स रन आवश्यक" },
  top_entities: { en: "Top structural entities", hi: "शीर्ष संरचनात्मक एंटिटी" },
  ingest_title: { en: "Ingest evidence pipeline", hi: "साक्ष्य अपलोड पाइपलाइन" },
  upload_process: { en: "Upload & process", hi: "अपलोड और प्रोसेस" },
  running: { en: "Running…", hi: "चल रहा है…" },
  network_title: { en: "Network Explorer", hi: "नेटवर्क एक्सप्लोरर" },
  atlas_title: { en: "Entity directory", hi: "एंटिटी निर्देशिका" },
  compare_title: { en: "Relationship check", hi: "संबंध जांच" },
  anomalies_title: { en: "Anomaly dashboard", hi: "विसंगति डैशबोर्ड" },
  users_title: { en: "User administration", hi: "उपयोगकर्ता प्रशासन" },
  profile_title: { en: "Entity profile", hi: "एंटिटी प्रोफ़ाइल" },
  report_title: { en: "Investigation report", hi: "जांच रिपोर्ट" },
  summary_title: { en: "Plain-language summary", hi: "सरल भाषा में सारांश" },
  loading: { en: "Loading…", hi: "लोड हो रहा है…" },
  no_data: { en: "No data yet — ingest evidence first.", hi: "अभी कोई डेटा नहीं — पहले साक्ष्य अपलोड करें।" },
  login_title: { en: "Sign in to your console", hi: "अपने कंसोल में साइन इन करें" },
  login_sub: { en: "Use credentials created by your administrator.", hi: "अपने प्रशासक द्वारा बनाए गए क्रेडेंशियल का उपयोग करें।" },
  email_label: { en: "Work email", hi: "कार्य ईमेल" },
  password_label: { en: "Password", hi: "पासवर्ड" },
  sign_in: { en: "Access Secure Console →", hi: "सुरक्षित कंसोल खोलें →" },
  signing_in: { en: "Signing in…", hi: "साइन इन हो रहा है…" },
  file_label: { en: "File (CSV/JSON/TXT)", hi: "फ़ाइल (CSV/JSON/TXT)" },
  dataset_label: { en: "Dataset type", hi: "डेटासेट प्रकार" },
  explore: { en: "Explore", hi: "एक्सप्लोर करें" },
  check_button: { en: "Check relationship", hi: "संबंध जांचें" },
  checking: { en: "Checking…", hi: "जांच हो रही है…" },
  verdict_high: { en: "Review first", hi: "पहले समीक्षा करें" },
  verdict_mid: { en: "Keep watch", hi: "नज़र रखें" },
  verdict_low: { en: "Routine", hi: "सामान्य" },
};

export function pick(entry, lang) {
  if (!entry) return "";
  if (typeof entry === "string") return entry;
  return entry[lang] || entry.en;
}

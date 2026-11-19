// Turns backend identifiers into text a person can read.

// "monthly_income" -> "Monthly income", "pm_jan_dhan_yojana" -> "Pm jan dhan yojana"
export function humanize(id: string): string {
  const s = id.replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const LANGUAGE_LABELS: Record<string, string> = {
  'en-IN': 'English',
  'hi-IN': 'हिंदी (Hindi)',
  'bn-IN': 'বাংলা (Bengali)',
  'mr-IN': 'मराठी (Marathi)',
  'ta-IN': 'தமிழ் (Tamil)',
  'te-IN': 'తెలుగు (Telugu)',
  'gu-IN': 'ગુજરાતી (Gujarati)',
  'kn-IN': 'ಕನ್ನಡ (Kannada)',
  'ml-IN': 'മലയാളം (Malayalam)',
  'pa-IN': 'ਪੰਜਾਬੀ (Punjabi)',
};

// Label for a select option from the profile schema.
export function optionLabel(option: string): string {
  return LANGUAGE_LABELS[option] ?? humanize(option);
}

// Scheme ids the generic humanize() gets wrong (acronyms).
const SCHEME_NAMES: Record<string, string> = {
  pm_jan_dhan_yojana: 'PM Jan Dhan Yojana',
  pmay_rural_housing_subsidy: 'PMAY Rural Housing',
  pm_mudra_yojana_shishu: 'PM Mudra (Shishu)',
};

export function schemeName(schemeId: string): string {
  return SCHEME_NAMES[schemeId] ?? humanize(schemeId);
}

/**
 * The shipped UI locales. English is the default because the owner asked for
 * it; the others are one dictionary each.
 *
 * `short` is what the header button shows; `native` is how the language names
 * itself; `label` is the English name for people who do not read the script.
 */
export const LOCALES = [
  { code: "en", label: "English", native: "English", short: "EN" },
  { code: "hi", label: "Hindi", native: "हिंदी", short: "HI" },
  { code: "bn", label: "Bengali", native: "বাংলা", short: "BN" },
  { code: "mr", label: "Marathi", native: "मराठी", short: "MR" },
] as const;

export type Locale = (typeof LOCALES)[number]["code"];

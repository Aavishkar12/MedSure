package com.powerbank.medsure.i18n

/** One of the 22 scheduled Indian languages, plus English. */
data class AppLanguage(val code: String, val native: String, val english: String)

val AllLanguages = listOf(
    AppLanguage("en", "English", "English"),
    AppLanguage("hi", "हिन्दी", "Hindi"),
    AppLanguage("ta", "தமிழ்", "Tamil"),
    AppLanguage("te", "తెలుగు", "Telugu"),
    AppLanguage("bn", "বাংলা", "Bengali"),
    AppLanguage("mr", "मराठी", "Marathi"),
    AppLanguage("gu", "ગુજરાતી", "Gujarati"),
    AppLanguage("kn", "ಕನ್ನಡ", "Kannada"),
    AppLanguage("ml", "മലയാളം", "Malayalam"),
    AppLanguage("or", "ଓଡ଼ିଆ", "Odia"),
    AppLanguage("pa", "ਪੰਜਾਬੀ", "Punjabi"),
    AppLanguage("as", "অসমীয়া", "Assamese"),
    AppLanguage("ur", "اردو", "Urdu"),
    AppLanguage("mai", "मैथिली", "Maithili"),
    AppLanguage("sat", "ᱥᱟᱱᱛᱟᱲᱤ", "Santali"),
    AppLanguage("ks", "کٲشُر", "Kashmiri"),
    AppLanguage("ne", "नेपाली", "Nepali"),
    AppLanguage("sd", "سنڌي", "Sindhi"),
    AppLanguage("kok", "कोंकणी", "Konkani"),
    AppLanguage("doi", "डोगरी", "Dogri"),
    AppLanguage("mni", "ꯃꯩꯇꯩꯂꯣꯟ", "Manipuri"),
    AppLanguage("brx", "बड़ो", "Bodo"),
    AppLanguage("sa", "संस्कृतम्", "Sanskrit"),
)

/**
 * Looks up UI copy for the chosen language. English, Tamil and Hindi are fully
 * translated; every other language falls back to English, key by key.
 */
class Tx(private val lang: String?) {
    private val map: Map<String, String> = when (lang) {
        "ta" -> Dict.ta
        "hi" -> Dict.hi
        else -> Dict.en
    }

    operator fun get(key: String): String = map[key] ?: Dict.en[key] ?: key

    val times: List<String> = when (lang) {
        "ta" -> Dict.ta_times
        "hi" -> Dict.hi_times
        else -> Dict.en_times
    }

    val days: List<String> = when (lang) {
        "ta" -> Dict.ta_days
        "hi" -> Dict.hi_days
        else -> Dict.en_days
    }
}

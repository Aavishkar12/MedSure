package com.powerbank.medsure.i18n

/** Strings for the automatic red-alert call. {name} and {n} are replaced in code. */
internal object CallDict {
    val en: Map<String, String> = mapOf(
        "acTitle" to "Calling {name} in {n}",
        "acBody" to "MedSure will phone {name} from this phone so someone can check on you. Tap Cancel if this was a mistake.",
        "acCancel" to "Cancel",
        "acNow" to "Call now",
        "acCancelled" to "Call cancelled",
        "acCancelledBody" to "No call was made. If you need help, call 108.",
        "acRetry" to "Start the call again",
        "acCalled" to "Called {name}",
        "acCalledBody" to "Did {name} pick up? If not, try the next person.",
        "acNext" to "Didn't pick up. Call {name}",
        "acAgain" to "Call {name} again",
        "acNoMore" to "There is no one else to call. Please call 108.",
        "acNoOne" to "No family number saved",
        "acNoOneBody" to "Add a family member with a phone number so MedSure can call them. For now, please call 108.",
        "phoneErr" to "Mobile numbers start with 6, 7, 8 or 9. Enter 10 digits without +91.",
    )
    val ta: Map<String, String> = mapOf(
        "acTitle" to "{n} வினாடிகளில் {name} அவர்களை அழைக்கிறோம்",
        "acBody" to "யாராவது உங்களைப் பார்க்க, இந்த தொலைபேசியிலிருந்து {name} அவர்களை MedSure அழைக்கும். தவறாக இருந்தால் ரத்து செய்யவும்.",
        "acCancel" to "ரத்து செய்",
        "acNow" to "இப்போதே அழை",
        "acCancelled" to "அழைப்பு ரத்து செய்யப்பட்டது",
        "acCancelledBody" to "அழைப்பு செய்யப்படவில்லை. உதவி தேவைப்பட்டால் 108-ஐ அழையுங்கள்.",
        "acRetry" to "மீண்டும் அழைப்பைத் தொடங்கு",
        "acCalled" to "{name} அவர்களை அழைத்தோம்",
        "acCalledBody" to "{name} எடுத்தாரா? இல்லையென்றால் அடுத்தவரை அழையுங்கள்.",
        "acNext" to "எடுக்கவில்லை. {name} அவர்களை அழை",
        "acAgain" to "{name} அவர்களை மீண்டும் அழை",
        "acNoMore" to "அழைக்க வேறு யாரும் இல்லை. 108-ஐ அழையுங்கள்.",
        "acNoOne" to "குடும்ப எண் சேமிக்கப்படவில்லை",
        "acNoOneBody" to "MedSure அழைக்க, தொலைபேசி எண்ணுடன் ஒரு குடும்ப உறுப்பினரைச் சேர்க்கவும். இப்போதைக்கு 108-ஐ அழையுங்கள்.",
        "phoneErr" to "கைப்பேசி எண் 6, 7, 8 அல்லது 9-இல் தொடங்கும். +91 இல்லாமல் 10 இலக்கங்களை உள்ளிடவும்.",
    )
    val hi: Map<String, String> = mapOf(
        "acTitle" to "{n} सेकंड में {name} को कॉल हो रहा है",
        "acBody" to "कोई आपकी खबर ले सके, इसलिए MedSure इस फ़ोन से {name} को कॉल करेगा। गलती हुई हो तो रद्द करें दबाएँ।",
        "acCancel" to "रद्द करें",
        "acNow" to "अभी कॉल करें",
        "acCancelled" to "कॉल रद्द हुआ",
        "acCancelledBody" to "कोई कॉल नहीं किया गया। मदद चाहिए तो 108 पर कॉल करें।",
        "acRetry" to "कॉल फिर शुरू करें",
        "acCalled" to "{name} को कॉल किया",
        "acCalledBody" to "क्या {name} ने फ़ोन उठाया? नहीं तो अगले व्यक्ति को कॉल करें।",
        "acNext" to "फ़ोन नहीं उठाया। {name} को कॉल करें",
        "acAgain" to "{name} को फिर कॉल करें",
        "acNoMore" to "कॉल करने के लिए कोई और नहीं है। कृपया 108 पर कॉल करें।",
        "acNoOne" to "परिवार का नंबर सेव नहीं है",
        "acNoOneBody" to "फ़ोन नंबर के साथ परिवार का सदस्य जोड़ें ताकि MedSure उन्हें कॉल कर सके। अभी के लिए 108 पर कॉल करें।",
        "phoneErr" to "मोबाइल नंबर 6, 7, 8 या 9 से शुरू होता है। +91 के बिना 10 अंक डालें।",
    )
}

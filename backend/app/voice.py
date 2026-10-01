"""Spoken message for the alert call. Deliberately generic: no medical details are read aloud."""
from twilio.twiml.voice_response import Gather, VoiceResponse

# language -> (Twilio <Say> voice, language code, prompt, thanks, goodbye)
# English and Hindi use Amazon Polly Aditi. The Tamil voice name is a best guess: confirm it in your
# Twilio console (Programmability > Voice > Text-to-speech) and edit it here if it differs.
VOICES = {
    "en": ("Polly.Aditi", "en-IN",
           "Urgent. {name}'s check-in shows a red alert. Please call {name} now. Press 1 to confirm you have heard this.",
           "Thank you. We have noted that you are on it.",
           "We did not get your response. We will try another family member."),
    "hi": ("Polly.Aditi", "hi-IN",
           "अत्यावश्यक। {name} की जाँच में लाल चेतावनी आई है। कृपया अभी {name} को फ़ोन करें। सुनने की पुष्टि के लिए 1 दबाएँ।",
           "धन्यवाद। हमने दर्ज कर लिया है कि आप संभाल रहे हैं।",
           "हमें आपका जवाब नहीं मिला। हम परिवार के किसी और सदस्य को फ़ोन करेंगे।"),
    "ta": ("Google.ta-IN-Standard-A", "ta-IN",
           "அவசரம். {name} அவர்களின் பரிசோதனையில் சிவப்பு எச்சரிக்கை வந்துள்ளது. உடனே {name} அவர்களை அழையுங்கள். கேட்டதை உறுதிப்படுத்த 1 அழுத்தவும்.",
           "நன்றி. நீங்கள் கவனித்துக்கொள்கிறீர்கள் என்று பதிவு செய்தோம்.",
           "உங்கள் பதில் கிடைக்கவில்லை. குடும்பத்தில் மற்றொருவரை அழைப்போம்."),
}


def alert_twiml(patient_name: str, language: str, ack_url: str) -> str:
    cfg = VOICES.get(language, VOICES["en"])
    prompt = cfg[2].format(name=patient_name)
    vr = VoiceResponse()
    for _ in range(2):  # ask twice before giving up
        g = Gather(num_digits=1, action=ack_url, method="POST", timeout=8)
        g.say(prompt, voice=cfg[0], language=cfg[1])
        vr.append(g)
    vr.say(cfg[4], voice=cfg[0], language=cfg[1])
    return str(vr)


def thanks_twiml(language: str) -> str:
    cfg = VOICES.get(language, VOICES["en"])
    vr = VoiceResponse()
    vr.say(cfg[3], voice=cfg[0], language=cfg[1])
    return str(vr)

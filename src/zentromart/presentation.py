"""Identity disclosure and speech-only formatting; never invent policy facts."""
from datetime import date
import re


def disclose_ai(reply, language):
    if re.search(r"\bAI\s+(?:support\s+)?assistant\b|एआई.{0,30}असिस्टेंट", reply, re.I):
        return reply
    return {'en': "I'm ZentroMart's AI support assistant. ",
            'hi': 'मैं ZentroMart की एआई सहायता असिस्टेंट हूँ। ',
            'hi-en': 'Main ZentroMart ka AI support assistant hoon. '}[language] + reply


def prepare_speech(text, language):
    text = re.sub(r'\[[^\]\n]+\]', '', text)
    months = ('January February March April May June July August September October November December'.split()
              if language != 'hi' else
              'जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर'.split())
    def spoken_date(match):
        try:
            value = date.fromisoformat(match[0])
        except ValueError:
            return match[0]
        return f'{value.day} {months[value.month - 1]} {value.year}'
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', spoken_date, text)
    text = re.sub(r'(\bOrder\s*(?:(?:ID|number)\s*)?[:#]?\s*|ऑर्डर\s*(?:आईडी\s*)?[:#]?\s*)(\d{8})(?!\d)',
                  lambda m: m[1] + m[2][:4] + ' ' + m[2][4:], text, flags=re.I)
    return text.strip()

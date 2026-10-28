"""Context-aware minimization, not a complete personal-data detector.

Keep public amounts/dates useful while hiding identity values. Proof collection
is hidden as a whole by the UI and never relies on this best-effort helper.
"""

import re


IDENTITY = re.compile(
    r"(?P<label>(?:\b(?:last\s*(?:4|four)\s*(?:digits)?|order(?:\s+(?:id|number))?|phone|mobile|pincode|pin|suffix|verification(?:\s+value)?)\b|फ़ोन|फोन|पिनकोड|आखिरी\s*अंक))"
    r"(?P<gap>[^\d\n]{0,18})(?P<value>\+?\d(?:[\s(),+-]*\d){3,})", re.I)
PUBLIC_FACT = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"(?:(?:\bINR|\bRs\.?|₹)\s*\d[\d,]*(?:\.\d{1,2})?|"
    r"\b\d[\d,]*(?:\.\d{1,2})?\s*(?:rupees|रुपये)\b|"
    r"\b(?:refund\s+amount|amount|price|cost|paid)\s*[:=]?\s*\d[\d,]*(?:\.\d{1,2})?)", re.I)
NUMBERS = re.compile(r"\d(?:[\s(),+-]*\d){3,}")


def minimize(text, *, number="<number omitted>", email="<email omitted>", url="<URL omitted>"):
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", email, text)
    text = re.sub(r"https?://\S+", url, text)
    text = IDENTITY.sub(lambda match: match["label"] + match["gap"] + number, text)
    output, start = [], 0
    for match in PUBLIC_FACT.finditer(text):
        output.extend((NUMBERS.sub(number, text[start:match.start()]), match[0]))
        start = match.end()
    output.append(NUMBERS.sub(number, text[start:]))
    return "".join(output)

"""Reviewed workflow sentences: no private text is sent to a translation service.

Templates preserve opaque facts, commands, dates and money. Unknown sentences
fail closed rather than falsely labeling an English paragraph as Hindi.
"""

import re
from string import Formatter


VERSION = "zentromart-localization-v2"
LANGUAGES = ("en", "hi", "hi-en")
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def choose_language(text, previous="en", preferred=None):
    if preferred is not None:
        if preferred not in LANGUAGES:
            raise ValueError("Choose en, hi, or hi-en")
        return preferred
    if re.search(r"\bhinglish\b", text, re.I):
        return "hi-en"
    if re.search(r"english\s*(?:mein|please)|(?:in|में)\s+english|अंग्रेज़ी", text, re.I):
        return "en"
    if re.search(r"hindi\s*(?:mein|please)|in\s+hindi|[\u0900-\u097f]", text, re.I):
        return "hi"
    if re.search(r"\b(?:mera|meri|mere|mujhe|chahiye|hai|hain|nahi|karo|batao|karna|kya)\b", text, re.I):
        return "hi-en"
    return previous


# English source, Hindi, Hinglish. Each row is one complete rendered sentence.
SENTENCES = (
    ("Hi! I'm ZentroMart's AI support assistant.", "नमस्ते! मैं ZentroMart का AI सपोर्ट सहायक हूँ।", "Hi! Main ZentroMart ka AI support assistant hoon."),
    ("How can I help you today—track an order, check a return, or understand a refund?", "आज कैसे मदद करूँ—ऑर्डर ट्रैक करना है, रिटर्न देखना है या रिफंड समझना है?", "Aaj kaise help karoon—order track karna hai, return check karna hai, ya refund samajhna hai?"),
    ("Hi! To continue with your order, please enter the requested phone suffix or delivery pincode in the verification field.", "नमस्ते! ऑर्डर की मदद जारी रखने के लिए सत्यापन वाले फ़ील्ड में फ़ोन के आखिरी अंक या डिलीवरी पिनकोड भरें।", "Hi! Order ki help jaari rakhne ke liye verification field mein phone ke last digits ya delivery pincode dein."),
    ("You're welcome! Let me know if there's anything else you'd like help with.", "आपका स्वागत है! और कोई मदद चाहिए तो बताइए।", "You're welcome! Aur kisi cheez mein help chahiye toh batayein."),
    ("Of course—I can help you check that.", "ज़रूर—मैं इसे देखने में आपकी मदद कर सकता हूँ।", "Bilkul—main ise check karne mein help kar sakta hoon."),
    ("What's your eight-digit order ID? I'll ask for a quick verification step next.", "आपकी आठ अंकों की ऑर्डर ID क्या है? उसके बाद एक छोटा सत्यापन करेंगे।", "Aapki aath-digit order ID kya hai? Uske baad ek chhota verification step karenge."),
    ("Please keep phone numbers, pincodes and verification values out of public-policy questions.", "सार्वजनिक नीति के सवालों में फ़ोन नंबर, पिनकोड और सत्यापन जानकारी न भेजें।", "Public-policy questions mein phone numbers, pincodes aur verification values mat bhejein."),
    ("Stop using the product immediately.", "उत्पाद का इस्तेमाल तुरंत बंद करें।", "Product ka istemaal turant band karein."),
    ("Human review is required.", "सपोर्ट टीम की समीक्षा ज़रूरी है।", "Support team ka review zaroori hai."),
    ("Ticket writing is disabled; no ticket was created.", "टिकट बनाना बंद है; कोई टिकट नहीं बनाया गया।", "Ticket banana disabled hai; koi ticket nahi bana."),
    ("Human review is required; the session ticket limit was reached.", "टीम की समीक्षा ज़रूरी है; इस सत्र की टिकट सीमा पूरी हो गई है।", "Team review chahiye; session ki ticket limit poori ho gayi hai."),
    ("No new ticket was created.", "कोई नया टिकट नहीं बनाया गया।", "Koi naya ticket nahi bana."),
    ("Human review is needed, but ticket creation could not be confirmed.", "टीम की समीक्षा ज़रूरी है, लेकिन टिकट बनने की पुष्टि नहीं हो सकी।", "Team review chahiye, lekin ticket banne ki pushti nahi ho saki."),
    ("No automatic retry was made.", "अपने आप दोबारा प्रयास नहीं किया गया।", "Apne aap dobara koshish nahi ki gayi."),
    ("Ticket {ticket} is confirmed for human follow-up.", "टीम के फ़ॉलो-अप के लिए टिकट {ticket} बनने की पुष्टि है।", "Team follow-up ke liye ticket {ticket} confirm hai."),
    ("No refund, compensation or cancellation has been approved.", "रिफंड, मुआवज़ा या रद्दीकरण मंज़ूर नहीं किया गया है।", "Koi refund, compensation ya cancellation approve nahi hua hai."),
    ("Verification could not be completed.", "सत्यापन पूरा नहीं हो सका।", "Verification poora nahi ho saka."),
    ("I cannot share order details.", "मैं ऑर्डर की जानकारी साझा नहीं कर सकता।", "Main order ki details share nahi kar sakta."),
    ("Please contact support from your registered phone; general policy help is still available.", "अपने पंजीकृत फ़ोन से सपोर्ट से संपर्क करें; सामान्य नीति की मदद उपलब्ध है।", "Registered phone se support se sampark karein; general policy help abhi bhi mil sakti hai."),
    ("The session verification limit was reached.", "इस सत्र की सत्यापन सीमा पूरी हो गई है।", "Session ki verification limit poori ho gayi hai."),
    ("Please use support from your registered phone.", "अपने पंजीकृत फ़ोन से सपोर्ट से संपर्क करें।", "Registered phone se support se sampark karein."),
    ("Please provide one value: the last four digits of your registered phone OR the six-digit delivery pincode.", "एक जानकारी दें: पंजीकृत फ़ोन के आखिरी चार अंक या डिलीवरी का छह अंकों का पिनकोड।", "Ek value dein: registered phone ke last chaar digits YA delivery ka chhe-digit pincode."),
    ("Do not send the full phone number.", "पूरा फ़ोन नंबर न भेजें।", "Poora phone number mat bhejein."),
    ("Verification failed or could not be completed.", "सत्यापन असफल रहा या पूरा नहीं हो सका।", "Verification fail hua ya poora nahi ho saka."),
    ("No order details can be shared.", "ऑर्डर की जानकारी साझा नहीं की जा सकती।", "Order ki details share nahi ki ja sakti."),
    ("Contact support from your registered phone.", "पंजीकृत फ़ोन से सपोर्ट से संपर्क करें।", "Registered phone se support se sampark karein."),
    ("I could not verify that value.", "इस जानकारी का सत्यापन नहीं हो सका।", "Is value ka verification nahi ho saka."),
    ("You have one retry: provide one four-digit phone suffix or six-digit delivery pincode.", "एक और प्रयास बाकी है: फ़ोन के आखिरी चार अंक या छह अंकों का डिलीवरी पिनकोड दें।", "Ek retry baaki hai: phone ke last chaar digits ya chhe-digit delivery pincode dein."),
    ("Which item line is affected? Use /item LINE QTY; I will not guess between items.", "कौन-सी आइटम लाइन प्रभावित है? /item LINE QTY लिखें; मैं आइटम का अनुमान नहीं लगाऊँगा।", "Kaunsi item line affected hai? /item LINE QTY likhein; main item guess nahi karunga."),
    ("How many hours after delivery was the issue reported, and are photos of the item and packaging available? No claim is approved yet.", "डिलीवरी के कितने घंटे बाद शिकायत हुई और क्या आइटम व पैकेजिंग की तस्वीरें हैं? अभी कोई दावा मंज़ूर नहीं है।", "Delivery ke kitne ghante baad issue report hua, aur item aur packaging ki photos hain? Abhi koi claim approve nahi hai."),
    ("The recorded report was {hours} hours after delivery.", "रिकॉर्ड के अनुसार शिकायत डिलीवरी के {hours} घंटे बाद हुई।", "Record ke mutabik report delivery ke {hours} ghante baad hui."),
    ("It is within the 48-hour reporting window; photos and claim review are still required.", "यह 48 घंटे की शिकायत अवधि में है; तस्वीरें और दावे की समीक्षा फिर भी ज़रूरी हैं।", "Yeh 48-hour reporting window mein hai; photos aur claim review phir bhi zaroori hain."),
    ("It is outside 48 hours; normal return-window or warranty review is needed.", "यह 48 घंटे से बाहर है; सामान्य रिटर्न अवधि या वारंटी की समीक्षा चाहिए।", "Yeh 48 hours ke bahar hai; normal return-window ya warranty review chahiye."),
    ("No refund is approved.", "कोई रिफंड मंज़ूर नहीं है।", "Koi refund approve nahi hai."),
    ("No refund initiation is recorded.", "रिकॉर्ड में रिफंड शुरू होने की जानकारी नहीं है।", "Record mein refund shuru hone ki jaankari nahi hai."),
    ("Return refunds depend on pickup and QC; Plus initiation is at pickup.", "रिटर्न रिफंड पिकअप और गुणवत्ता जाँच पर निर्भर है; Plus में शुरुआत पिकअप पर होती है।", "Return refund pickup aur QC par depend hai; Plus mein initiation pickup par hoti hai."),
    ("COD bank transfers require verified bank details.", "COD बैंक ट्रांसफर के लिए सत्यापित बैंक विवरण चाहिए।", "COD bank transfer ke liye verified bank details chahiye."),
    ("I cannot initiate a refund.", "मैं रिफंड शुरू नहीं कर सकता।", "Main refund initiate nahi kar sakta."),
    ("The recorded refund route needs review; I cannot calculate a reliable deadline from it.", "रिकॉर्ड वाले रिफंड तरीके की समीक्षा चाहिए; इससे भरोसेमंद अंतिम तारीख नहीं निकाल सकता।", "Recorded refund route ka review chahiye; isse reliable deadline nahi nikaal sakta."),
    ("Recorded refund amount: INR {amount}.", "रिकॉर्ड में रिफंड राशि: INR {amount}।", "Recorded refund amount: INR {amount}."),
    ("Refund reference: {rrn}.", "रिफंड संदर्भ: {rrn}।", "Refund reference: {rrn}."),
    ("Completion is recorded on {date}.", "रिकॉर्ड में पूरा होने की तारीख {date} है।", "Record mein completion ki date {date} hai."),
    ("Wallet refunds are instant, within two hours.", "वॉलेट रिफंड तुरंत, दो घंटे के अंदर होता है।", "Wallet refund turant, do ghante ke andar hota hai."),
    ("Only an initiation date is recorded, so I cannot calculate the exact hourly deadline or assert completion.", "सिर्फ शुरुआत की तारीख दर्ज है, इसलिए घंटे की सटीक सीमा या पूरा होने की पुष्टि नहीं कर सकता।", "Sirf initiation date recorded hai; exact hourly deadline ya completion confirm nahi kar sakta."),
    ("The recorded initiation gives an expected window of {start} through {end}.", "दर्ज शुरुआत के आधार पर अपेक्षित अवधि {start} से {end} है।", "Recorded initiation ke hisaab se expected window {start} se {end} hai."),
    ("Business days are Monday-Saturday excluding listed holidays.", "कार्यदिवस सोमवार से शनिवार हैं, सूचीबद्ध छुट्टियों को छोड़कर।", "Business days Monday-Saturday hain, listed holidays ko chhodkar."),
    ("An absent completion field is not proof that the bank has not paid.", "पूरा होने का फ़ील्ड खाली होने से यह साबित नहीं होता कि बैंक ने भुगतान नहीं किया।", "Completion field khaali hone se yeh prove nahi hota ki bank ne payment nahi ki."),
    ("Please select one item line using /item LINE QTY; I will not choose between multiple items.", "एक आइटम लाइन /item LINE QTY से चुनें; मैं कई आइटम में से खुद नहीं चुनूँगा।", "Ek item line /item LINE QTY se chunein; main multiple items mein se khud nahi chununga."),
    ("No delivery date is recorded, so the return window cannot be calculated.", "डिलीवरी तारीख दर्ज नहीं है, इसलिए रिटर्न अवधि नहीं निकाल सकते।", "Delivery date recorded nahi hai, isliye return window calculate nahi ho sakti."),
    ("This category is not returnable for change of mind.", "मन बदलने पर इस श्रेणी का रिटर्न नहीं होता।", "Change of mind ke liye yeh category returnable nahi hai."),
    ("Damage/wrong-item cases use a separate review.", "क्षतिग्रस्त या गलत आइटम के मामलों की अलग समीक्षा होती है।", "Damage ya wrong-item cases ka alag review hota hai."),
    ("The delivery date falls outside supported policy coverage; human review is needed.", "डिलीवरी तारीख समर्थित नीति अवधि से बाहर है; टीम की समीक्षा चाहिए।", "Delivery date supported policy coverage ke bahar hai; team review chahiye."),
    ("This is a damage/wrong-item case; the 48-hour reporting rules and claim review apply, not automatic change-of-mind approval.", "यह क्षति या गलत आइटम का मामला है; 48 घंटे के शिकायत नियम और समीक्षा लागू हैं, अपने आप रिटर्न मंज़ूर नहीं है।", "Yeh damage/wrong-item case hai; 48-hour reporting rules aur claim review lagenge, automatic change-of-mind approval nahi."),
    ("The {days}-calendar-day window ends on {deadline}; it is within the date window when evaluated on {evaluated}.", "{days} कैलेंडर दिनों की अवधि {deadline} को खत्म होती है; {evaluated} को जाँचने पर यह अवधि के अंदर है।", "{days}-calendar-day window {deadline} ko khatam hoti hai; {evaluated} par evaluate karne par yeh window ke andar hai."),
    ("The {days}-calendar-day window ends on {deadline}; it is past the date window when evaluated on {evaluated}.", "{days} कैलेंडर दिनों की अवधि {deadline} को खत्म होती है; {evaluated} को जाँचने पर अवधि बीत चुकी है।", "{days}-calendar-day window {deadline} ko khatam hoti hai; {evaluated} par evaluate karne par window beet chuki hai."),
    ("Item-condition rules still apply.", "आइटम की स्थिति संबंधी नियम फिर भी लागू हैं।", "Item-condition rules phir bhi lagenge."),
    ("For {qty} unit(s), the arithmetic estimate is INR {amount}, including INR {fee} pickup deduction.", "{qty} यूनिट के लिए गणना का अनुमान INR {amount} है, जिसमें INR {fee} पिकअप कटौती शामिल है।", "{qty} unit(s) ka arithmetic estimate INR {amount} hai, jisme INR {fee} pickup deduction hai."),
    ("This is not approval or a payout.", "यह मंज़ूरी या भुगतान नहीं है।", "Yeh approval ya payout nahi hai."),
    ("The refund arithmetic needs human review.", "रिफंड गणना के लिए टीम की समीक्षा चाहिए।", "Refund arithmetic ke liye team review chahiye."),
    ("A selected line, quantity, and clearly classified return reason are required for an estimate; no reason or fee will be guessed.", "अनुमान के लिए चुनी हुई लाइन, मात्रा और स्पष्ट रिटर्न कारण चाहिए; कारण या शुल्क का अनुमान नहीं लगाया जाएगा।", "Estimate ke liye selected line, quantity aur clear return reason chahiye; reason ya fee guess nahi hogi."),
    ("The order is already recorded as cancelled.", "रिकॉर्ड में ऑर्डर पहले से रद्द है।", "Record mein order pehle se cancelled hai."),
    ("This assistant did not cancel it; ask about refunds to check the recorded refund route.", "इस सहायक ने इसे रद्द नहीं किया; दर्ज रिफंड तरीके के लिए रिफंड के बारे में पूछें।", "Is assistant ne cancel nahi kiya; recorded refund route check karne ke liye refund ke baare mein poochhein."),
    ("Please check the chosen grocery slot start time in My Orders.", "My Orders में चुने हुए किराना स्लॉट का शुरू होने का समय देखें।", "My Orders mein chosen grocery slot ka start time check karein."),
    ("It is not recorded, so I cannot confirm whether its two-hour cancellation cutoff passed.", "यह समय दर्ज नहीं है, इसलिए दो घंटे की रद्दीकरण सीमा बीतने की पुष्टि नहीं कर सकता।", "Yeh recorded nahi hai, isliye two-hour cancellation cutoff beetne ki pushti nahi kar sakta."),
    ("The order is recorded as not shipped.", "रिकॉर्ड के अनुसार ऑर्डर अभी शिप नहीं हुआ है।", "Record ke mutabik order abhi ship nahi hua hai."),
    ("Cancel it yourself from My Orders; this assistant cannot cancel it.", "My Orders से खुद रद्द करें; यह सहायक रद्द नहीं कर सकता।", "My Orders se khud cancel karein; yeh assistant cancel nahi kar sakta."),
    ("For a completed prepaid cancellation, refund initiation is immediate.", "प्रीपेड रद्दीकरण पूरा होने पर रिफंड की शुरुआत तुरंत होती है।", "Completed prepaid cancellation par refund initiation turant hoti hai."),
    ("This is COD; no prepaid refund is implied.", "यह COD है; प्रीपेड रिफंड का दावा नहीं किया जा रहा।", "Yeh COD hai; prepaid refund imply nahi hota."),
    ("Selected-line arithmetic estimate: INR {amount}; this is not a cancellation or refund approval.", "चुनी लाइन की गणना का अनुमान: INR {amount}; यह रद्दीकरण या रिफंड मंज़ूरी नहीं है।", "Selected-line arithmetic estimate: INR {amount}; yeh cancellation ya refund approval nahi hai."),
    ("A shipped order cannot be cancelled by the assistant.", "शिप हुआ ऑर्डर सहायक रद्द नहीं कर सकता।", "Shipped order assistant cancel nahi kar sakta."),
    ("Refusal at the door or an eligible return may apply; prepaid refusal refunds wait for warehouse receipt.", "दरवाज़े पर लेने से इनकार या पात्र रिटर्न लागू हो सकता है; प्रीपेड इनकार के रिफंड के लिए वेयरहाउस में सामान पहुँचना ज़रूरी है।", "Door par refusal ya eligible return ho sakta hai; prepaid refusal refund warehouse receipt tak wait karta hai."),
    ("Recorded status: {status}.", "दर्ज स्थिति: {status}।", "Recorded status: {status}."),
    ("Promised date: {date}.", "वादा की गई तारीख: {date}।", "Promised date: {date}."),
    ("No paid Express fee is eligible for a credit.", "क्रेडिट के लिए कोई भुगतान किया गया Express शुल्क पात्र नहीं है।", "Credit ke liye koi paid Express fee eligible nahi hai."),
    ("Wallet credit of INR {amount} is recorded on {date}.", "INR {amount} का वॉलेट क्रेडिट {date} को दर्ज है।", "INR {amount} ka wallet credit {date} ko recorded hai."),
    ("The paid Express fee is covered by the automatic 48-hour wallet-credit rule; I cannot assert it has posted.", "भुगतान किया गया Express शुल्क अपने आप 48 घंटे के वॉलेट-क्रेडिट नियम में आता है; क्रेडिट हो जाने का दावा नहीं कर सकता।", "Paid Express fee automatic 48-hour wallet-credit rule mein hai; credit post hone ka claim nahi kar sakta."),
    ("Late Standard delivery has no compensation under this policy.", "इस नीति में देर से Standard डिलीवरी पर मुआवज़ा नहीं है।", "Is policy mein late Standard delivery par compensation nahi hai."),
    ("Verified order status: {status}.", "सत्यापित ऑर्डर की स्थिति: {status}।", "Verified order status: {status}."),
    ("You can ask about delivery, returns, refunds, cancellation or an item issue.", "आप डिलीवरी, रिटर्न, रिफंड, रद्दीकरण या आइटम की समस्या पूछ सकते हैं।", "Aap delivery, returns, refunds, cancellation ya item issue ke baare mein poochh sakte hain."),
    ("Conversation details cleared.", "बातचीत की जानकारी मिटा दी गई है।", "Conversation ki details clear ho gayi hain."),
    ("Verification attempt limits remain active in this session.", "इस सत्र में सत्यापन प्रयास की सीमाएँ लागू रहेंगी।", "Is session mein verification attempt limits active rahengi."),
    ("Please provide one eight-digit order ID.", "एक आठ अंकों की ऑर्डर ID दें।", "Ek aath-digit order ID dein."),
    ("No order is verified.", "कोई ऑर्डर सत्यापित नहीं है।", "Koi order verified nahi hai."),
    ("Please discuss one SKU at a time, or select an item line after verification.", "एक बार में एक SKU बताएँ या सत्यापन के बाद आइटम लाइन चुनें।", "Ek baar mein ek SKU batayein, ya verification ke baad item line chunein."),
    ("Please provide the eight-digit order ID first.", "पहले आठ अंकों की ऑर्डर ID दें।", "Pehle aath-digit order ID dein."),
    ("Do not send verification proof yet.", "अभी सत्यापन की जानकारी न भेजें।", "Abhi verification proof mat bhejein."),
    ("Verification could not be completed; no specific-order details can be shared.", "सत्यापन पूरा नहीं हुआ; किसी विशेष ऑर्डर की जानकारी नहीं दे सकते।", "Verification poora nahi hua; specific order details share nahi kar sakte."),
    ("Use /policy for general help.", "सामान्य मदद के लिए /policy लिखें।", "General help ke liye /policy use karein."),
    ("Use /reason followed by change_of_mind, damaged, defective, wrong, missing, or expired.", "/reason के बाद change_of_mind, damaged, defective, wrong, missing या expired लिखें।", "/reason ke baad change_of_mind, damaged, defective, wrong, missing ya expired likhein."),
    ("The estimate is conditional, not claim approval.", "अनुमान शर्तों पर निर्भर है, दावे की मंज़ूरी नहीं है।", "Estimate conditional hai, claim approval nahi hai."),
    ("That line or quantity is not valid for this order.", "इस ऑर्डर के लिए वह लाइन या मात्रा मान्य नहीं है।", "Is order ke liye woh line ya quantity valid nahi hai."),
    ("Please use /item LINE QTY.", "कृपया /item LINE QTY लिखें।", "Please /item LINE QTY likhein."),
    ("The mock tool could not complete safely.", "मॉक टूल सुरक्षित तरीके से पूरा नहीं हो सका।", "Mock tool safely complete nahi ho saka."),
    ("No private details or action success can be confirmed.", "निजी जानकारी या कार्रवाई सफल होने की पुष्टि नहीं की जा सकती।", "Private details ya action success confirm nahi kar sakte."),
    ("The verified record does not support a safe calculation for this request.", "सत्यापित रिकॉर्ड इस अनुरोध की सुरक्षित गणना के लिए पर्याप्त नहीं है।", "Verified record is request ki safe calculation ke liye kaafi nahi hai."),
    ("Human review is needed; no amount or action is approved.", "टीम की समीक्षा चाहिए; कोई राशि या कार्रवाई मंज़ूर नहीं है।", "Team review chahiye; koi amount ya action approve nahi hai."),
)


def _compile(row):
    pattern, fields = "", set()
    for literal, name, spec, conversion in Formatter().parse(row[0]):
        pattern += re.escape(literal)
        if name:
            pattern += f"(?P<{name}>[^.\\n]+?)"
            fields.add(name)
    for target in row[1:]:
        if {name for _, name, _, _ in Formatter().parse(target) if name} != fields:
            raise ValueError("Translation placeholders must match")
    return re.compile(pattern), row


COMPILED = tuple(_compile(row) for row in SENTENCES)


def localize(text, language):
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    if language == "en":
        return text
    # Item lists contain only validated line numbers, catalog IDs and quantities.
    if text.startswith("Verified order items: "):
        payload = text.removeprefix("Verified order items: ")
        if not re.fullmatch(r"line [0-9]+: [A-Z]{3}-[0-9]{4}, quantity [0-9]+(?:; line [0-9]+: [A-Z]{3}-[0-9]{4}, quantity [0-9]+)*", payload):
            raise ValueError("Unexpected item-list structure")
        prefix = "सत्यापित ऑर्डर के आइटम: " if language == "hi" else "Verified order ke items: "
        return prefix + payload.replace("line", "लाइन" if language == "hi" else "line").replace("quantity", "मात्रा" if language == "hi" else "quantity")
    output = []
    for sentence in re.split(r"(?<=\.)\s+", text.strip()):
        for pattern, row in COMPILED:
            match = pattern.fullmatch(sentence)
            if match:
                output.append(row[1 if language == "hi" else 2].format(**match.groupdict()))
                break
        else:
            raise ValueError("Missing reviewed workflow translation")
    return " ".join(output)


TRANSLATION_FALLBACK = {
    "hi": "इस उत्तर का सुरक्षित अनुवाद उपलब्ध नहीं है। कृपया English चुनें या सपोर्ट टीम से समीक्षा कराएँ। कोई नई कार्रवाई मंज़ूर नहीं है।",
    "hi-en": "Is reply ka safe translation available nahi hai. Please English chunein ya support team se review karayein. Koi naya action approve nahi hai.",
}

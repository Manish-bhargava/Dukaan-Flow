/**
 * Hindi / English for the retailer screens. Text is written in English in the code and
 * looked up here when the shop has chosen Hindi. Missing entries simply show English.
 * The choice is kept on the phone; changing it reloads the page (instant from the cache).
 */
export type Lang = 'en' | 'hi'
const KEY = 'dukaanflow.lang'

export const lang: Lang = (() => {
  try {
    return localStorage.getItem(KEY) === 'hi' ? 'hi' : 'en'
  } catch {
    return 'en'
  }
})()

if (typeof document !== 'undefined') document.documentElement.lang = lang

export function setLang(next: Lang) {
  localStorage.setItem(KEY, next)
  window.location.reload()
}

/** t('Only {n} left', { n: '5 cases' }) */
export function t(text: string, vars?: Record<string, string | number>): string {
  let out = (lang === 'hi' && HI[text]) || text
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v))
  return out
}

/** Unit / counted words ("case", "product") in the chosen language. */
export function word(w: string, n: number): string {
  if (lang === 'hi') return WORDS_HI[w] ?? w
  return `${w}${n === 1 ? '' : 's'}`
}

const WORDS_HI: Record<string, string> = {
  case: 'पेटी', piece: 'पीस', product: 'प्रोडक्ट', item: 'आइटम', order: 'ऑर्डर', line: 'लाइन',
}

const HI: Record<string, string> = {
  // header, tabs, menu
  Catalogue: 'प्रोडक्ट', Offers: 'ऑफ़र', 'AI Order': 'AI ऑर्डर', 'My orders': 'मेरे ऑर्डर', Cart: 'कार्ट',
  'Credit details': 'क्रेडिट', 'View profile': 'प्रोफ़ाइल', 'Log out': 'लॉग आउट', '{amount} left': '{amount} बाकी',
  // login
  'Log in': 'लॉग इन', 'Mobile number': 'मोबाइल नंबर', 'Send OTP': 'OTP भेजें', '← Back to home': '← होम',
  'Welcome to DukaanFlow': 'DukaanFlow में आपका स्वागत है',
  'Log in with the mobile number registered with your distributor.': 'डिस्ट्रीब्यूटर के पास दर्ज मोबाइल नंबर से लॉग इन करें।',
  Retailer: 'दुकानदार', Staff: 'स्टाफ़', 'Enter a valid 10-digit mobile number.': '10 अंकों का सही मोबाइल नंबर डालें।',
  'Code sent for': 'कोड भेजा गया', 'Change number': 'नंबर बदलें', 'Enter the 6-digit OTP from your email': 'ईमेल पर आया 6 अंकों का OTP डालें',
  'This code is no longer valid': 'यह कोड अब मान्य नहीं है', 'Code expires in {time}': 'कोड {time} में ख़त्म होगा',
  'Resend in {n}s': '{n} सेकंड में दोबारा भेजें', 'Resend OTP': 'OTP दोबारा भेजें', 'Verify & log in': 'जाँचें और लॉग इन करें',
  'Didn’t get it? Check your spam folder. A new code replaces the old one.': 'नहीं मिला? स्पैम फ़ोल्डर देखें। नया कोड पुराने की जगह लेता है।',
  'Please wait…': 'कृपया रुकें…',
  // catalogue
  Products: 'प्रोडक्ट', 'Search by name or SKU': 'नाम या SKU से खोजें', All: 'सभी', 'Loading products…': 'प्रोडक्ट लोड हो रहे हैं…',
  'No products found': 'कोई प्रोडक्ट नहीं मिला', 'Try another search or category.': 'दूसरा नाम या कैटेगरी चुनें।',
  'No products are priced for your shop yet.': 'आपकी दुकान के लिए अभी कोई रेट नहीं है।',
  'Load more ({n} more)': 'और दिखाएँ ({n} और)', 'Offers & Schemes': 'ऑफ़र और स्कीम', 'See all offers': 'सभी ऑफ़र देखें',
  'Last order': 'पिछला ऑर्डर', 'Repeat this order': 'यही ऑर्डर दोबारा करें', 'View cart': 'कार्ट देखें',
  'View details': 'पूरी जानकारी', Add: 'जोड़ें', 'Out of stock': 'स्टॉक में नहीं', 'Only {n} left': 'सिर्फ़ {n} बचे',
  '{n} in stock': '{n} स्टॉक में', '{name}: view details': '{name}: पूरी जानकारी',
  // prices
  'incl. {rate}% GST': '{rate}% GST सहित', '+ {rate}% GST': '+ {rate}% GST अलग से',
  'GST {rate}% (treatment not recorded)': 'GST {rate}%', piece: 'पीस', case: 'पेटी',
  'Buy {min} get {free} free': '{min} {unit} लें, {free} {unit} फ़्री', '{pct}% off on {min}+': '{min}+ {unit} पर {pct}% छूट',
  // cart
  'Your cart is empty': 'कार्ट खाली है', 'Add products from the': 'प्रोडक्ट जोड़ें:', catalogue: 'प्रोडक्ट सूची',
  or: 'या', 'type your order as a message': 'मैसेज लिखकर ऑर्डर करें', 'Empty cart': 'कार्ट खाली करें',
  'Includes items read from your message.': 'आपके मैसेज से पढ़े गए आइटम शामिल हैं।', 'Order summary': 'ऑर्डर का हिसाब',
  'Calculating…': 'हिसाब हो रहा है…', 'Note for the distributor (optional)': 'डिस्ट्रीब्यूटर के लिए नोट (ज़रूरी नहीं)',
  'e.g. Deliver before 10 am': 'जैसे: सुबह 10 बजे से पहले भेजें', 'Place order': 'ऑर्डर भेजें',
  'Prices, schemes and GST are calculated by DukaanFlow and checked again when you place the order. No payment is taken now.':
    'रेट, स्कीम और GST DukaanFlow तय करता है और ऑर्डर भेजते समय फिर से जाँचता है। अभी कोई पेमेंट नहीं लिया जाता।',
  'Some items are not available in the quantity you want. Reduce or remove them to place the order.':
    'कुछ आइटम इतनी मात्रा में उपलब्ध नहीं हैं। ऑर्डर भेजने के लिए मात्रा कम करें या हटाएँ।',
  'Ordering is paused for your shop: {reason}. Please contact your salesman or the distributor.':
    'आपकी दुकान के ऑर्डर अभी रुके हैं: {reason}। कृपया अपने सेल्समैन या डिस्ट्रीब्यूटर से बात करें।',
  'Your credit limit has been reached.': 'आपकी क्रेडिट लिमिट पूरी हो गई है।',
  'This order is more than your available credit.': 'यह ऑर्डर आपके बचे क्रेडिट से ज़्यादा है।',
  'New orders cannot be placed right now.': 'अभी नया ऑर्डर नहीं भेजा जा सकता।',
  'Available credit: {available}. Order total: {total}. Reduce the order to fit, or':
    'बचा क्रेडिट: {available}। ऑर्डर: {total}। ऑर्डर कम करें, या',
  Please: 'कृपया', contact: 'बात करें:', 'your salesman': 'आपके सेल्समैन', 'the distributor’s order desk.': 'डिस्ट्रीब्यूटर का ऑर्डर डेस्क।',
  Remove: 'हटाएँ', Rate: 'रेट', GST: 'GST', Discount: 'छूट', Free: 'फ़्री', 'Scheme applied: {scheme}': 'स्कीम लगी: {scheme}',
  ' · you get {n}': ' · आपको मिलेंगे {n}', 'Only {n} available': 'सिर्फ़ {n} उपलब्ध', ' (free cases count too)': ' (फ़्री पेटी भी गिनी जाती हैं)',
  'Value before discount': 'छूट से पहले', 'Scheme discount': 'स्कीम छूट', 'Taxable value': 'टैक्स योग्य राशि',
  'Order total': 'कुल ऑर्डर',
  // orders
  'Under review': 'जाँच में', 'Credit hold': 'क्रेडिट रोक', 'On hold': 'रुका हुआ', 'Needs clarification': 'जानकारी चाहिए',
  Confirmed: 'कन्फ़र्म', Rejected: 'रद्द', 'From catalogue': 'प्रोडक्ट सूची से', 'From message (AI)': 'मैसेज से (AI)',
  'By your salesman': 'आपके सेल्समैन से', '← My orders': '← मेरे ऑर्डर', 'Placed {date}': '{date} को भेजा',
  ' · from your message': ' · आपके मैसेज से', 'Your note: {note}': 'आपका नोट: {note}', Total: 'कुल',
  'Adds these items to your cart at today’s prices and schemes.': 'ये आइटम आज के रेट और स्कीम पर कार्ट में जुड़ेंगे।',
  'Order placed and confirmed. Its amount has been added to your outstanding credit.':
    'ऑर्डर कन्फ़र्म हो गया। इसकी राशि आपके बकाया में जुड़ गई है।',
  'Order sent to the order desk for review. Its amount is held from your credit until they accept or reject it.':
    'ऑर्डर जाँच के लिए भेज दिया गया है। मंज़ूर या रद्द होने तक इसकी राशि आपके क्रेडिट से रोकी गई है।',
  'Under review: the order desk has received this order but has not accepted it yet.':
    'जाँच में: ऑर्डर डेस्क को ऑर्डर मिल गया है, अभी मंज़ूर नहीं हुआ।',
  'This order is above your available credit. The order desk will review it.': 'यह ऑर्डर आपके बचे क्रेडिट से ज़्यादा है। ऑर्डर डेस्क इसे देखेगा।',
  'On hold: {reason}': 'रुका हुआ: {reason}', 'the order desk will contact you.': 'ऑर्डर डेस्क आपसे संपर्क करेगा।',
  'Confirmed{date}.': 'कन्फ़र्म{date}।', ' on {date}': ' {date} को', 'Rejected: {reason}': 'रद्द: {reason}',
  'The order desk needs a clarification: {question} Please reply to your salesman or the order desk. Your order is kept as you placed it.':
    'ऑर्डर डेस्क को जानकारी चाहिए: {question} कृपया सेल्समैन या ऑर्डर डेस्क को बताएँ। आपका ऑर्डर वैसा ही रखा है।',
  Orders: 'ऑर्डर', 'AI drafts': 'AI ड्राफ़्ट',
  // AI order
  Type: 'लिखें', Photo: 'फ़ोटो', 'Voice note': 'वॉइस नोट',
  'Type your order as you would on WhatsApp, send a photo of your list, or record a voice note, in Hindi, Hinglish or English. Nothing is ordered until you review it.':
    'WhatsApp की तरह ऑर्डर लिखें, लिस्ट की फ़ोटो भेजें या वॉइस नोट बोलें, हिंदी, हिंग्लिश या अंग्रेज़ी में। आपके देखे बिना कोई ऑर्डर नहीं जाता।',
  'Read my order': 'ऑर्डर पढ़ें', 'Reading your order…': 'ऑर्डर पढ़ा जा रहा है…', 'Use example': 'उदाहरण देखें',
  'Take a photo of your handwritten or printed order list.': 'अपनी हाथ से लिखी या छपी ऑर्डर लिस्ट की फ़ोटो लें।',
  'Take or choose a photo': 'फ़ोटो लें या चुनें', 'Reading your photo…': 'फ़ोटो पढ़ी जा रही है…',
  'JPEG, PNG or WebP, up to 5 MB.': 'JPEG, PNG या WebP, 5 MB तक।',
  'Speak your order, e.g. “5 peti chhota biscuit, 2 peti washing powder 1 kilo”.':
    'अपना ऑर्डर बोलें, जैसे “5 पेटी छोटा बिस्किट, 2 पेटी वाशिंग पाउडर 1 किलो”।',
  'Start recording': 'रिकॉर्ड शुरू करें', 'Stop and read my order': 'रोकें और ऑर्डर पढ़ें', 'Listening to your voice note…': 'वॉइस नोट सुना जा रहा है…',
  'From: “{text}”': 'आपने लिखा: “{text}”',
  // profile / credit
  'Credit left': 'बचा क्रेडिट', 'Credit limit': 'क्रेडिट लिमिट', 'Outstanding amount': 'बकाया राशि',
  'Held for orders under review': 'जाँच वाले ऑर्डर के लिए रोका गया', 'Shop details': 'दुकान की जानकारी',
  'Your salesman': 'आपके सेल्समैन', 'Total purchased': 'कुल ख़रीद',
  'Current schemes on products at your prices. Free cases and discounts are applied automatically when you order the qualifying quantity.':
    'आपके रेट पर अभी की स्कीम। तय मात्रा ऑर्डर करने पर फ़्री पेटी और छूट अपने आप लग जाती है।',
  'Loading offers…': 'ऑफ़र लोड हो रहे हैं…', 'No offers right now': 'अभी कोई ऑफ़र नहीं', 'Loading orders…': 'ऑर्डर लोड हो रहे हैं…',
  'No orders yet': 'अभी कोई ऑर्डर नहीं', Repeat: 'दोबारा करें', 'Show more': 'और दिखाएँ',
  'Under review: received by the order desk, not accepted yet. Confirmed: accepted by the order desk. Tap Repeat to order the same products again.':
    'जाँच में: ऑर्डर डेस्क को मिला, अभी मंज़ूर नहीं। कन्फ़र्म: ऑर्डर डेस्क ने मंज़ूर किया। वही सामान फिर मँगाने के लिए "दोबारा करें" दबाएँ।',
  'Drafts from your messages (not sent yet)': 'आपके मैसेज से बने ड्राफ़्ट (अभी भेजे नहीं)', 'Tap to review and send': 'देखकर भेजें', Draft: 'ड्राफ़्ट',
  'Loading product…': 'प्रोडक्ट लोड हो रहा है…', '← Back to catalogue': '← प्रोडक्ट सूची', 'Update cart': 'कार्ट अपडेट करें',
  'Add to cart': 'कार्ट में जोड़ें', '{n} in your cart.': 'कार्ट में {n}।', '{n} already in your cart.': 'कार्ट में पहले से {n}।',
  'My profile': 'मेरी प्रोफ़ाइल', 'Credit limit reached': 'क्रेडिट लिमिट पूरी', 'of your {limit} credit limit': '{limit} की क्रेडिट लिमिट में से',
  'Confirmed orders not paid yet': 'कन्फ़र्म ऑर्डर जिनका पेमेंट बाकी है', 'Comes back if the order desk rejects them': 'ऑर्डर रद्द होने पर वापस मिल जाता है',
  // offers / product
  'Offers & schemes': 'ऑफ़र और स्कीम', '← Catalogue': '← प्रोडक्ट', Brand: 'ब्रांड', 'Pack size': 'पैक', 'Price': 'रेट',
}

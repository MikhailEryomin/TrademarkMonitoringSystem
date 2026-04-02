import string

# Typosquatting (replace) dictionary (QWERTY FUZZING)
QWERTY_MAP = {
    '1': '2q', '2': '1q3w', '3': '2we4r', '4': '3re5t', '5': '4rt6y',
    '6': '5ty7u', '7': '6yu8i', '8': '7ui9o', '9': '8io0p', '0': '9op',
    'q': '12wa', 'w': '23esaq', 'e': '34rdsw', 'r': '45tfde', 't': '56ygfr',
    'y': '67uhgt', 'u': '78ijhy', 'i': '89okju', 'o': '90plki', 'p': '0ol',
    'a': 'qwsz', 's': 'wedxza', 'd': 'erfcxs', 'f': 'rtgvdc', 'g': 'tyhbvf',
    'h': 'yujngb', 'j': 'uikmnh', 'k': 'iolmj', 'l': 'opk',
    'z': 'asx', 'x': 'sdcz', 'c': 'dfvx', 'v': 'fgbc', 'b': 'ghnv',
    'n': 'hjmb', 'm': 'jkn'
}

# Source from APWG
# TLD-squatting
TLDS = [
    'com', 'ru', 'рф', 'su', 'info', 'net', 'live', 'link', 'org', 'xyz', 'me', 'site', 'online'
]

# Homoglyphs squatting
HOMOGLYPHS = {
    'a': ['а'], 'c': ['с'], 'd': ['cl'], 'e': ['е'], 'i': ['і', 'l'], 'o': ['о', '0'], 'p': ['р'], 's': ['ѕ'],
    'x': ['х'], 'y': ['у'],
    'm': ['rn', 'nn'], 'w': ['vv']
}

VALID_CHARS = set(string.ascii_lowercase + string.digits + '-')



# ------------------------------
# Combosquatting word dictionary
# ------------------------------

# Source from WIPO/EUIPO
INDUSTRY_MAPPING = {
    # 9 класс (он огромен), 42 (IT услуги), 38 (Связь)
    'tech': {9, 37, 38, 42},

    # 14 (Часы/Ювелирка) - Rolex, Cartier часто атакуют
    'fashion': {14, 18, 25},

    # 3 - это Chanel, Dior, L'Oreal
    'beauty': {3},

    # Еда и Рестораны
    'food': {29, 30, 31, 32, 43},

    # Авто и Транспорт
    # 39 (Перевозки/Аренда) - кейсы типа Uber, Yandex Go
    'auto': {12, 37, 39},

    # Маркетплейсы, магазины (Avito, Ozon, WB...)
    'market': {35},

    # Финансы и Крипта
    # Финтех часто регистрирует и 36 (финансы) и 9/42 (софт)
    # Но для генерации слов лучше оставить жесткую привязку к 36
    'finance': {36},

    # Медицина и Фарма
    'medicine': {5, 10, 44},

    # Netflix, Skillbox, Онлайн-казино
    'media': {41},
}

KEYWORDS = [
    # Source from akamai analysis in 2024
    'support', 'com', 'login', 'help', 'secure', 'www', 'account',
    'app', 'verify', 'service', 'us', 'id', 'jp', 'find', 'online', 'info',
    'update', 'security', 'web', 'maps', 'my', 'alert', 'mail', 'verification',
    'signin', 'auth', 'map', 'services', 'location', 'gift', 'accounts', 'live',
    'track', 'm', 'uk', 'es', 'co', 'supports', 'findmyphone', 'device', 'fr', 'pay',
    'chat', 'inc', 'log', 'fmi', 'i', 'nitro', 'center', 'event',
    # ru-segment (heuristric data or yandex wordstats source)
    'russia', 'msk', 'spb', 'krd', 'ekb', 'samara', 'nn', '77', '78', '23', '96', '63',
    'vhod', 'kabinet', 'online', 'oficialniy', 'kupit', 'zakaz',
    'cena', 'otzyvy', 'moskva', 'spb', 'dostavka', 'oplata',
    'lk', 'bank', 'zaim', 'karta', 'bonus',
    'invest', 'gaz', 'neft', 'shop', 'store', 'market'
]

PARKING_KEYWORDS = [
    "parked domain", "domain owner", "domain is for sale", "buy this domain", "domain name is available",
    "parked free", "godaddy", "dan.com", "sedo", "domain info",
    "domain has been registered", "future home of", "сайт находится в разработке",
    "хостинг", "домен продается", "купить этот домен", "reg.ru", "nic.ru",
    "parking", "under construction", "coming soon"
]

# heuristic data 
INDUSTRY_KEYWORDS = {

    'tech': [
        'support', 'service', 'login', 'account', 'cloud', 'app',
        'dev', 'api', 'tech', 'driver', 'soft', 'download',
        'vpn', 'recovery', 'repair', 'remont', 'secure'
    ],

    'fashion': [
        'outlet', 'sale', 'discount', 'replica', 'fake', 'cheap',
        'boutique', 'style', 'collection', 'shoes', 'bags', 'wear',
        'brand', 'official', 'stock', 'club'
    ],

    'beauty': [
        'cosmetics', 'beauty', 'makeup', 'skin', 'hair', 'parfum',
        'cream', 'lab', 'spa', 'shop', 'store', 'official'
    ],

    'food': [
        'delivery', 'order', 'menu', 'cafe', 'pizza', 'sushi',
        'burger', 'kitchen', 'food', 'eda', 'rest', 'coffee',
        'grill', 'bar', 'bakery'
    ],

    'auto': [
        'auto', 'car', 'drive', 'service', 'motors', 'parts',
        'salon', 'dealer', 'rent', 'taxi', 'remont', 'oil',
        'glass', 'tyres'
    ],

    'finance': [
        'bank', 'login', 'account', 'card', 'pay', 'wallet',
        'crypto', 'invest', 'credit', 'cash', 'money', 'secure',
        'online', 'client', 'app', 'transfer'
    ],

    'medicine': [
        'med', 'clinic', 'doctor', 'health', 'pharmacy', 'apteka',
        'lab', 'test', 'drug', 'pill', 'care', 'help'
    ],

    'media': [
        'play', 'watch', 'stream', 'game', 'bet', 'casino',
        'study', 'course', 'school', 'live', 'video', 'news'
    ],

    'market': [
        'seller', 'partner', 'business', 'kabinet', 'merchant', 'login',
        'delivery', 'dostavka', 'track', 'order', 'pvz', 'post', 'express',
        'pay', 'card', 'refund', 'money', 'cash', 'vozvrat', 'oplata',
        'job', 'work', 'rabota', 'driver', 'courier', 'hr', 'team',
        'promo', 'sale', 'gift', 'bonus', 'prize', 'win', 'free'
    ]
}

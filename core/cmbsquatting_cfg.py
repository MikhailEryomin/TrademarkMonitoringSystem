"""
Словарь строк для комбосквоттинга.
Словари подбираются на основе классов МКТУ для текущего товарного знака (INDUSTRY_KEYWORDS)
Помимо этого есть также универсальный набор слов KEYWORDS.


Что стоит улучшить:
1. Улучшить покрытие классов МКТУ в INDUSTRY_MAPPING

"""

INDUSTRY_MAPPING = {
    'tech': {7, 9, 37, 38, 42},
    'fashion': {18, 25, 35},
    'food': {29, 30, 31, 32, 43},
    'auto': {12, 37},
    'finance': {36},
    'medicine': {5, 10, 44},
    # ...
}


KEYWORDS = [
    'official', 'center', 'centr', 'sale', 'shop', 'promo', 'store', 'online',
    'russia', 'msk', 'spb', 'krd', 'help', 'info', 'pro'
]

INDUSTRY_KEYWORDS = {
    'tech': [
        'repair', 'remont', 'service', 'support', 'helper', 'restore', 
        'recovery', 'updates', 'tech', 'secure', 'galaxy', 'pc', 'mobile'
    ],
    'fashion': [
        'style', 'shoes', 'wear', 'bags', 'outlet', 'collection', 'new', 'brand',
        'clothing', 'clothes', 'fashion', 'trend', 'designer', 'luxury', 'premium',
        'sale', 'discount', 'promo', 'offer', 'clearance', 'stock', 'outlet'
    ],
    'food': [
        'delivery', 'cafe', 'bakery', 'eat', 'menu', 'food', 'eda', 'rest', 'bar', 
        'restaurant', 'pizza', 'burger', 'sushi', 'coffee', 'tea', 'breakfast', 'lunch',
        'dinner', 'supper', 'brunch', 'buffet', 'takeaway', 'takeout'
    ],
    'auto': [
        'auto', 'car', 'dealership', 'test-drive', 'service', 'remont',
        'vehicle', 'cars', 'automobile', 'motors', 'motor', 'driving',
        'new', 'used', 'preowned', 'certified', 'salon', 'showroom'
    ],
    'finance': [
        'bank', 'credit', 'loan', 'invest', 'money', 'pay', 'online',
        'financial', 'finance', 'banking', 'investment', 'savings', 'deposit',
        'mortgage', 'refinance', 'insurance', 'lifeinsurance', 'carinsurance',
        'payment', 'transfer', 'wire', 'remittance', 'exchange', 'currency'
    ],
    'medicine': [
        'clinic', 'doctor', 'med', 'health', 'apteka', 'lab', 'test',
        'medical', 'medicine', 'hospital', 'polyclinic', 'dentist', 'dental',
        'therapy', 'treatment', 'surgery', 'operation', 'rehabilitation',
        'pharmacy', 'drugstore', 'drugs', 'medication', 'prescription'
    ]
}
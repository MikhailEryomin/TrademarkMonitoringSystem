from modules.analyzer import FeatureExtractor

tm_name = 'Adidas'
url = 'https://otzovik.com/reviews/adidas_ru-internet-magazin_sportivnoy_odezhdi_i_obuvi/'
clean_url = url.split('://')[-1].replace('www.', '').split('/')[0]
domain = clean_url.split('.')[0]
extractor = FeatureExtractor()
similatity = extractor._calculate_domain_similarity(tm_name=tm_name, url=url, dom=domain)
print(f"[*] Domain Similarity: tm_name: {tm_name}, url: {url}, domain: {domain}. Similarity: {similatity}")

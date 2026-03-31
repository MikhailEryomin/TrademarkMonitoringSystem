from bs4 import BeautifulSoup
import requests
import re

url = 'https://www.samsungstore.ru'
response = requests.get(url)
response.encoding = 'utf-8'

soup = BeautifulSoup(response.text, 'html.parser')

for element in soup(["script", "style", "nav", "noscript", "svg", "button"]):
    element.extract()

HEAD_LIMIT = 1500
TAIL_LIMIT = 1000

raw_text = soup.get_text(separator=' | ')
full_text = re.sub(r'\s+', ' ', raw_text)
full_text = re.sub(r'(\|\s*)+', '| ', full_text).strip()

title = soup.title.string if soup.title else ""
description_tag = soup.find('meta', attrs={'name': 'description'})
description = description_tag['content'] if description_tag else ""

emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text))
phones = set(re.findall(r'(?:\+7|8)(?:[\s\-\(\)]*\d){10}', full_text))
inn_codes = set(re.findall(r'ИНН\s?:?\s?(\d{10,12})', full_text))

if len(full_text) <= (HEAD_LIMIT + TAIL_LIMIT):
    content_sample = full_text
else:
    head = full_text[:HEAD_LIMIT]
    tail = full_text[-TAIL_LIMIT:]
    content_sample = f"{head}\n\n...\n\n{tail}"

print(f'full_text: {full_text}\n')
print(f'title: {title}\n')
print(f'description: {description}\n')
print(f'emails: {emails}\n')
print(f'phones: {phones}\n')
print(f'inn_codes: {inn_codes}\n')

print(f'content-sample: {content_sample}\n')

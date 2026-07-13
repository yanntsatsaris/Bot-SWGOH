import requests
from bs4 import BeautifulSoup

def test():
    r = requests.get('https://swgoh.gg/characters/')
    soup = BeautifulSoup(r.text, 'html.parser')
    units = soup.find_all('li', class_='media')
    if not units:
        units = soup.find_all('div', class_='collection-char')
    for u in units[:2]:
        print(u.prettify())

test()

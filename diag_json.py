from bs4 import BeautifulSoup

with open('output/post_diag_0.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

target = 'no thoughts just spidey'
for tag in soup.find_all(True):
    if tag.string and target in tag.string:
        if tag.name not in ['script', 'style', 'title']:
            print(f'PARENT 1: {tag.parent.name}, class: {tag.parent.get("class")}')
            print(f'PARENT 2: {tag.parent.parent.name}, class: {tag.parent.parent.get("class")}')
            print('---')

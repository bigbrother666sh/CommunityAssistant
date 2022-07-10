import re

with open('intents.txt', 'r', encoding='utf-8') as f:
    texts = [line for line in f.readlines() if line.strip()]

with open('intents_new.txt', 'w', encoding='utf-8') as f:
    for text in texts:
        print(text)
        _text = re.search(r'-\s.+', text)
        if _text:
            text = _text.group()[2:].strip()
        print(text)
        f.write(text+'\n')

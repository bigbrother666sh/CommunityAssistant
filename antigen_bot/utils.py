"""utils function for AntigenBot"""
from __future__ import annotations


def remove_at_info(text: str) -> str:
    """get the clear message, remove the command prefix and at"""
    split_chars = ['\u2005', '\u0020']
    while text.startswith('@'):
        text = text.strip()
        for char in split_chars:
            tokens = text.split(char)
            if len(tokens) > 1:
                tokens = [token for token in text.split(char) if not token.startswith('@')]
                text = char.join(tokens)
            else:
                text = ''.join(tokens)
    return text

class DFAFilter():
    '''有穷状态机完成'''

    def __init__(self):
        self.keywords_chains={}
        self.delimit='\x00'

    def add(self, keyword):
        keyword=keyword.lower()
        chars=keyword.strip()
        if not chars:
            return

        level = self.keywords_chains
        for i in range(len(chars)):
            if chars[i] in level:
                level = level[chars[i]]

            else:
                if not isinstance(level,dict):
                    break

                for j in range(i,len(chars)):
                    level[chars[j]]={}
                    last_level,last_char=level,chars[j]
                    level=level[chars[j]]

                last_level[last_char] = {self.delimit:0}
                break

        if i == len(chars)-1:
            level[self.delimit]=0

    def parse(self, path="./utils/keywords"):
        with open(path, encoding='utf-8') as f:
            for keyword in f:
                self.add(keyword.strip())

    def filter(self, message):
        message = message.lower()
        start = 0
        while start < len(message):
            res = []
            level = self.keywords_chains
            for char in message[start:]:
                if char in level:
                    if self.delimit not in level[char]:
                        level = level[char]
                        res.append(char)
                    else:
                        res.append(char)
                        return ''.join(res)
            start += 1
        return None

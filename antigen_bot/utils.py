"""
utils function for AntigenBot
还是有点问题，wujingjing原版的也有bug
这一块如果仅是处理@信息是可以的
但是如果是历史引用消息含@，只有在@开头时才行
另外企业微信发出的@信息 貌似自动会把分隔符去掉T……这是微信客户端的问题
"""
#from __future__ import annotations
import re

def remove_at_info(text: str) -> str:
    """get the clear message, remove the command prefix and at"""
    return re.sub(r'@.+?\s', "", text)

if __name__ == "__main__":
    print("====remove at info test====")

    while True:
        print("输入Q退出")
        prompt = input("输入待测文本：")
        if prompt.lower() == "q":
            break
        result = remove_at_info(prompt)
        if result:
            print(result)
        else:
            print("failed")

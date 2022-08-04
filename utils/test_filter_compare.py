from DFAFilter import DFAFilter
from simpleFilter import SimpleFilter
import time

daf = DFAFilter()
daf.parse()
gfw = SimpleFilter()

print("====敏感词测试(filter compare)====")
while True:
    print("输入Q退出")
    prompt = input("输入待测文本：")
    if prompt.lower() == "q":
        break

    time0 = time.time()
    result0 = gfw.filter(prompt)
    print('--Simplefilter--')
    if result0:
        print("检测出敏感词：", result0)
    else:
        print("未查出敏感词")
    time1 = time.time()
    print('总共耗时：' + str(time1 - time0) + 's')

    print(prompt)
    time0 = time.time()
    result1 = daf.filter(prompt)
    print('--DAFfilter--')
    if result1:
        print("检测出敏感词：", result1)
    else:
        print("未查出敏感词")
    time1 = time.time()
    print('总共耗时：' + str(time1 - time0) + 's')
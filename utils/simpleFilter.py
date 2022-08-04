'''
简单校验文本是否直接含有keywords里面的关键词
关键词数据来自：https://github.com/fwwdn/sensitive-stop-words
'''
import os
import logging


class SimpleFilter:
    '''有穷状态机完成'''

    def __init__(self, logs: str = '.utils'):
        # 1. create the cache_dir
        self.cache_dir = logs
        os.makedirs(self.cache_dir, exist_ok=True)

        # 2. save the log info into <plugin_name>.log file
        self.logger = logging.getLogger('DAFFilter')
        self.logger.handlers = []
        self.logger.setLevel('INFO')
        self.logger.propagate = False
        log_file = os.path.join(self.cache_dir, 'simplefilter_LTE.log')

        file_handler = logging.FileHandler(log_file, 'a', encoding='utf-8')
        file_handler.setLevel('INFO')
        self.logger.addHandler(file_handler)

        file = os.path.split(os.path.realpath(__file__))[0]
        path = os.path.join(file, 'keywords')
        with open(path, encoding='utf-8') as f:
            self.keywords = [keyword.lower().strip() for keyword in f]

    def filter(self, message):
        message = message.lower()
        for keyword in self.keywords:
            if keyword in message:
                return keyword
        return None


if __name__ == "__main__":
    import time
    gfw = SimpleFilter()
    print("====敏感词测试(simple filter)====")

    while True:
        print("输入Q退出")
        prompt = input("输入待测文本：")
        if prompt.lower() == "q":
            break
        time1 = time.time()
        result = gfw.filter(prompt)
        if result:
            print("检测出敏感词：", result)
        else:
            print("未查出敏感词")
        time2 = time.time()
        print('总共耗时：' + str(time2 - time1) + 's')

import requests
import os


class DocFAQ:

    def __init__(self, skill_id: str, terminal: str):
        self.skill_id = skill_id
        self.terminal = terminal
        AK, SK = os.environ.get("accesstoken").split('||')
        host = f'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={AK}&client_secret={SK}'
        response = requests.get(host)
        if not response:
            raise Exception('request failed--access token can not be obtained')

        access_token = response.json()
        if "error" in access_token:
            raise Exception('request failed--access token error: %s' % access_token)
        else:
            #print('access token obtain successful: %s' % access_token)
            token = access_token["access_token"]
            self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            self.url = 'https://aip.baidubce.com/rpc/2.0/unit/service/v3/chat?access_token=' + token

    def predict(self, text: str, session_id: str = '') -> dict:
        request_body = ",\"request\":{\"terminal_id\":\"%s\",\"query\":\"%s\"}}" % (self.terminal, text)
        post_data = "{\"version\":\"3.0\",\"skill_ids\":[%s],\"session_id\":\"%s\",\"log_id\":\"7758521\"" % (self.skill_id, session_id) + request_body
        #print(post_data)
        #post_data = "{\"version\":\"3.0\",\"skill_ids\":\"1211404\",\"session_id\":\"\",\"log_id\":\"7758521\",\"request\":{\"terminal_id\":\"88888\",\"query\":\"你好\"}}"
        #print(post_data)
        response = requests.post(self.url, data=post_data.encode(), headers=self.headers)
        if response:
            return response.json()
        else:
            return {}


if __name__ == "__main__":
    import time
    from pprint import pprint
    faq = DocFAQ(skill_id='1211404', terminal='test')

    print("====DocFAQ Test====")
    session_id = ''

    while True:
        prompt = input("请提问（输入Q退出）：")
        if prompt.lower() == "q":
            break

        time0 = time.time()
        result = faq.predict(prompt, session_id)
        if result:
            pprint(result)
        else:
            print("没有结果")
        time1 = time.time()
        print('总共耗时：' + str(time1 - time0) + 's')

        if result['result']['responses'][0]['actions'][0]['action_id'] == 'Innovation_Bot_guide':
            session_id = result['result']['session_id']

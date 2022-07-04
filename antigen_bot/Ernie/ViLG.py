import requests
import json
import time


class ViLG:
    """
    ai.baidu.com/https://ai.baidu.com/ai-doc/wenxin/Il3cbftp9
    Ernie-ViLG
    """
    def __init__(self, access_token: str):
        self.url = "https://wenxin.baidu.com/younger/portal/api/rest/1.0/ernievilg/v1/txt2img/"
        self.access_token = access_token

    def get_response(self, text):
        payload = {
            'access_token': self.access_token,
            'text': text,
            'style': '油画',
            'resolution': 1024
        }
        response = requests.request("POST", self.url, data=payload)
        response_text = json.loads(response.text)
        if response_text["code"]:
            raise RuntimeError(f'generation failed:{response_text["code"]}')

        return response_text["data"]["taskID"]

    def submit_API(self, text):
        task_id = self.get_response(text)

        url = "https://wenxin.baidu.com/younger/portal/api/rest/1.0/ernievilg/v1/getImg"

        payload = {
            'access_token': self.access_token,
            'taskId': task_id
        }

        response = requests.request("POST", url, data=payload)

        response_text = json.loads(response.text)
        if response_text["code"]:
            raise RuntimeError(f'getting img failed:{response_text["code"]}')

        wait_time = int(response_text['data']['waiting'])
        print(f"expect waiting in {wait_time}s")
        time.sleep(wait_time)

        return response_text["data"]["img"]


if __name__ == "__main__":
    print("====Ernie ViLG Test====")
    print("输入access_token")
    access_token = input("access_token：")
    try:
        vilg = ViLG(access_token)
    except:
        print("access_token wrong")
        raise RuntimeError("access_token wrong")

    while (1):
        print("输入Q退出")
        prompt = input("16个字以内文本：")
        if prompt.lower() == "q":
            break
        url = vilg.submit_API(prompt)
        print(url)
        
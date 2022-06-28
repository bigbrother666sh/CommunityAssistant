import json
import os
import re
import time
import xlrd
import random
from typing import Optional
from wechaty import (
    Wechaty,
    FileBox,
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger
from datetime import datetime
from antigen_bot.message_controller import message_controller


class OnCallNoticePlugin(WechatyPlugin):
    """
    功能点：
        1. 侦测"工作群"中或指定联系人的特定格式消息（key_words和楼号数字的任意组合），进行预设通知内容的触发
        2. 应用于"[团购送达](https://github.com/ShanghaiITVolunteer/AntigenWechatBot/issues/25#issuecomment-1104817261)"、
        "[核酸提醒](https://github.com/ShanghaiITVolunteer/AntigenWechatBot/issues/25#issuecomment-1104823018)"等需求场景
        3. 配置文件：.wechaty/on_call_notice.json(存储keyword已经对应的回复文本（必须）、群聊名称pre_fix(必须）、回复媒体（存贮在media/）以及延迟时间）
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None, configs: str = 'CA_configs'):
        super().__init__(options)
        # 1. init the config file
        self.config_url = configs
        self.config_files = os.listdir(self.config_url)

        # 2. save the log info into <plugin_name>.log file
        self.cache_dir = f'./.{self.name}'
        self.file_cache_dir = f'{self.cache_dir}/file'
        os.makedirs(self.file_cache_dir, exist_ok=True)

        log_file = os.path.join(self.cache_dir, 'log.log')
        self.logger = get_logger(self.name, log_file)

        # 3. check and load metadata
        if self._file_check() is False:
            raise RuntimeError('On_call_Notice plugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('CA director.json not valid, pls refer to above info and try again')

        self.data = self._load_message_forwarder_configuration()
        if not self.data:
            raise RuntimeError('CA on_call_notice.xlsx not valid, pls refer to above info and try again')

        if "authorize.json" in self.config_files:
            with open(os.path.join(self.config_url, 'authorize.json'), 'r', encoding='utf-8') as f:
                self.auth = json.load(f)
        else:
            date = datetime.today().strftime('%Y-%m-%d')
            self.auth = {key: {date: []} for key in self.data.keys()}

        self.listen_to_forward = {}   #记录转发状态
        self.last_loop = {}    #记录上一轮发送群名

    async def init_plugin(self, wechaty: Wechaty) -> None:
        message_controller.init_plugins(wechaty)
        return await super().init_plugin(wechaty)

    def _file_check(self) -> bool:
        """check the config file"""
        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

        if "on_call_notice.xlsx" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have on_call_notice.xlsx!')
            return False

    def _load_message_forwarder_configuration(self) -> dict:
        """load the config data"""
        config_file = os.path.join(self.config_url, 'on_call_notice.xlsx')
        data = xlrd.open_workbook(config_file)

        result = {}
        for name in data.sheet_names():
            table = data.sheet_by_name(name)
            nrows = table.nrows
            cols = table.ncols
            if nrows < 3:
                continue

            if cols < 4:
                self.logger.warning('on_call_notice.xlsx format error: information not sufficient')
                return {}

            if table.cell_value(0,0) != "pre_fix":
                self.logger.warning('on_call_notice.xlsx format error: first line first column not pre_fix')
                return {}

            if table.cell_value(1,0) != "keywords":
                self.logger.warning('on_call_notice.xlsx format error: may miss keywords')
                return {}

            result[name] = {"pre_fix": table.cell_value(0, 1)} if table.cell_value(0, 1) else None

            for i in range(2, nrows):
                result[name][table.cell_value(i, 0)] = {}
                result[name][table.cell_value(i, 0)]["reply"] = table.cell_value(i,1) if table.cell_value(i,1) else None
                result[name][table.cell_value(i, 0)]["media"] = table.cell_value(i, 2) if table.cell_value(i, 2) else None
                result[name][table.cell_value(i, 0)]["hold"] = int(table.cell_value(i, 3)) if table.cell_value(i, 3) else 0

        return result

    async def director_message(self, msg: Message):
        """
        Director Module
        """
        # 1. check the heartbeat of WechatyPlugin
        if msg.text() == "ding":
            await msg.say('dong -- OnCallNoticePlugin')
            return
        # 2. help menu
        if msg.text() == 'help':
            await msg.say("OnCallNoticePlugin Director Code: \n"
                          "ding -- check heartbeat \n"
                          "reload configs --- reload on_call_notice.xlsx \n")
            return
        # 3.functions
        if msg.text() == 'reload configs':
            data = self._load_message_forwarder_configuration()
            if data is None:
                await msg.say("on_call_notice.xlsx not valid, I'll keep the old set. no change happened")
            else:
                self.data = data
                await msg.say("on_call_notice configs has been updated")
            return

        await msg.say("send help to me to check what you can do")

    async def forward_message(self, _id, msg: Message, regex):
        """forward the message to the target conversations

        Args:
            msg (Message): the message to forward
            regex (the compile object): the conversation filter
        """
        rooms = await self.bot.Room.find_all()
        random.shuffle(rooms)

        self.last_loop[_id] = []

        if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO, MessageType.MESSAGE_TYPE_ATTACHMENT, MessageType.MESSAGE_TYPE_EMOTICON]:
            file_box = await msg.to_file_box()
            saved_file = os.path.join(self.file_cache_dir, file_box.name)
            await file_box.to_file(saved_file, overwrite=True)
            file_box = FileBox.from_file(saved_file)

            for room in rooms:
                await room.ready()
                topic = room.payload.topic
                if regex.search(topic) and file_box:
                    await room.say(file_box)
                    self.last_loop[_id].append(topic)

        if msg.type() in [MessageType.MESSAGE_TYPE_TEXT, MessageType.MESSAGE_TYPE_URL, MessageType.MESSAGE_TYPE_MINI_PROGRAM]:
            for room in rooms:
                await room.ready()
                topic = room.payload.topic
                if regex.search(topic):
                    await msg.forward(room)
                    self.last_loop[_id].append(topic)

        if msg.type() == MessageType.MESSAGE_TYPE_AUDIO:
            file_box = await msg.to_file_box()
            saved_file = os.path.join(self.file_cache_dir, file_box.name)
            await file_box.to_file(saved_file, overwrite=True)
            new_audio_file = FileBox.from_file(saved_file)
            new_audio_file.metadata = {
                "voiceLength": 2000
            }

            for room in rooms:
                await room.ready()
                topic = room.payload.topic
                if regex.search(topic) and new_audio_file:
                    await room.say(new_audio_file)
                    self.last_loop[_id].append(topic)

        self.logger.info('=================finish to On_call_Notice=================\n\n')

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin":
            return

        talker = msg.talker()
        date = datetime.today().strftime('%Y-%m-%d')

        # 2. check if is director
        if talker.contact_id in self.directors:
            await self.director_message(msg)
            return

        if (talker.contact_id in self.auth.keys()) and ("撤销" in msg.text()) and (await msg.mention_self()):
            if msg.room().room_id in self.auth[talker.contact_id].get(date, []):
                self.auth[talker.contact_id][date].remove(msg.room().room_id)
                with open(os.path.join(self.config_url, 'authorize.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.auth, f)
                await msg.say("本群转发授权已经撤销，如需转发，请管理人员再次授权")
            else:
                await msg.room().say("本群未开启授权，如需授权，请在被授权群中@我并发送 授权", [talker.contact_id])
            return

        if (talker.contact_id in self.auth.keys()) and ("授权" in msg.text()) and (await msg.mention_self()):
            if date in self.auth[talker.contact_id].keys():
                self.auth[talker.contact_id][date].append(msg.room().room_id)
            else:
                self.auth[talker.contact_id][date] = [msg.room().room_id]
            with open(os.path.join(self.config_url, 'authorize.json'), 'w', encoding='utf-8') as f:
                json.dump(self.auth, f)
            await msg.room().say("本群授权已开启，如需撤销，请在本群中@我并发送 撤销", [talker.contact_id])
            await msg.say("本群已授权开启转发，授权期仅限今日（至凌晨12点）。转发请按如下格式： @我 楼号 预设关键词or转发（均用空格隔开）")
            return

        # 如果是转发状态，那么就直接转发
        if talker.contact_id in self.listen_to_forward.keys():
            #群消息要先鉴权
            if msg.room():
                if self.listen_to_forward[talker.contact_id][2] not in self.auth[self.listen_to_forward[talker.contact_id][1]].get(date, []):
                    del self.listen_to_forward[talker.contact_id]
                    await msg.say("呵呵，你的权限刚刚被取消了哦~")
                    return

            message_controller.disable_all_plugins(msg)
            await self.forward_message(talker.contact_id, msg, self.listen_to_forward[talker.contact_id][0])
            if msg.room():
                if self.last_loop.get(talker.contact_id, []):
                    await msg.room().say("已转发，@我并发送查询，查看转发群记录", [talker.contact_id])
                else:
                    await msg.room().say("呵呵，未找到可通知的群，请重试", [talker.contact_id])
            else:
                if self.last_loop.get(talker.contact_id, []):
                    await msg.say("已转发，@我并发送查询，查看转发群记录")
                else:
                    await msg.say("呵呵，未找到可通知的群，请重试")
            del self.listen_to_forward[talker.contact_id]
            return

        # 管理员群发功能
        if talker.contact_id in self.data.keys() and not msg.room() and "群转发" in msg.text():
            pre_fix = self.data[talker.contact_id]['pre_fix']
            if not pre_fix:
                await msg.say("还未配置所属小区，通知未触发")
                return

            regex = re.compile(r"{0}.*".format(pre_fix))
            self.listen_to_forward[talker.contact_id] = [regex, talker.contact_id, talker.contact_id]
            return

        # 3. 判断是否来自工作群或者指定联系人的消息（优先判定群）
        if msg.room():
            if not await msg.mention_self():
                return
            text = await msg.mention_text()
            id = msg.room().room_id
        else:
            text = msg.text()
            id = talker.contact_id

        if text == "查询":
            if self.last_loop.get(talker.contact_id, []):
                for record in self.last_loop[talker.contact_id]:
                    await msg.say(record)
            else:
                await msg.say("未查到对应您的上一轮通知记录")
            return

        token = None
        if id in self.data.keys():
            token = id
        else:
            for key, value in self.auth.items():
                if id in value.get(date, []):
                    token = key
                    break

        if token:
            spec = self.data[token]
        else:
            await msg.say("呵呵，你没有权限哦~")
            return

        words = re.split(r"\s+?", text)

        # 4. 检查msg.text()是否包含关键词
        reply = ""
        file_box = None
        for word in words:
            if word in spec.keys():
                self.logger.info('=================start to On_call_Notice=================')
                await talker.ready()
                self.logger.info('message: %s', msg)

                if not spec[word]['reply']:
                    await msg.say("kewords【{}】未设定转发文本".format(word))
                    return

                if spec[word]["hold"] != 0:
                    await msg.say("收到，等待{0}秒后，按预设【{1}】进行发送".format(spec[word]["hold"], word))
                    time.sleep(spec[word]["hold"])
                else:
                    await msg.say("收到，现在开始按预设【{}】进行发送".format(word))

                reply = spec[word].get("reply")

                if spec[word]["media"]:
                    file_box = FileBox.from_file(self.config_url + "/media/" + spec[word]["media"])
                words.remove(word)

        if (not reply) and ("转发" not in words):
            return

        # 5. 匹配群进行转发
        pre_fix = self.data[token].get('pre_fix')

        if not pre_fix:
            await msg.say("还未配置所属小区，通知未触发")
            return

        words_more = []
        for word in words:
            if re.search(r"\d+[\-:：~\u2014\u2026\uff5e\u3002]{1,2}\d+", word, re.A):
                two_num = re.findall(r"\d+", word, re.A)
                if len(two_num) == 2:
                    try:
                        n, m = int(two_num[0]), int(two_num[1])
                        if n > m:
                            m, n = int(two_num[0]), int(two_num[1])
                        for k in range(n, m):
                            words_more.append(str(k))
                        words_more.append(str(m))
                    except:
                        await msg.say("{0}中所包含的楼栋未成功通知，请按正确指定格式重试".format(word))
                else:
                    await msg.say("{0}中所包含的楼栋未成功通知，请按正确指定格式重试".format(word))

        words.extend(words_more)
        words = set(filter(None, words))

        regex_words = "|".join(words)
        if len(regex_words) == 0:
            await msg.say("呵呵，未找到可通知的群，请重试")
            return
        regex = re.compile(r"{0}.*\D({1})\D.*".format(pre_fix, regex_words))

        if "转发" in words:
            self.listen_to_forward[talker.contact_id] = [regex, token, id]
            #这一步分别存储 转发规则、授权来源和对话号，后二者用于后续鉴权
            return

        rooms = await self.bot.Room.find_all()
        random.shuffle(rooms)

        self.last_loop[talker.contact_id] = []
        for room in rooms:
            await room.ready()
            topic = room.payload.topic
            if regex.search(topic):
                await room.say(reply)
                if file_box:
                    await room.say(file_box)
                self.last_loop[talker.contact_id].append(topic)

        self.logger.info('=================finish to On_call_Notice=================\n')

        if msg.room():
            if self.last_loop.get(talker.contact_id, []):
                await msg.room().say("已转发，@我并发送查询，查看转发群记录", [talker.contact_id])
            else:
                await msg.room().say("呵呵，未找到可通知的群，请重试", [talker.contact_id])
        else:
            if self.last_loop.get(talker.contact_id, []):
                await msg.say("已转发，@我并发送查询，查看转发群记录")
            else:
                await msg.say("呵呵，未找到可通知的群，请重试")

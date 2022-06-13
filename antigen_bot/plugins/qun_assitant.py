import json
import os
import re
import time
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


class QunAssitantPlugin(WechatyPlugin):
    """
    群管助手，功能：
    1、非群主不能更改群名
    2、群内敏感词监测
    3、智能FAQ
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None, configs: str = 'QA_configs'):
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
            raise RuntimeError('QunAssistantPlugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('CA director.json not valid, pls refer to above info and try again')

        if "room_dict.json" in self.config_files:
            with open(os.path.join(self.config_url, 'room_dict.json'), 'r', encoding='utf-8') as f:
                self.room_dict = json.load(f)
        else:
            self.room_dict = {}

        if "qunzhu.json" in self.config_files:
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'r', encoding='utf-8') as f:
                self.qunzhu = json.load(f)
        else:
            self.qunzhu = []

        if "verify_codes.json" in self.config_files:
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'r', encoding='utf-8') as f:
                self.verify_codes = json.load(f)
        else:
            self.verify_codes = []

        if "qun_faq.json" in self.config_files:
            with open(os.path.join(self.config_url, 'qun_faq.json'), 'r', encoding='utf-8') as f:
                self.qun_faq = json.load(f)
        else:
            self.qun_faq = {key:{} for key in self.room_dict.keys()}

        if "qun_open_seq.json" in self.config_files:
            with open(os.path.join(self.config_url, 'qun_open_seq.json'), 'r', encoding='utf-8') as f:
                self.qun_open_seq = json.load(f)
        else:
            self.qun_open_seq = {key:{} for key in self.room_dict.keys()}

    async def init_plugin(self, wechaty: Wechaty) -> None:
        message_controller.init_plugins(wechaty)
        return await super().init_plugin(wechaty)

    def _file_check(self) -> bool:
        """check the config file"""
        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

    async def director_message(self, msg: Message):
        """
        Director Module
        """
        # 1. check the heartbeat of WechatyPlugin
        if msg.text() == "ding":
            await msg.say('dong -- QunAssistantPlugin')
            return
        # 2. help menu
        if msg.text() == 'help':
            await msg.say("QunAssistantPlugin Director Code: \n"
                          "ding -- check heartbeat \n"
                          "start with ### -- add verify code")
            return
        # 3.functions
        if msg.text().startswith("###"):
            self.verify_codes.append(msg.text()[3:])
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'w', encoding='utf-8') as f:
                json.dump(self.verify_codes, f)
            await msg.say(f"new verify code: {msg.text()[3:]} added")
            return

    async def forward_message(self, _id, msg: Message, regex):
        """forward the message to the target conversations

        Args:
            msg (Message): the message to forward
            regex (the compile object): the conversation filter
        """
        rooms = await self.bot.Room.find_all()
        random.shuffle(rooms)

        self.last_loop[_id] = []

        if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO, MessageType.MESSAGE_TYPE_ATTACHMENT]:
            file_box = await msg.to_file_box()
            file_path = self.file_cache_dir
            await file_box.to_file(file_path, overwrite=True)
            file_box = FileBox.from_file(file_path)

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

        self.logger.info('=================finish to On_call_Notice=================\n\n')

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin":
            return

        talker = msg.talker()
        date = datetime.today().strftime('%Y-%m-%d')
        text = msg.text()

        # 2. check if is director
        if talker.contact_id in self.directors:
            await self.director_message(msg)
            return

        # 3. 处理群主消息
        if text in self.verify_codes:
            self.verify_codes.remove(text)
            self.qunzhu.append(contact.contact_id)
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qunzhu, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'w', encoding='utf-8') as f:
                json.dump(self.verify_codes, f, ensure_ascii=False)
            await msg.say("hi，很高兴为您服务，请拉我到需要我协助管理的群内，并@我说：觉醒")
            return

        # 4. 这个模块只处理群消息，且只处理@自己的消息
        if not msg.room() or not await msg.mention_self():
            return

        room = msg.room()
        text = await msg.mention_text()

        if talker.contact_id in self.qunzhu:
            if text == '觉醒':
                self.room_dict[room.room_id] = talker.contact_id
                with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.qunzhu, f, ensure_ascii=False)
                await room.say('大家好，我是AI群助理，接下来由我来为大家服务啦~')
                await topic = room.topic()
                await talker.say(f'您已在{topic}群中激活了AI助理，如需关闭，请@我说：退下')
            if text == '退下':
                del self.room_dict[room.room_id]
                with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.qunzhu, f, ensure_ascii=False)
                await topic = room.topic()
                await talker.say(f'您已在{topic}群中取消了AI助理，如需再次启用，请@我说：觉醒')
            return

        if room.room_id not in self.room_dict.keys():
            return

        owner = await room.owner()

            if room.room_id not in tuan:
                tuan.append(room.room_id)
                topic = await room.topic()
                tuan_detail[room.room_id] = {'topic': topic, "tuanzhang": owner.name, "announce": None, "faq": {},
                                             "track": {}, "members": []}
                # tuan_track[room.room_id] = {'ordered': [], "payed": [], "delivered": [], "received": [], "confirmed": [], "withdraw": [], "returns": [], "refund": []}
                tuan_media[room.room_id] = {"buffer": []}
                tuan_minipro[room.room_id] = {}
                tuan_order[room.room_id] = {"记一下": []}

            if owner.contact_id not in tuanzhang:
                tuanzhang.append(owner.contact_id)

            # 暂时python-wechaty 在这里有bug
            if owner.is_friend():
                await owner.say(pre_words['welcome_tuanzhang'])
            else:
                await xiaoyan.Friendship.add(owner, pre_words['invite_tuanzhang'])

            path = os.getcwd() + f'\material\{room.room_id}'
            if not os.path.exists(path):
                os.mkdir(path)

                # 处理来自团长的消息
            if talker.contact_id == owner.contact_id:
                if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO,
                                  MessageType.MESSAGE_TYPE_ATTACHMENT]:
                    file_box_buffer = await msg.to_file_box()
                    await file_box_buffer.to_file(path + f'\{file_box_buffer.name}')
                    if tuan_order[room.room_id]['记一下']:
                        if (msg.date() - tuan_order[room.room_id]['记一下'][0]).seconds <= 30：  # 指令有效期30s
                        tuan_media[room.room_id][tuan_order[room.room_id]['记一下'][1]].append(
                            path + f'\{file_box_buffer.name}')
                    else:
                        del tuan_order[room.room_id]['记一下']
                        tuan_media[room.room_id]["buffer"].append(path + f'\{file_box_buffer.name}')
                        tuan_media[room.room_id]["buffer_time"] = msg.date()
                else:
                    tuan_media[room.room_id]["buffer"].append(path + f'\{file_box_buffer.name}')
                    tuan_media[room.room_id]["buffer_time"] = msg.date()

            if msg.type() == MessageType.MESSAGE_TYPE_MINI_PROGRAM:
                minipro = await msg.to_mini_program()
                if tuan_order[room.room_id]['记一下']:
                    if (msg.date() - tuan_order[room.room_id]['记一下'][0]).seconds <= 30：  # 指令有效期30s
                    tuan_minipro[room.room_id][tuan_order[room.room_id]['记一下'][1]] = minipro
                    else:
                    del tuan_order[room.room_id]['记一下']
                    tuan_minipro[room.room_id]["buffer"] = minipro
                    tuan_minipro[room.room_id]["buffer_time"] = msg.date()
            else:
                tuan_minipro[room.room_id]["buffer"] = minipro
                tuan_minipro[room.room_id]["buffer_time"] = msg.date()

        if msg.type() == MessageType.MESSAGE_TYPE_URL:
            urlfile = await msg.to_url_link()
            if tuan_order[room.room_id]['记一下']:
                if (msg.date() - tuan_order[room.room_id]['记一下'][0]).seconds <= 30：  # 指令有效期30s
                tuan_media[room.room_id][tuan_order[room.room_id]['记一下'][1]].append(urlfile)
            else:
                del tuan_order[room.room_id]['记一下']
                tuan_media[room.room_id]["buffer"].append(path + f'\{file_box_buffer.name}')
                tuan_media[room.room_id]["buffer_time"] = msg.date()
        else:
            tuan_media[room.room_id]["buffer"].append(path + f'\{file_box_buffer.name}')
            tuan_media[room.room_id]["buffer_time"] = msg.date()

    # 处理引用回复，从中自动提取文本FAQ
        if re.match(r"^「.+」\s-+\s.+", text, re.S):  # 判断是否为引用消息
            quote = re.search(r"：.+」", text, re.S).group()[1:-1]  # 引用内容
            reply = re.search(r"-\n.+", text, re.S).group()[2:]  # 回复内容
            tuan_detail[room.room_id]["faq"][quote] = reply

        if await msg.mention_self():
            text = await msg.mention_text()
            if "记一下" in text:
                tuan_order[room.room_id]['记一下'][0] = msg.date()
                tuan_order[room.room_id]['记一下'][1] = text.replace('记一下', "")
                if tuan_media[room.room_id]["buffer"]:
                    if (msg.date() - tuan_media[room.room_id]["buffer_time"]).seconds <= 30:
                        tuan_media[room.room_id][tuan_order[room.room_id]['记一下'][1]] = tuan_media[room.room_id]["buffer"]
                        tuan_media[room.room_id]["buffer"] = []
                        tuan_order[room.room_id]['记一下'] = []
                    else:
                        tuan_media[room.room_id]["buffer"] = []

    # todo 下面是收款追踪功能，团长在群里@AI+开启xxx收款，统计收款（重复发"开启xx收款"会重置收款，目前一个群同时只会追踪一个收款"
        return

    # 如果群公告改变，则提醒大家注意查收
        announce = await room.announce()
        if announce != tuan_detail[room.room_id]["announce"]:
            await room.say(pre_words["announce"])

    # 检查群成员是否已经将群昵称设为"楼号-门牌号"，如未则提醒，如有则按此更新微信备注（取代昵称）
        alias = await room.alias(talker)
        if alias:
            if alias != await talker.alias():
                try:
                    await talker.alias(alias)
                    print(f"改变{talker.name}的备注成功!")
                except Exception:
                    print(f"改变{talker.name}的备注失败~")
        else:
            await room.say(pre_words['alias_reminder'], [talker.contact_id])

    # 处理mention群主（团长）或者自己的消息
        contact_mention_list = await msg.mention_list()
        if owner in contact_mention_list or await msg.mention_self():
            if msg.type() == MessageType.MESSAGE_TYPE_TEXT:
                text = await msg.mention_text()
            if text:
                questions = tuan_detail[room.room_id]["faq"].keys()
                quotes = []
                if questions:
                    for i in questions:
                        quotes.append(quote)
                    results = module.similarity(questions, quotes], use_gpu = True)
                    results.sort(key=lambda k: (k.get('similarity')), reverse=True)
                    print("top-1 similarity：", results[0]['similarity'])
                    if results[0]['similarity'] > 0.95:
                        if
                    tuan_detail["questions"] == None:
                    tuan_detail["questions"].append(text)
                    tuan_detail["answers"].append(None)
                    if owner.is_friend():
                        await owner.say("团购群【" + tuan_detail[room.room_id]["topic"] + "】中的【" + alias if alias else talker.name + "】提问：【" + text + "】")
                    await owner.say("请在这里直接回复你的答案（文字、图片、链接、小程序等），小助理会自动回复用户，且后续遇到类似问题直接替您回答")
                    else:
                    await xiaoyan.Friendship.add(owner, pre_words['invite_tuanzhang'])
                    else:
                    test_text = []
                    for i in range(0, len(tuan_detail["questions"])):
                        test_text.append(text)
                    results = module.similarity(texts=[tuan_detail["questions"], test_text], use_gpu=True)
                    results.sort(key=lambda k: (k.get('similarity')), reverse=True)
                    print("top-1 similarity：", results[0]['similarity'])
                    if results[0]['similarity'] > 0.9:
                        answer = tuan_detail["answers"][tuan_detail["questions"].index(results[0]['text_1'])]
                    if answer:
                        await room.say(answer)
                    await room.say(pre_words['answer'], [talker.contact_id])
                    else:
                    tuan_detail["questions"].append(text)
                    tuan_detail["answers"].append(None)

                # 提取群内的转账消息追踪记录
                    if msg.type() == MessageType.MESSAGE_TYPE_TRANSFER:  # 先判断消息类型
                        from_id = re.search(r"<payer_username><!\[CDATA\[.+?\]", text).group()[25:-1]  # 取发款人ID
                    receive_id = re.search(r"<receiver_username><!\[CDATA\[.+?\]", text).group()[28:-1]  # 收款人 ID
                    amount = re.search(r"<feedesc><!\[CDATA\[.+?\]", text).group()[18:-1]  # 金额(从feedesc字段取，包含货币符号，不能计算，仅文本）
                    pay_memo = re.search(r"<pay_memo><!\[CDATA\[.+?\]", text).group()[19:-1]  # 转账留言
                    direction = re.search(r"<paysubtype>\d", text).group()[-1]  # 转账方向，从paysubtype字段获取，1为发出，2为接收，4为拒绝，不知道为何没有3，这可能是个藏bug的地方
                if direction == "1":
                    print(from_id + " send" + amount + " to " + receive_id + "and say:" + pay_memo)
                elif direction == "3":
                    print(receive_id + " have received" + amount + " from " + from_id + " .transaction finished.")
                elif direction == "4":
                    print(receive_id + " have rejected" + amount + " from " + from_id + " .transaction abort.")
        return

        if msg.type() == MessageType.MESSAGE_TYPE_CONTACT:
            # 目前contact格式消息没法儿处理，收到此类消息可以让用户把小助手转发给对方，这样也不会造成打扰
            await talker.say('为避免打扰，我不会主动添加用户，如您朋友有使用需求，请可以把我推给ta')

    async def on_room_join(self, room: Room, invitees: List[Contact], inviter: Contact, date: datetime) -> None:
        """handle the event when someone enter the room
        功能描述：
            1. 有人新入群后的操作
            2. 主要是欢迎并提醒ta把群昵称换为楼栋-门牌号
        Args:
            room (Room): the Room object
            invitees (List[Contact]): contacts who are invited into room
            inviter (Contact): inviter
            date (datetime): the time be invited
        """
        if room.room_id not in self.room_dict.keys():
            return

        mentionlist = [contact.contact_id for contact in invitees]
        path = os.getcwd() + '\media\welcome.jpeg'
        filebox = FileBox.from_file(path)
        await room.say(filebox)
        await room.say("欢迎入群，请先看群公告并遵守群主相关规定，否则我会跟你杠到底哦~", mentionlist)
        # 检查群成员是否已经将群昵称设为"楼号-门牌号"，如未则提醒，如有则按此更新微信备注（取代昵称）
        for contact in invitees:
            if contact == self.bot.user_self():
                continue
            alias = await room.alias(contact)
            if alias:
                if alias != await contact.alias():
                    try:
                        await contact.alias(alias)
                        self.logger.info(f"更新{contact.name}的备注成功!")
                    except Exception:
                        self.logger.warning(f"更新{contact.name}的备注失败~")
            else:
                await room.say('进群请按规定改昵称哦~', [contact.contact_id])

    async def on_room_topic(self, room: Room, new_topic: str, old_topic: str, changer: Contact, date: datetime) -> None:
        """on room topic changed,

        功能点：
            1. 群名称被更改后的操作
            2. 如果不是群主改的群名，机器人自动修改回原群名并提醒用户不当操作

        Args:
            room (Room): The Room object
            new_topic (str): old topic
            old_topic (str): new topic
            changer (Contact): the contact who change the topic
            date (datetime): the time when the topic changed
        """
        if room.room_id not in self.room_dict.keys():
            return

        if changer.contact_id == self.bot.user_self().contact_id:
            return

        self.logger.info(f'receive room topic changed event <from<{new_topic}> to <{old_topic}>> from room<{room}> ')
        owner = await room.owner()
        if changer.contact_id != owner.contact_id:
            await changer.say('非群主不能更改群名称，请勿捣乱，要不咱俩杠到底')
            await room.topic(old_topic)

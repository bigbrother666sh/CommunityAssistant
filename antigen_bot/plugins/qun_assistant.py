import json
import os
import re
from typing import Optional, List
from wechaty import (
    Wechaty,
    Room,
    Contact,
    FileBox,
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger
from datetime import datetime
from antigen_bot.message_controller import message_controller
from utils.DFAFilter import DFAFilter
from paddlenlp import Taskflow


class QunAssistantPlugin(WechatyPlugin):
    """
    群管助手，功能：
    1、非群主不能更改群名
    2、群内敏感词监测
    3、智能FAQ
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
            self.qunzhu = {}

        if "verify_codes.json" in self.config_files:
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'r', encoding='utf-8') as f:
                self.verify_codes = json.load(f)
        else:
            self.verify_codes = []

        if "qun_faq.json" in self.config_files:
            with open(os.path.join(self.config_url, 'qun_faq.json'), 'r', encoding='utf-8') as f:
                self.qun_faq = json.load(f)
        else:
            self.qun_faq = {key: {} for key in self.room_dict.keys()}

        if "qun_open_seq.json" in self.config_files:
            with open(os.path.join(self.config_url, 'qun_open_seq.json'), 'r', encoding='utf-8') as f:
                self.qun_open_seq = json.load(f)
        else:
            self.qun_open_seq = {}

        self.gfw = DFAFilter()
        self.gfw.parse()
        self.sim = Taskflow("text_similarity")
        self.logger.info(f'QunAssisstant plugin init success.')

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
                          "start with ### -- add verify code \n"
                          "save -- save users status")
            return
        # 3.functions
        if msg.text().startswith("###"):
            self.verify_codes.append(msg.text()[3:])
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'w', encoding='utf-8') as f:
                json.dump(self.verify_codes, f)
            await msg.say(f"new verify code: {msg.text()[3:]} added")
            return

        if msg.text() == 'save':
            with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                json.dump(self.room_dict, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qunzhu, f, ensure_ascii=False)
            await msg.say('save success')

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin":
            return

        talker = msg.talker()
        text = msg.text()

        # 2. check if is director
        if talker.contact_id in self.directors:
            await self.director_message(msg)
            return

        # 3. 处理群主消息
        if text in self.verify_codes:
            message_controller.disable_all_plugins(msg)
            self.verify_codes.remove(text)
            self.qunzhu[talker.contact_id] = talker.name
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qunzhu, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'w', encoding='utf-8') as f:
                json.dump(self.verify_codes, f, ensure_ascii=False)
            await msg.say("hi，很高兴为您服务，请拉我到需要我协助管理的群内，并@我说：觉醒")
            return

        if msg.type() == MessageType.MESSAGE_TYPE_CONTACT:
            # 目前contact格式消息没法儿处理，收到此类消息可以让用户把小助手转发给对方，这样也不会造成打扰
            await talker.say('为避免打扰，我不会主动添加用户，如您朋友有使用需求，请可以把我推给ta')
            return

        # 4. 这个模块只处理群消息，且只处理@自己的消息
        if not msg.room() or not await msg.mention_self():
            return

        room = msg.room()
        await room.ready()
        topic = await room.topic()
        owner = await room.owner()
        text = await msg.mention_text()

        if talker.contact_id in self.qunzhu:
            message_controller.disable_all_plugins(msg)
            if owner.contact_id != talker.contact_id:
                await room.say("您不是该群群主，出于隐私保护，您无法在本群中启动我的功能")
                return

            if text == '觉醒':
                self.room_dict[room.room_id] = talker.contact_id
                with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.qunzhu, f, ensure_ascii=False)
                await room.say('大家好，我是AI群助理，我可以帮助群主回复大家的问题，请@我提问，如果遇到我不知道的问题，我会第一时间通知群主~')

                if room.room_id not in self.qun_faq:
                    self.qun_faq[room.room_id] = {}
                await talker.say(f'您已在{topic}群中激活了AI助理，如需关闭，请在群中@我说：退下')
                await talker.alias(f'{topic}群主')
                self.qunzhu[talker.contact_id] = await talker.alias()

            if text == '退下':
                del self.room_dict[room.room_id]
                with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.qunzhu, f, ensure_ascii=False)
                await talker.say(f'您已在{topic}群中取消了AI助理，如需再次启用，请在群中@我说：觉醒')
            return

        if talker.contact_id in self.qun_open_seq:
            text = self.qun_open_seq[talker.contact_id][0]
            room = self.qun_open_seq[talker.contact_id][1]
            talkerid = self.qun_open_seq[talker.contact_id][2]
            if text == '结束':
                await room.say(f'您之前的提问：{text}，群主已经回答了，答案见上，请您查收~', [talkerid])
                del self.qun_open_seq[talker.contact_id]
            else:
                self.qun_faq[room.room_id][text].append(msg)
                await self.forward_message(msg, room)
            return

        if room.room_id not in self.room_dict:
            return

        # 处理引用回复，从中自动提取文本FAQ
        if re.match(r"^「.+」\s-+\s.+", text, re.S):  # 判断是否为引用消息
            #quote = re.search(r"：.+」", text, re.S).group()[1:-1]  # 引用内容
            reply = re.search(r"-\n.+", text, re.S).group()[2:]  # 回复内容
            text = reply

        text = text.strip().replace('\n', '，')

        if self.gfw.filter(text):
            self.logger.info(f'{text} is filtered, for the reason of {self.gfw.filter(text)}')
            await room.say('请勿发表不当言论，谢谢配合', [talker.contact_id])
            return

        self.logger.info(f'{talker.name} in {topic} asked: {text}')
        # 5. smart FAQ
        answer = []
        if self.qun_faq[room.room_id]:
            similatiry_list = [[text, key] for key in list(self.qun_faq[room.room_id].keys())]
            similatiry = self.sim(similatiry_list)
            for i in range(len(similatiry)-1, -1, -1):
                if similatiry[i]['similarity'] > 0.9:
                    self.logger.info(f"found matched text: {similatiry[i]['text2']}")
                    answer = self.qun_faq[room.room_id][similatiry[i]['text2']]
                    break

        if not answer:
            await room.say("抱歉这个问题我没找到答案，已私信通知群主", [talker.contact_id, self.room_dict[room.room_id]])
            #await contact = self.bot.Contact.find(self.qunzhu[self.room_dict[room.room_id]])
            try:
                await owner.say(f'{talker.name}在{topic}群中提问了：{text}，我的记忆中没有这个答案，请您直接在这里回复我，我会代为回复并在后续类似问题中自动回复')
                await owner.say('答案支持文本、图片、视频、文件、小程序等多种格式，多条答案请依次回复，并在最后说“结束”')
            except Exception as e:
                self.logger.error(e)
            self.qun_open_seq[owner.contact_id] = [text, room, talker.contact_id]
            self.qun_faq[room.room_id][text] = []
        else:
            await room.say(f'对于您说的“{text}”，群主之前有回答，请参考如下', [talker.contact_id])
            for _answer in answer:
                await self.forward_message(_answer, room)

        # 最后检查下talker的群昵称状态，并更新下talker在bot的备注
        alias = await room.alias(talker)
        if alias:
            if alias != await talker.alias():
                try:
                    await talker.alias(alias)
                    print(f"改变{talker.name}的备注成功!")
                except:
                    print(f"改变{talker.name}的备注失败~")
        else:
            await room.say('另外提醒您及时按群主要求更改群昵称哦', [talker.contact_id])

    """
    todo 下面是收款追踪功能，团长在群里@AI+开启xxx收款，统计收款（重复发"开启xx收款"会重置收款，目前一个群同时只会追踪一个收款"
    提取群内的转账消息追踪记录
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
    """

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

    async def forward_message(self, msg: Message, room: Room) -> None:
        """forward the message to the target conversations

        Args:
            msg (Message): the message to forward
            regex (the compile object): the conversation filter
        """
        if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO, MessageType.MESSAGE_TYPE_ATTACHMENT, MessageType.MESSAGE_TYPE_EMOTICON]:
            file_box = await msg.to_file_box()
            saved_file = os.path.join(self.file_cache_dir, file_box.name)
            await file_box.to_file(saved_file, overwrite=True)
            file_box = FileBox.from_file(saved_file)
            await room.say(file_box)

        if msg.type() in [MessageType.MESSAGE_TYPE_TEXT, MessageType.MESSAGE_TYPE_URL, MessageType.MESSAGE_TYPE_MINI_PROGRAM]:
            await msg.forward(room)

        if msg.type() == MessageType.MESSAGE_TYPE_AUDIO:
            file_box = await msg.to_file_box()
            saved_file = os.path.join(self.file_cache_dir, file_box.name)
            await file_box.to_file(saved_file, overwrite=True)
            new_audio_file = FileBox.from_file(saved_file)
            new_audio_file.metadata = {
                "voiceLength": 2000
            }
            await room.say(new_audio_file)

        self.logger.info('=================finish to Qun_Assistant_FAQ=================\n\n')

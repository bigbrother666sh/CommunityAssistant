import json
import os
import re
import time
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
from utils.rasaintent import RasaIntent
from paddlenlp import Taskflow
from antigen_bot.inspurai import Yuan
from antigen_bot.docfaq import DocFAQ


class QunAssistantPlugin(WechatyPlugin):
    """
    群管助手，功能：
    1、非群主不能更改群名
    2、群内敏感词监测
    3、智能FAQ
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None, configs: str = 'CAconfigs'):
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
            self.qun_faq = {key: {} for key in self.qunzhu}

        self.qun_meida_faq = {key: {} for key in self.qunzhu}
        self.listen_to = {}
        self.gfw = DFAFilter()
        self.gfw.parse()
        self.sim = Taskflow("text_similarity")
        self.intent = RasaIntent()
        self.yuan = Yuan(engine='dialog',
                         temperature=1,
                         max_tokens=150,
                         input_prefix='',
                         input_suffix='',
                         output_prefix='',
                         output_suffix='',
                         append_output_prefix_to_query=False,
                         topK=3,
                         topP=0.9,
                         frequencyPenalty=1.2, )
        self.room_open_seq = {key: {} for key in self.room_dict}
        self.docfaq = DocFAQ(skill_id='1211404', terminal='awada')
        self.logger.info(f'UNIT DocFAQ loaded, skill_id: {self.docfaq.skill_id}, terminal: {self.docfaq.terminal}')
        self.logger.info('QunAssistantPlugin init success')

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
            await msg.say(f"new verify code: {msg.text()[3:]} added -- QunAssistant")
            return

        if msg.text() == 'save':
            with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                json.dump(self.room_dict, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qunzhu, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'qun_faq.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qun_faq, f, ensure_ascii=False)
            await msg.say('save success -- QunAssistant')

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
            self.qunzhu.append(talker.contact_id)
            with open(os.path.join(self.config_url, 'qunzhu.json'), 'w', encoding='utf-8') as f:
                json.dump(self.qunzhu, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'verify_codes.json'), 'w', encoding='utf-8') as f:
                json.dump(self.verify_codes, f, ensure_ascii=False)
            await msg.say("hi，很高兴为您服务，请拉我到需要我协助管理的群内，并@我说：小助理 -- QunAssistant")
            return

        if msg.type() == MessageType.MESSAGE_TYPE_CONTACT:
            # 目前contact格式消息没法儿处理，收到此类消息可以让用户把小助手转发给对方，这样也不会造成打扰
            await talker.say('为避免打扰，我不会主动添加用户，如您朋友有使用需求，请可以把我推给ta -- QunAssistant')
            return

        if msg.room():
            if '@所有人' in msg.text():
                return
            text = await msg.mention_text()
            attention = True if await msg.mention_self() else False

        # 4. handle the pre-record meida faq
        if talker.contact_id in self.listen_to:
            message_controller.disable_all_plugins(msg)
            if text == '结束':
                if self.qun_meida_faq[talker.contact_id].get(self.listen_to[talker.contact_id], []):
                    await msg.say(f'{self.listen_to[talker.contact_id]}的答案已经记录 -- QunAssistant')
                else:
                    await msg.say(f'{self.listen_to[talker.contact_id]}的答案尚未补充，再次录入需要重新输入问题文本 -- QunAssistant')
                del self.listen_to[talker.contact_id]
                return

            if not self.listen_to[talker.contact_id] or text == self.listen_to[talker.contact_id]:
                if msg.type() != MessageType.MESSAGE_TYPE_TEXT:
                    await msg.say("请先录入问题，问题仅支持文本，放弃请发送：结束 -- QunAssistant")
                    return
                self.listen_to[talker.contact_id] = text
                if text in self.qun_meida_faq[talker.contact_id]:
                    await msg.say("问题已存在，如果更新答案请直接发送媒体文件，否则请发送：结束 -- QunAssistant")
                else:
                    self.qun_meida_faq[talker.contact_id][text] = []
                    await msg.say("问题已记录，请继续发送媒体文件（支持视频、图片、文字、公众号文章、小程序、语音等）\n"
                                  "依次一条，依次发送到这里，我会逐一记录 \n"
                                  "最后请发送 结束 -- QunAssistant")
                return

            if self.listen_to[talker.contact_id]:
                self.qun_meida_faq[talker.contact_id][self.listen_to[talker.contact_id]].append(msg)
                await msg.say("已记录，如果还有答案，请继续转发。录入结束请发送：结束 -- QunAssistant")
            else:
                await msg.say("请先发送问题文本，再录入答案 -- QunAssistant")
            return

        if talker.contact_id in self.qunzhu and "记一下" in text:
            message_controller.disable_all_plugins(msg)
            await msg.say("好的，请先输入问题，仅限文本格式 -- QunAssistant")
            if talker.contact_id not in self.qun_meida_faq:
                self.qun_meida_faq[talker.contact_id] = {}
            self.listen_to[talker.contact_id] = ''
            return

        # 5. 处理群主在群内的信息，包括在群里启用或者取消小助手，以及通过引用消息录入FAQ
        if not msg.room():
            return

        room = msg.room()
        await room.ready()
        topic = await room.topic()
        owner = await room.owner()

        if talker.contact_id in self.qunzhu:
            if attention is True:
                if owner.contact_id != talker.contact_id:
                    await room.say("您不是该群群主，出于隐私保护，您无法在本群中启动我的功能——群助理插件")
                    return

                if text == '小助理':
                    message_controller.disable_all_plugins(msg)
                    self.room_dict[room.room_id] = talker.contact_id
                    self.room_open_seq[room.room_id] = {}
                    with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                        json.dump(self.room_dict, f, ensure_ascii=False)
                    await room.say('大家好，我是AI群助理，我可以帮助群主回复大家的问题，请@我提问，如果遇到我不知道的问题，我会第一时间通知群主~')
                    await talker.say(f'您已在{topic}群中激活了AI助理，如需关闭，请在群中@我说：退下')

                if text == '退下':
                    message_controller.disable_all_plugins(msg)
                    if room.room_id in self.room_dict:
                        del self.room_dict[room.room_id]
                        with open(os.path.join(self.config_url, 'room_dict.json'), 'w', encoding='utf-8') as f:
                            json.dump(self.room_dict, f, ensure_ascii=False)
                    await talker.say(f'您已在{topic}群中取消了AI助理，如需再次启用，请在群中@我说：小助理')

            if re.match(r"^「.+」\s-+\s.+", text, re.S):  # 判断是否为引用消息
                message_controller.disable_all_plugins(msg)
                quote = re.search(r"：.+」", text, re.S).group()[1:-1]  # 引用内容
                reply = re.search(r"-\n.+", text, re.S).group()[2:]  # 回复内容
                quote = re.sub(r'@.+?\s', "", quote).strip()
                reply = re.sub(r'@.+?\s', "", reply).strip()
                if talker.contact_id not in self.qun_faq:
                    self.qun_faq[talker.contact_id] = {}
                self.qun_faq[talker.contact_id][quote] = reply
            return

       # 6. 处理群成员信息，目前支持劝架和智能FAQ，
        if room.room_id not in self.room_dict:
            return

        message_controller.disable_all_plugins(msg)

        if re.match(r"^「.+」\s-+\s.+", text, re.S):
            text = re.search(r"：.+」", text, re.S).group()[1:-1] + "，" + re.search(r"-\n.+", text, re.S).group()[2:]

        text = text.strip().replace('\n', '，')

        if self.gfw.filter(text):
            await room.say('请勿发表不当言论，谢谢配合', [talker.contact_id])
            self.logger.info(f'{talker.name} in {topic} 发表不当言论: {text}')
            return

        if talker.contact_id in self.room_open_seq[room.room_id]:
            if 'session_id' in self.room_open_seq[room.room_id][talker.contact_id]:
                await self.further_search(room=room, talker=talker, owner=owner, topic=topic, text=text)
                del self.room_open_seq[room.room_id][talker.contact_id]
                return

            if time.time() - self.room_open_seq[room.room_id][talker.contact_id]['time'] <= 300:
                #text = self.room_open_seq[room.room_id][talker.contact_id]['text'] + text
                attention = True
            del self.room_open_seq[room.room_id][talker.contact_id]

        intent, conf = self.intent.predict(text)

        if intent == 'quarrel':
            self.logger.info(f'{talker.name} in {topic} 争吵: {text}')
            self.logger.info(f'intent: {intent}, conf: {conf}')
            reply = self.quanjia(text)
            if reply:
                await room.say(reply, [talker.contact_id])
            return

        if intent in ['notinterest', 'aichallenge', 'badreply']:
            return

        if intent == 'question':
            self.logger.info(f'{talker.name} in {topic} 反映问题: {text}')
            self.logger.info(f'intent: {intent}, conf: {conf}')
            await room.say('居然还有这样的事情[惊讶]，不好意思，您别着急哈~ 您说的的这个问题我已经记录并转告群主啦', [talker.contact_id])
            try:
                await owner.say(f'{talker.name}在{topic} 群中反映问题：{text} --QunAssistant')
            except Exception as e:
                self.logger.error(e)
            return

        if intent == 'angry':
            self.logger.info(f'{talker.name} in {topic} 中情绪激动，说: {text}')
            self.logger.info(f'intent: {intent}, conf: {conf}')
            await room.say('不好意思，让您生气了，我这就通知群主~ 基层工作不易，还请您理解[流泪]', [talker.contact_id])
            try:
                await owner.say(f'{talker.name}在{topic} 中情绪激动，说：{text} --QunAssistant')
            except Exception as e:
                self.logger.error(e)
            return

        if intent in ['provocate', 'complain']:
            self.logger.info(f'{talker.name} in {topic} 抱怨: {text}')
            self.logger.info(f'intent: {intent}, conf: {conf}')
            await room.say('您先别着急，气大伤身啊[调皮]\n这个问题我们在处理了，您也可以私信群主了解详情', [talker.contact_id])
            try:
                await owner.say(f'{talker.name}在{topic} 抱怨: {text} --QunAssistant')
            except Exception as e:
                self.logger.error(e)
            return

        if attention is False:
            return

        self.logger.info(f'{talker.name} in {topic} asked: {text}')
        self.logger.info(f'intent: {intent}, conf: {conf}')
        if intent == 'continuetosay':
            self.room_open_seq[room.room_id][talker.contact_id] = {'text': text, 'time': time.time()}
            await room.say('嗯，我在，您说', [talker.contact_id])
            return

        if intent == 'praise':
            await room.say('谢谢您，我会更加努力的[害羞]', [talker.contact_id])
            return

        if intent == 'greeting':
            await room.say('您好，在的，有问题可以@我直接提问哦', [talker.contact_id])
            return

        if intent == 'bye':
            await room.say('好的呢[愉快]', [talker.contact_id])
            return

        # 7. smart FAQ
        answered = False
        if self.qun_faq[self.room_dict[room.room_id]]:
            similatiry_list = [[text, key] for key in list(self.qun_faq[self.room_dict[room.room_id]].keys())]
            similatiry = self.sim(similatiry_list)
            for i in range(len(similatiry)-1, -1, -1):
                if similatiry[i]['similarity'] > 0.88:
                    self.logger.info(f"found matched text: {similatiry[i]['text2']}, answered:{self.qun_faq[self.room_dict[room.room_id]][similatiry[i]['text2']]}")
                    await room.say(self.qun_faq[self.room_dict[room.room_id]][similatiry[i]['text2']], [talker.contact_id])
                    await room.say("以上答案来自群主历史回复，仅供参考哦~", [talker.contact_id])
                    answered = True
                    break

        answer = []
        if self.qun_meida_faq[self.room_dict[room.room_id]]:
            similatiry_list = [[text, key] for key in list(self.qun_meida_faq[self.room_dict[room.room_id]].keys())]
            similatiry = self.sim(similatiry_list)
            for i in range(len(similatiry)-1, -1, -1):
                if similatiry[i]['similarity'] > 0.88:
                    self.logger.info(f"found matched text: {similatiry[i]['text2']}")
                    answer = self.qun_meida_faq[self.room_dict[room.room_id]][similatiry[i]['text2']]
                    break

        if answer:
            await room.say(f'对于您说的“{text}”，群主之前有回答，请参考如下', [talker.contact_id])
            for _answer in answer:
                await self.forward_message(_answer, room)
            self.logger.info('Media Answered')

        if not answer and answered is False:
            await self.further_search(room=room, talker=talker, owner=owner, topic=topic, text=text)

        # 最后检查下talker的群昵称状态，并更新下talker在bot的备注
        alias = await room.alias(talker)
        if alias:
            if alias != await talker.alias():
                try:
                    await talker.alias(alias)
                    self.logger.info(f"改变{talker.name}的备注成功!")
                except Exception as e:
                    self.logger.error(e)
        else:
            await room.say('另外提醒您及时按群主要求更改群昵称哦', [talker.contact_id])

    async def further_search(self, room: Room, talker: Contact, owner: Contact, topic: str, text: str) -> None:
        session_id = ''
        if talker.contact_id in self.room_open_seq[room.room_id]:
            session_id = self.room_open_seq[room.room_id][talker.contact_id].get('session_id', '')

        result = self.docfaq.predict(text, session_id)
        if result and result['error_code'] == 0 and result['result']['responses'][0]['actions'][0]['action_id'] != 'Innovation_Bot_failure':
            await room.say(result['result']['responses'][0]['actions'][0]['say'], [talker.contact_id])
            self.logger.info(f"docFAQ--{result['result']['responses'][0]['actions'][0]['say']}\n")
            if result['result']['responses'][0]['actions'][0]['action_id'] == 'Innovation_Bot_guide':
                self.room_open_seq[room.room_id][talker.contact_id] = {'text': text, 'time': time.time, 'session_id': result['result']['session_id']}
                for option in result['result']['responses'][0]['actions'][0]['options']:
                    await room.say(option['option'])
                await room.say('如果引导项中没有您想要的，您也可以进一步补充关键信息，帮助我们为您找到更合适的答案。')
        else:
            await room.say("抱歉这个问题我没找到答案，已私信通知群主", [talker.contact_id, self.room_dict[room.room_id]])
            try:
                await owner.say(f'{talker.name}在{topic}群中提问了：{text}，我的记忆中以及文档库中均没有这个答案，请您及时群内引用回复，或者录入媒体答案 --QunAssistant')
            except Exception as e:
                self.logger.error(e)
            if result['result']['responses'][0]['actions'][0]['action_id'] != 'Innovation_Bot_failure':
                self.logger.error(f'UNIT FAQ failed \n {result}\n')
            else:
                self.logger.warning('no answer found\n')

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
    def quanjia(self, text: str) -> str:
        prompt = f"你所在的群是小区住户聊天群，群成员都是同住一个小区的邻居，平时大家都很和睦。今天你突然看到有人在群里争吵说：“{text}” ，你赶忙劝对方说：“"
        self.logger.info(prompt)
        for i in range(7):
            reply = self.yuan.submit_API(prompt, trun="”")
            #reply = self.zeus.get_response(prompt)
            if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                self.logger.warning(f'generation failed {str(i + 1)} times.')
                continue

        if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
            self.logger.warning(f'Yuan may out of service, {reply}')
            return ''

        return reply

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
        path = os.getcwd() + '/media/welcome.jpeg'
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
        """
        if msg.type() in [MessageType.MESSAGE_TYPE_IMAGE, MessageType.MESSAGE_TYPE_VIDEO, MessageType.MESSAGE_TYPE_EMOTICON]:
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

        self.logger.info('Qun_Assistant_Message_Forward_Finish\n')

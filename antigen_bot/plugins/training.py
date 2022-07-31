import os
import re
from typing import Optional
from wechaty import (
    Wechaty,
    MessageType,
    WechatyPlugin,
    Message,
    Contact,
    FriendshipType,
    Friendship,
    WechatyPluginOptions
)

from antigen_bot.message_controller import message_controller
from utils.DFAFilter import DFAFilter
from utils.rasaintent import RasaIntent
from antigen_bot.inspurai import Yuan
import json
import xlrd
from datetime import datetime
#from antigen_bot.Ernie.Zeus import Zeus


class TrainingPlugin(WechatyPlugin):
    """
    社群工作人员培训模块
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None, configs: str = 'CAconfigs'):
        super().__init__(options)
        # 1. init the config file
        self.config_url = configs
        self.config_files = os.listdir(self.config_url)

        # 2. save the log info into <plugin_name>.log file
        #self.cache_dir = f'./.{self.name}'
        #self.file_cache_dir = f'{self.cache_dir}/file'
        #os.makedirs(self.file_cache_dir, exist_ok=True)

        #log_file = os.path.join(self.cache_dir, 'log.log')
        #self.logger = get_logger(self.name, log_file)

        # 3. check and load metadata
        if self._file_check() is False:
            raise RuntimeError('TrainingPlugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        self.courses = self._load_course()

        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('Training director.json not valid, pls refer to above info and try again')

        if "train_room.json" in self.config_files:
            with open(os.path.join(self.config_url, 'train_room.json'), 'r', encoding='utf-8') as f:
                self.train_room = json.load(f)
        else:
            self.train_room = {}

        if "train_record.json" in self.config_files:
            with open(os.path.join(self.config_url, 'train_record.json'), 'r', encoding='utf-8') as f:
                self.record = json.load(f)
        else:
            self.record = {}

        self.gfw = DFAFilter()
        self.gfw.parse()
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
        #self.zeus = Zeus()
        self.training = {}
        self.logger.info(f'Training plugin init success.')
        engine_name = self.yuan.get_engine()
        self.logger.info(
            f'with yuan engine:{engine_name},with temperature=1, max_tokens=150, topK=3, topP=0.9, frequencyPenalty=1.2')

    async def init_plugin(self, wechaty: Wechaty) -> None:
        message_controller.init_plugins(wechaty)
        return await super().init_plugin(wechaty)

    def _file_check(self) -> bool:
        """check the config file"""
        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

        if "courses.xlsx" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have courses.xlsx!')
            return False

    async def director_message(self, msg: Message):
        """
        Director Module
        """
        # 1. check the heartbeat of WechatyPlugin
        if msg.text() == "ding":
            await msg.say(f'dong -- {self.name}TrainingPlugin')
            return
        # 2. help menu
        if msg.text() == 'help':
            await msg.say(f"{self.name} TrainingPlugin Director Code: \n"
                          "ding -- check heartbeat \n"
                          "save -- save users status")
            return
        # 3.functions
        if msg.text() == 'save':
            with open(os.path.join(self.config_url, 'train_room.json'), 'w', encoding='utf-8') as f:
                json.dump(self.train_room, f, ensure_ascii=False)
            with open(os.path.join(self.config_url, 'train_record.json'), 'w', encoding='utf-8') as f:
                json.dump(self.record, f, ensure_ascii=False)
            await msg.say(f'save success -- {self.name} Trainingplugin')

    def _load_course(self) -> dict:
        """load the course data"""
        course_file = os.path.join(self.config_url, 'courses.xlsx')
        data = xlrd.open_workbook(course_file)
        table = data.sheets()[0]

        courses = {}
        nrows = table.nrows
        if nrows < 2:
            self.logger.warning('no data in courses.xls,this is not allowed')
            return courses

        for i in range(1, nrows):
            courses[table.cell_value(i, 0)] = {'prompt': table.cell_value(i, 2), 'des': f'情景对话模拟训练已开始。\n{table.cell_value(i, 1)}',
                                              'opening': table.cell_value(i, 3)}
        return courses

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin" or not msg.room():
            return

        if msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        talker = msg.talker()
        room = msg.room()

        if msg.room() and '@所有人' in msg.text():
            return

        text = await msg.mention_text() if room else msg.text()

        # 2. check if is director
        if talker.contact_id in self.directors:
            if text == '觉醒':
                message_controller.disable_all_plugins(msg)
                await room.ready(force_sync=True)
                self.train_room[await room.topic()] = [contact.contact_id for contact in await room.member_list()]
                await room.say('大家好，我是数字社工助理，我可以通过扮演各种居民角色，以情景对话模拟的方式帮助大家提升工作技能。\n'
                               '欢迎大家微信加我开始体验。')
                return

            if text == '结束服务':
                message_controller.disable_all_plugins(msg)
                del self.train_room[await room.topic()]
                return

            await self.director_message(msg)
            return

        if self.bot.user_self() in await msg.mention_list() and await room.topic() in self.train_room:
            message_controller.disable_all_plugins(msg)
            await room.say('您好，我是数字社工助理，我可以通过扮演各种居民角色，以情景对话模拟的方式帮助大家提升工作技能。\n'
                           '欢迎微信加我开始体验。')
            return

        # 这里预留未来群聊训练模式（用于人工指导、测试等）
        if msg.room():
            return

        # 3. check if is training
        if talker.contact_id in self.training:
            message_controller.disable_all_plugins(msg)
            if "结束训练" in text:
                self.logger.info(f"来自 {self.training[talker.contact_id]['group']} 的 {talker.name} 主动结束了训练，该次训练记录取消")
                del self.training[talker.contact_id]
                await talker.say('训练结束，结果未记录，如需重新开始，请回复：开始训练')
                return

            if not self.training[talker.contact_id]['course']:
                for title in self.courses.keys():
                    if title in text:
                        self.training[talker.contact_id]['course'] = title
                        await talker.say(self.courses[title]["des"])
                        await talker.say('提醒：对话中有时我会故意沉默，您可以继续说，不必等待。')
                        self.logger.info(f"来自 {self.training[talker.contact_id]['group']} 的 {talker.name} 开始了训练，课程：{title}")
                        await talker.say(self.courses[title]["opening"])
                        self.training[talker.contact_id]['log'].append(f"你说：“{self.courses[title]['opening']}”")
                    else:
                        await talker.say('请先选择课程，如需结束或重新开始，请回复：结束训练')
                    return

            if re.match(r"^「.+」\s-+\s.+", text, re.S):
                text = re.search(r"：.+」", text, re.S).group()[1:-1] + "，" + re.search(r"-\n.+", text, re.S).group()[2:]

            text = text.strip().replace('\n', '，')
            self.training[talker.contact_id]['log'].append(f"工作人员说：“{text}”")

            if self.gfw.filter(text):
                await talker.say(f'您因发表不当言论挑战失败，对话轮次：{len(self.training[talker.contact_id]["turn"])}')
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 因发表不当言论挑战失败')
                await self.stop_train(talker)
                return

            intent, conf = self.intent.predict(text)
            if intent in ['notinterest', 'aichallenge', 'badreply', 'angry', 'provocate', 'complain', 'quarrel']:
                await talker.say(f"侦测到您未合理控制谈话情绪，本次挑战失败，对话轮次：{len(self.training[talker.contact_id]['turn'])}")
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}')
                await self.stop_train(talker)
                return

            dialog = ''
            for i in range(len(self.training[talker.contact_id]['log'])-1, -1, -1):
                dialog = self.training[talker.contact_id]['log'][i] + dialog
                if len(dialog) > 300:
                    break

            prompt = self.courses[self.training[talker.contact_id]['course']]['prompt'] + dialog + "你说：“"

            for i in range(7):
                reply = self.yuan.submit_API(prompt, trun="”")
                #reply = self.zeus.get_response(prompt)
                if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                    self.logger.warning(f'generation failed {str(i + 1)} times.')
                    continue
                if len(reply) <= 5 or reply not in dialog:
                    break
                print(prompt)

            if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                self.logger.warning(f'Yuan may out of service, {reply}')
                self.logger.info(prompt)
                return

            await talker.say(reply)
            self.logger.info(f"AI回复：{reply}")
            self.training[talker.contact_id]["log"].append(f"你说：“{reply}”")
            self.training[talker.contact_id]["turn"] += 1

            intent, conf = self.intent.predict(reply)
            if intent in ['bye', 'notinterest', 'greeting']:
                await talker.say(f'恭喜您，通过测试，对话轮次：{len(self.training[talker.contact_id]["turn"])}')
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 通过测试，AI角色最终情绪：{intent}')
                await self.stop_train(talker)
            elif intent == 'praise':
                await talker.say(f"恭喜您，完美应付此场景！对话轮次：{len(self.training[talker.contact_id]['turn'])}")
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 完美应付此场景！AI角色最终情绪：{intent}')
                await self.stop_train(talker)
            return

        # 5.start training
        if '开始训练' in text:
            message_controller.disable_all_plugins(msg)
            group = ''
            for key, list in self.train_room.items():
                if talker.contact_id in list:
                    group = key
                    break
            if not group:
                await talker.say('您没有权限开始训练，请联系上级部门添加微信号：baohukeji 咨询开通')
                self.logger.warning(f'{talker.name} 咨询开通')
                return

            self.training[talker.contact_id] = {'group':group, 'course': '', 'turn': 0, 'log': []}
            course_topics = '\n'.join(self.courses.keys())
            await talker.say(f'欢迎使用AI虚拟情景培训，目前已有课程如下：\n' + course_topics + '\n请直接回复课程名称开始')
        else:
            await talker.say('如需对话情景模拟训练请回复：开始训练')

    async def stop_train(self, talker: Contact) -> None:
        """
        End this round of training, calculate the ranking,
        inform the testers of the results,
        and record the test information as a txt file
        """
        date = datetime.now().strftime('%Y%m%d%H%M')
        if self.training[talker.contact_id]['course'] in self.record:
            self.record[self.training[talker.contact_id]['course']].append((self.training[talker.contact_id]['turn'], talker.name))
        else:
            self.record[self.training[talker.contact_id]['course']] = [(self.training[talker.contact_id]['turn'], talker.name)]

        record = 0
        if len(self.record[self.training[talker.contact_id]['course']]) > 10:
            self.record[self.training[talker.contact_id]['course']].sort(key=lambda x: x[0], reverse=True)
            record = self.record[self.training[talker.contact_id]['course']].index((self.training[talker.contact_id]['turn'], talker.name))

        if 0 < record <= 10:
            await talker.say(f'您本次测试成绩进入本场景周期排名前十！名列第{str(record)}，继续努力哦[撒花]')
        if record > 10:
            await talker.say(f"本次测试成绩超过本场景周期排名内{str(100-record*100//len(self.record[self.training[talker.contact_id]['course']]))}%的用户，再接再励哦~")

        with open(".TrainingPlugin/" + date + talker.name + ".txt", 'a', encoding='utf-8') as f:
            f.write(f'测试时间：{date}'+ '\n')
            f.write(f'测试人：{talker.name}'+ '\n')
            f.write(f"组织：{self.training[talker.contact_id]['group']}" + '\n')
            f.write(f"测试情景：{self.training[talker.contact_id]['course']}" + '\n')
            f.write(f"成绩（轮次）：{str(self.training[talker.contact_id]['turn'])}" + '\n')
            f.write(f"周期排名：{str(record)}" + '\n') if record != 0 else f.write(f"周期排名：---" + '\n')
            f.write("----------------------" + '\n')
            for turn in self.training[talker.contact_id]['log']:
                if turn.startwith('你'):
                    f.write('AI'+turn[1:] + '\n')
                else:
                    f.write('测试' + turn[2:] + '\n')
        del self.training[talker.contact_id]

    async def on_friendship(self, friendship: Friendship) -> None:
        """handle the event when there is friendship changed
        功能描述：
            1. 收到好友邀请的处理
            2. 判断是否有用户权限，有的话直接接受好友邀请
        Args:
            friendship (Friendship):
        """
        self.logger.info(f'receive friendship<{friendship}> event')

        if friendship.type() == FriendshipType.FRIENDSHIP_TYPE_RECEIVE:
            contact = friendship.contact()
            for key, list in self.train_room.items():
                if contact.contact_id in list:
                    await friendship.accept()
                    await contact.say('欢迎添加数字社工助理，如需开始情景对话模拟训练，请直接发送：开始训练')

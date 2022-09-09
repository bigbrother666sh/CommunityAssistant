import os
import re
from typing import Optional
from wechaty import (
    Wechaty,
    MessageType,
    WechatyPlugin,
    Message,
    Contact,
    WechatyPluginOptions
)
from paddlenlp import Taskflow
from antigen_bot.message_controller import message_controller
from utils.simpleFilter import SimpleFilter
from utils.rasaintent import RasaIntent
import json
import xlrd
from datetime import datetime
from pcl_pangu.online import Infer


class PanGuTrainingPlugin(WechatyPlugin):
    """
    社群工作人员培训模块
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None, configs: str = 'CAconfigs'):
        super().__init__(options)
        # 1. init the config file
        self.config_url = configs
        self.config_files = os.listdir(self.config_url)
        self.record_url = os.path.join(os.environ.get("CACHE_DIR", ".wechaty"), self.name)

        # 3. check and load metadata
        if self._file_check() is False:
            raise RuntimeError('TrainingPlugin needs above config_files, pls add and try again')

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        self.courses = self._load_course()

        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('Training director.json not valid, pls refer to above info and try again')

        self.gfw = SimpleFilter()
        self.intent = RasaIntent()
        self.sim = Taskflow("text_similarity")
        self.pangu_key = os.environ.get("PANGU_KEY", None)
        if not self.pangu_key:
            raise RuntimeError('pangu key not set')
        self.training = {}
        self.logger.info(f'Pangu Training plugin init success.')

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
                          "save -- save users status \n"
                          "reload -- reload new course.xlsx --TrainingPlugin")
            return
        # 3.functions
        if msg.text() == 'reload':
            new_course = self._load_course()
            if new_course:
                self.courses = new_course
                await msg.say('new course.xlsx loaded_Training Plugin')
            else:
                await msg.say('new course.xlsx file wrong, nothing happened_Training Plugin')
            return

        await msg.say('send help to see what I can do--TrainingPlugin')

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
            courses[table.cell_value(i, 0)] = {'prompt': table.cell_value(i, 2), 'des': f'情景对话模拟训练已开始。\n{table.cell_value(i, 1)}', 'opening': table.cell_value(i, 3)}
        return courses

    def repeat_check(self, list) -> int:
        """
        check the repeat message
        """
        similatiry = self.sim(list)
        repeat_no = 0
        for item in similatiry:
            if item['similarity'] > 0.9:
                repeat_no += 1
            if repeat_no > 2:
                return repeat_no
        return repeat_no

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin":
            return

        if msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        talker = msg.talker()

        if msg.room():
            return

        text = msg.text()

        # 3. check if is training
        if talker.contact_id in self.training:
            message_controller.disable_all_plugins(msg)
            if "结束训练" in text:
                self.logger.info(f"{talker.name} 主动结束了训练，该次训练记录取消")
                del self.training[talker.contact_id]
                await talker.say('训练结束，结果未记录，如需重新开始，请回复：开始训练')
                return

            if not self.training[talker.contact_id]['course']:
                for title in self.courses.keys():
                    if title in text:
                        self.training[talker.contact_id]['course'] = title
                        await talker.say(self.courses[title]["des"])
                        await talker.say('提醒：对话中有时我会故意沉默，您可以继续说，不必等待。期间如果您想结束或重新开始训练，请发送：结束训练')
                        self.logger.info(f"{talker.name} 开始了训练，课程：{title}")
                        await talker.say(self.courses[title]["opening"])
                        # self.training[talker.contact_id]['log'].append(f"你说：“{self.courses[title]['opening']}”")
                        return
                await talker.say('请先选择课程，如需结束或重新开始，请回复：结束训练')
                return

            if re.match(r"^「.+」\s-+\s.+", text, re.S):
                text = re.search(r"：.+」", text, re.S).group()[1:-1] + "，" + re.search(r"-\n.+", text, re.S).group()[2:]

            text = text.strip().replace('\n', '，')
            self.training[talker.contact_id]['log'].append(f"工作人员说：“{text}”")

            if self.gfw.filter(text):
                await talker.say(f'您因发表不当言论挑战失败，对话轮次：{self.training[talker.contact_id]["turn"]}')
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 因发表不当言论挑战失败')
                self.logger.info(f'测试人员：{talker.name} 因发表不当言论挑战失败，详情已记录.TrainingPlugin文件夹')
                await self.stop_train(talker)
                return

            intent, conf = self.intent.predict(text)
            if intent == "continuetosay":
                self.logger.info('intent: continuetosay, just pass')
                return

            if intent in ['impatient', 'bye', 'badreply', 'angry', 'quarrel']:
                await talker.say(f"侦测到您未合理控制谈话情绪，本次挑战失败，对话轮次：{self.training[talker.contact_id]['turn']}")
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}')
                self.logger.info(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}')
                await self.stop_train(talker)
                return

            dialog = ''
            for i in range(len(self.training[talker.contact_id]['log'])-1, -1, -1):
                dialog = self.training[talker.contact_id]['log'][i] + dialog
                if len(dialog) > 50:
                    break

            prompt = self.courses[self.training[talker.contact_id]['course']]['prompt'] + dialog + "你说：“"

            for i in range(7):
                reply = Infer.generate("pangu-alpha-13B-md", prompt, self.pangu_key)
                if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                    self.logger.warning(f'generation failed {str(i + 1)} times.')
                    self.logger.info(prompt)
                    continue
                if len(self.training[talker.contact_id]["log"]) <= 12:
                    repeat = self.repeat_check([[f"你说：“{reply}”", key] for key in self.training[talker.contact_id]["log"]])
                else:
                    repeat = self.repeat_check([[f"你说：“{reply}”", key] for key in self.training[talker.contact_id]["log"][-12:]])
                if repeat < 2:
                    break
                self.logger.warning(f'repeat generation:{reply}')
                self.logger.info(prompt)
                prompt = self.courses[self.training[talker.contact_id]['course']]['prompt'] + self.training[talker.contact_id]['log'][-1] + "你说：“"

            if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                self.logger.warning(f'Yuan may out of service, {reply}')
                self.logger.info(prompt)
                return

            await talker.say(reply)
            self.training[talker.contact_id]["turn"] += 1
            self.training[talker.contact_id]['log'].append(f"你说：“{reply}”")

            intent, conf = self.intent.predict(reply)
            if intent in ['bye', 'sayno']:
                await talker.say(f'恭喜您，通过测试，对话轮次：{self.training[talker.contact_id]["turn"]}')
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 通过测试，AI角色最终情绪：{intent}')
                self.logger.info(f'测试人员：{talker.name} 通过测试，详情已记录.TrainingPlugin文件夹')
                await self.stop_train(talker)
            elif intent in ['praise', 'praise_bye']:
                await talker.say(f"恭喜您，完美应付此场景！对话轮次：{self.training[talker.contact_id]['turn']}")
                self.training[talker.contact_id]['log'].append(f'测试人员：{talker.name} 完美应付此场景！AI角色最终情绪：{intent}')
                self.logger.info(f'测试人员：{talker.name} 完美通过测试，详情已记录于.TrainingPlugin文件夹')
                await self.stop_train(talker)
            elif intent in ['angry', 'doubt', 'quarrel', 'sayno']:
                self.training[talker.contact_id]['fail'] += 1
                if self.training[talker.contact_id]['fail'] > 3:
                    await talker.say(f"虚拟角色情绪激动次数超过3次，本次挑战失败，对话轮次：{self.training[talker.contact_id]['turn']}")
                    self.training[talker.contact_id]['log'].append(f'虚拟角色情绪激动次数超过3次，本次挑战失败，测试人员：{talker.name}')
                    self.logger.info(f'虚拟角色情绪激动次数超过3次，本次挑战失败，测试人员：{talker.name}，详情已记录于 {self.name}文件夹')
                    await self.stop_train(talker)
            return

        # 5.start training
        if '开始训练' in text:
            message_controller.disable_all_plugins(msg)
            self.training[talker.contact_id] = {'course': '', 'turn': 0, 'fail': 0, 'log': []}
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

        with open(os.path.join(self.record_url, date + talker.name + ".txt"), 'w', encoding='utf-8') as f:
            f.write(f'测试时间：{date}' + '\n')
            f.write(f'测试人：{talker.name}' + '\n')
            f.write(f"测试情景：{self.training[talker.contact_id]['course']}" + '\n')
            f.write(f"成绩（轮次）：{str(self.training[talker.contact_id]['turn'])}" + '\n')
            f.write("----------------------" + '\n')
            f.write(f"AI说：“{self.courses[self.training[talker.contact_id]['course']]['opening']}”" + '\n')
            for turn in self.training[talker.contact_id]['log']:
                if turn.startswith('你'):
                    f.write('AI'+turn[1:] + '\n')
                else:
                    f.write('测试' + turn[2:] + '\n')
        del self.training[talker.contact_id]

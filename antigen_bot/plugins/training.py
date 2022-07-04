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
from utils.rasaintent import RasaIntent
from paddlenlp import Taskflow
from antigen_bot.inspurai import Yuan


class TrainingPlugin(WechatyPlugin):
    """
    社群工作人员培训模块
    这里ai会扮演两个角色：1、很难缠的刺头；2、要死要活的怨妇
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
        self.training_room = {}
        self.logger.info(f'Training plugin init success.')

    async def init_plugin(self, wechaty: Wechaty) -> None:
        message_controller.init_plugins(wechaty)
        return await super().init_plugin(wechaty)

    def _file_check(self) -> bool:
        """check the config file"""
        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

    @message_controller.may_disable_message
    async def on_message(self, msg: Message) -> None:
        if msg.is_self() or msg.talker().contact_id == "weixin" or not msg.room():
            return

        if msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        talker = msg.talker()
        room = msg.room()
        text = await msg.mention_text() if await msg.mention_self() else msg.text()

        # 2. check if is director
        if talker.contact_id in self.directors:
            if text == '觉醒':
                message_controller.disable_all_plugins(msg)
                self.training_room[room.room_id] = {'pre_prompt': '', 'des': '', 'trainer': '', 'turn': []}
                await room.say('AI培训演员就位，请问需要我这次扮演什么？刺头还是怨妇？', [talker.contact_id])

            if text == '刺头':
                message_controller.disable_all_plugins(msg)
                self.training_room[room.room_id] = {'pre_prompt': '', 'des': '', 'trainer': '', 'turn': []}
                await room.say('好的，刺头模式已启动，请指定测试人员', [talker.contact_id])

            if text == '怨妇':
                message_controller.disable_all_plugins(msg)
                self.training_room[room.room_id] = {'pre_prompt': '', 'des': '', 'trainer': '', 'turn': []}
                await room.say('好的，怨妇模式已启动，请指定测试人员', [talker.contact_id])

            if self.bot.user_self() in await msg.mention_list() and self.training_room[room.room_id]:
                message_controller.disable_all_plugins(msg)
                for contact in await room.member_list():
                    if contact.contact_id == self.bot.user_self().contact_id:
                        continue
                    else:
                        self.training_room[room.room_id]['trainer'] = contact.contact_id
                        await room.say(f'{contact.name}已指定为测试人员', [talker.contact_id])
                        break
                if self.training_room[room.room_id]['pre_prompt']:
                    await room.say(f'{self.training_room[room.room_id]["des"]}', [self.training_room[room.room_id]["trainer"]])
                    self.logger.info(f'director has start the training process, detail:{self.training_room[room.room_id]}')
                    if self.training_room[room.room_id]['pre_prompt'] == '':
                        await room.say('', [self.training_room[room.room_id]["trainer"]])
                        self.training_room[room.room_id]["turn"].append(f"你说：“{reply}”")
                        self.logger.info(f"AI说：“{reply}”")
                    if self.training_room[room.room_id]['pre_prompt'] == '':
                        await room.say('', [self.training_room[room.room_id]["trainer"]])
                        self.training_room[room.room_id]["turn"].append(f"你说：“{reply}”")
                        self.logger.info(f"AI说：“{reply}”")
            return

        # 3. check if is trainer
        if room.room_id not in self.training_room:
            return

        if talker.contact_id != self.training_room[room.room_id]['trainer']:
            return

        message_controller.disable_all_plugins(msg)
        if re.match(r"^「.+」\s-+\s.+", text, re.S):
            text = re.search(r"：.+」", text, re.S).group()[1:-1] + "，" + re.search(r"-\n.+", text, re.S).group()[2:]

        text = text.strip().replace('\n', '，')

        if self.gfw.filter(text):
            await room.say(f'测试人员：{talker.name} 因发表不当言论挑战失败，对话轮次：{len(self.training_room[room.room_id]["turn"])}', self.directors)
            self.logger.info(f'测试人员：{talker.name} 因发表不当言论挑战失败，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
            return

        intent = self.intent.predict(text)
        if intent in ['complain', 'challenge', 'challenge_bye', 'quarrel']:
            await room.say('侦测到您未合理控制谈话情绪，本次挑战失败', [talker.contact_id])
            await room.say(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                           self.directors)
            self.logger.info(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
            return

        self.training_room[room.room_id]["turn"].append(f"工作人员说：“{text}”")
        self.logger.info(f"trainer说：“{text}”")

        for i in range(7):
            prompt = self.training_room[room.room_id]['pre_prompt'] + ''.join(self.training_room[room.room_id]['turn'])
            reply = self.yuan.submit_API(prompt, trun="”")
            if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                self.logger.warning(f'generation failed {str(i + 1)} times.')
                continue
            if len(reply) <= 5 or reply not in ''.join(self.training_room[room.room_id]['turn']:
                break

        if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
            self.logger.warning(f'Yuan may out of service, {reply}')
            return

        intent = self.intent.predict(reply)
        if intent in ['notinterest', 'bye']:
            await room.say('恭喜您，通过测试，成绩为合格，这意味着您可以应付这种情况', [talker.contact_id])
            await room.say(
                f'测试人员：{talker.name} 通过测试，成绩合格，对方最终情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                self.directors)
            self.logger.info(
                f'测试人员：{talker.name} 通过测试，成绩合格，对方最终情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
        elif intent == 'praise':
            await room.say('恭喜您，通过测试，成绩优秀，你不仅应付了局面，居然还能让对方很满意[强]', [talker.contact_id])
            await room.say(
                f'测试人员：{talker.name} 通过测试，成绩优秀，对方最终情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                self.directors)
            self.logger.info(
                f'测试人员：{talker.name} 通过测试，成绩优秀，对方最终情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
        else:
            await room.say(reply)
            self.training_room[room.room_id]["turn"].append(f"你说：“{reply}”")
            self.logger.info(f"AI说：“{reply}”")

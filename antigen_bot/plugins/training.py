import os
import re
from typing import Optional
from wechaty import (
    Wechaty,
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger
from antigen_bot.message_controller import message_controller
from utils.DFAFilter import DFAFilter
from utils.rasaintent import RasaIntent
#from antigen_bot.inspurai import Yuan
from antigen_bot.Ernie.Zeus import Zeus


class TrainingPlugin(WechatyPlugin):
    """
    社群工作人员培训模块
    这里ai会扮演两个角色：1、很难缠的刺头；2、要死要活的怨妇
    """
    def __init__(self, options: Optional[WechatyPluginOptions] = None):
        super().__init__(options)

        # 2. save the log info into <plugin_name>.log file
        self.cache_dir = f'./.{self.name}'
        self.file_cache_dir = f'{self.cache_dir}/file'
        os.makedirs(self.file_cache_dir, exist_ok=True)

        log_file = os.path.join(self.cache_dir, 'log.log')
        self.logger = get_logger(self.name, log_file)

        # 3. check and load metadata
        self.directors = ['wxid_tnv0hd5hj3rs11']

        self.gfw = DFAFilter()
        self.gfw.parse()
        self.intent = RasaIntent()
        """
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
        """
        self.zeus = Zeus()
        self.training_room = {}
        self.logger.info(f'Training plugin init success.')

    async def init_plugin(self, wechaty: Wechaty) -> None:
        message_controller.init_plugins(wechaty)
        return await super().init_plugin(wechaty)

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
                return

            if text == '刺头':
                message_controller.disable_all_plugins(msg)
                self.training_room[room.room_id] = {'pre_prompt': '你叫李二牛，今年四十多岁，是个蛮不讲理的人。你所在的小区因突发疫情需要暂时封闭，但你执意出去与朋友聚会，于是你来到居委会，决定与工作人员好好理论一番。',
                                                    'des': '情景对话模拟训练已开始。\n我扮演一个蛮不讲理的小区居民，我们所在的小区因突发疫情需要暂时封闭，而我执意要外出与朋友聚会，我现在来到居委会，您刚好作为工作人员接待我。', 'trainer': '', 'turn': []}
                await room.say('好的，刺头模式已启动，请指定测试人员', [talker.contact_id])
                return

            if text == '怨妇':
                message_controller.disable_all_plugins(msg)
                self.training_room[room.room_id] = {'pre_prompt': '你叫王翠花，是个四十多岁的家庭妇女，你总是怀疑丈夫有外遇，但你也没有确凿证据，于是你来到居委会找工作人员寻求帮助。',
                                                    'des': '情景对话模拟训练已开始。\n我扮演一个四十多岁的家庭妇女，我怀疑我的丈夫有外遇，这让我心神不宁。于是我来到居委会寻求帮助，其实我并不确定这事儿是否归居委会管……您刚好作为工作人员接待我。', 'trainer': '', 'turn': []}
                await room.say('好的，怨妇模式已启动，请指定测试人员', [talker.contact_id])
                return

            if self.bot.user_self() in await msg.mention_list() and room.room_id in self.training_room:
                message_controller.disable_all_plugins(msg)
                for contact in await msg.mention_list():
                    if contact == self.bot.user_self() or contact.contact_id in self.directors:
                        continue
                    else:
                        self.training_room[room.room_id]['trainer'] = contact.contact_id
                        await room.say(f'{contact.name}已指定为测试人员', [talker.contact_id])
                        break
                if self.training_room[room.room_id]['pre_prompt']:
                    await room.say(f'{self.training_room[room.room_id]["des"]}', [self.training_room[room.room_id]["trainer"]])
                    await room.say('提醒：对话中有时我会故意沉默，您可以继续说，不必等待。', [self.training_room[room.room_id]["trainer"]])
                    self.logger.info(f'director has start the training process, detail:{self.training_room[room.room_id]}')
                    if self.training_room[room.room_id]['pre_prompt'] == '你叫李二牛，今年四十多岁，是个蛮不讲理的人。你所在的小区因突发疫情需要暂时封闭，但你执意出去与朋友聚会，于是你来到居委会，决定与工作人员好好理论一番。':
                        await room.say('居委会就可以随便限制居民的人身自由了么？！')
                        self.training_room[room.room_id]["turn"].append("你说：“居委会就可以随便限制居民的人身自由了么？！”")
                        self.logger.info("AI说：“居委会就可以随便限制居民的人身自由了么？！”")
                    if self.training_room[room.room_id]['pre_prompt'] == '你叫王翠花，是个四十多岁的家庭妇女，你总是怀疑丈夫有外遇，但你也没有确凿证据，于是你来到居委会找工作人员寻求帮助。':
                        await room.say('我怀疑我丈夫出轨了，现在法律不是说保护妇女权益么？这事儿你们居委会管么？')
                        self.training_room[room.room_id]["turn"].append("你说：“我怀疑我丈夫出轨了，现在法律不是说保护妇女权益么？这事儿你们居委会管么？”")
                        self.logger.info("AI说：“我怀疑我丈夫出轨了，现在法律不是说保护妇女权益么？这事儿你们居委会管么？”")
                else:
                    await room.say('请先指定仿真模式，现在有两种模式：刺头和怨妇。', [talker.contact_id])
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
            del self.training_room[room.room_id]
            return

        intent, conf = self.intent.predict(text)
        if intent in ['complain', 'challenge', 'challenge_bye', 'quarrel']:
            await room.say('侦测到您未合理控制谈话情绪，本次挑战失败', [talker.contact_id])
            await room.say(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                           self.directors)
            self.logger.info(f'测试人员：{talker.name} 因未合理控制情绪挑战失败，情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
            del self.training_room[room.room_id]
            return

        self.training_room[room.room_id]["turn"].append(f"工作人员说：“{text}”")
        self.logger.info(f"trainer说：“{text}”")

        dialog = ''
        for i in range(len(self.training_room[room.room_id]["turn"])-1, -1, -1):
            dialog = self.training_room[room.room_id]["turn"][i] + dialog
            if len(dialog) > 300:
                break

        prompt = self.training_room[room.room_id]['pre_prompt'] + dialog + "你说：“"
        self.logger.info(prompt)

        for i in range(7):
            #reply = self.yuan.submit_API(prompt, trun="”")
            reply = self.zeus.get_response(prompt)
            if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
                self.logger.warning(f'generation failed {str(i + 1)} times.')
                continue
            if len(reply) <= 5 or reply not in ''.join(self.training_room[room.room_id]['turn']):
                break

        if not reply or reply == "somethingwentwrongwithyuanservice" or reply == "请求异常，请重试":
            self.logger.warning(f'Yuan may out of service, {reply}')
            return

        await room.say(reply)
        intent, conf = self.intent.predict(reply)
        if intent in ['notinterest', 'bye']:
            await room.say('恭喜您，通过测试，成绩为合格，这意味着您可以应付这种情况', [talker.contact_id])
            await room.say(
                f'测试人员：{talker.name} 通过测试，成绩合格，对方最终情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                self.directors)
            self.logger.info(
                f'测试人员：{talker.name} 通过测试，成绩合格，对方最终情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
            del self.training_room[room.room_id]
        elif intent == 'praise':
            await room.say('恭喜您，通过测试，成绩优秀，你不仅应付了局面，居然还能让对方很满意[强]', [talker.contact_id])
            await room.say(
                f'测试人员：{talker.name} 通过测试，成绩优秀，对方最终情绪侦测：{intent}， 对话轮次：{len(self.training_room[room.room_id]["turn"])}',
                self.directors)
            self.logger.info(
                f'测试人员：{talker.name} 通过测试，成绩优秀，对方最终情绪侦测：{intent}，对话轮次：{len(self.training_room[room.room_id]["turn"])}')
            del self.training_room[room.room_id]
        else:
            self.training_room[room.room_id]["turn"].append(f"你说：“{reply}”")
            self.logger.info(f"AI说：“{reply}”")

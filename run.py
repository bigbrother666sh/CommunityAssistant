import asyncio
import os
import sys
from wechaty import Wechaty, WechatyOptions, WechatyPluginOptions

from dotenv import load_dotenv

from antigen_bot.plugins.on_call_notice import OnCallNoticePlugin
from antigen_bot.plugins.watch_room_topic import WatchRoomTopicPlugin
#from antigen_bot.plugins.dynamic_authorization import DynamicAuthorizationPlugin
#from antigen_bot.plugins.ding_dong import DingDongPlugin
# from antigen_bot.plugins.keyword_reply import KeyWordReplyPlugin
from antigen_bot.plugins.qun_assistant import QunAssistantPlugin


async def final_failure_handler(*args, **kwargs):
    sys.exit()


if __name__ == "__main__":
    # load_dotenv()
    options = WechatyOptions(
        port=int(os.environ.get('PORT', 8004)),
    )
    bot = Wechaty(options)
    conv_config_file = '.wechaty/conv2convs_config.xlsx'
    dynamic_plugin = DynamicAuthorizationPlugin(config_file='.wechaty/dynamic_authorise.json', conv_config_file=conv_config_file)
    bot.use([
        DingDongPlugin(),
        CommitteePlugin(),
        MessageForwarderPlugin(
            config_file='.wechaty/message_forwarder_v2.json'
        ),
        MessageForwarderPlugin(
            options=WechatyPluginOptions(name='MessageForwarderTestPlugin'),
            config_file='.wechaty/message_forwarder_test.json'
        ),
        Conv2ConvsPlugin(config_file=conv_config_file, dynamic_plugin=dynamic_plugin),
        dynamic_plugin,
        HealthCheckPlugin(options=HealthCheckPluginOptions(final_failure_handler=final_failure_handler)),
        # KeyWordReplyPlugin(),
    ])
    asyncio.run(bot.start())
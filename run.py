import asyncio
import os
import sys
from wechaty import Wechaty, WechatyOptions, WechatyPluginOptions

from dotenv import load_dotenv

from antigen_bot.plugins.on_call_notice import OnCallNoticePlugin
from antigen_bot.plugins.qun_assistant import QunAssistantPlugin


async def final_failure_handler(*args, **kwargs):
    sys.exit()


if __name__ == "__main__":
    # load_dotenv()
    options = WechatyOptions(
        port=int(os.environ.get('PORT', 8004)),
    )
    bot = Wechaty(options)
    # dynamic_plugin = DynamicAuthorizationPlugin(config_file='.wechaty/dynamic_authorise.json', conv_config_file=conv_config_file)
    bot.use([
        OnCallNoticePlugin(),
        QunAssistantPlugin(),
    ])
    asyncio.run(bot.start())
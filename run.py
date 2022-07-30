import asyncio
import os
import sys
from wechaty import Wechaty, WechatyOptions, WechatyPluginOptions
from antigen_bot.plugins.on_call_notice import OnCallNoticePlugin
from antigen_bot.plugins.qun_assistant import QunAssistantPlugin
from antigen_bot.plugins.lurker import Lurker
from antigen_bot.plugins.training import TrainingPlugin


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
        TrainingPlugin(),
        QunAssistantPlugin(),
        OnCallNoticePlugin(),
        Lurker(),
    ])
    asyncio.run(bot.start())
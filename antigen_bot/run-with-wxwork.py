import asyncio
import os
import sys

from wechaty import Wechaty, WechatyOptions, WechatyPluginOptions
from wechaty_puppet import PuppetOptions

from dotenv import load_dotenv

from antigen_bot.plugins.message_forwarder import MessageForwarderPlugin
from antigen_bot.plugins.conv2convs import Conv2ConvsPlugin
from antigen_bot.plugins.health_check import HealthCheckPlugin, HealthCheckPluginOptions
from antigen_bot.plugins.dynamic_authorization import DynamicAuthorizationPlugin
from antigen_bot.plugins.ding_dong import DingDongPlugin
from antigen_bot.plugins.keyword_reply import KeyWordReplyPlugin


async def final_failure_handler(*args, **kwargs):
    sys.exit()


if __name__ == "__main__":
    load_dotenv()
    options = WechatyOptions(puppet='wechaty-puppet-service',
                             puppet_options=PuppetOptions(token=''))
    bot = Wechaty(options)

    bot.use([
        Conv2ConvsPlugin(config_file=conv_config_file, dynamic_plugin=dynamic_plugin),
        dynamic_plugin,
        HealthCheckPlugin(options=HealthCheckPluginOptions(final_failure_handler=final_failure_handler)),
        KeyWordReplyPlugin(),
        DingDongPlugin(),
    ])
    asyncio.run(bot.start())
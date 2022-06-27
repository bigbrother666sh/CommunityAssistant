import os
import json
from typing import Optional
from wechaty import (
    MessageType,
    WechatyPlugin,
    Message,
    WechatyPluginOptions
)
from wechaty_puppet import get_logger


class Lurker(WechatyPlugin):
    """
    prepare for the CA
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

        with open(os.path.join(self.config_url, 'directors.json'), 'r', encoding='utf-8') as f:
            self.directors = json.load(f)

        if len(self.directors) == 0:
            self.logger.warning('there must be at least one director, pls retry')
            raise RuntimeError('CA director.json not valid, pls refer to above info and try again')

        with open(os.path.join(self.config_url, 'rooms.json'), 'r', encoding='utf-8') as f:
            self.rooms = json.load(f)

    def _file_check(self) -> bool:
        """check the config file"""
        if "directors.json" not in self.config_files:
            self.logger.warning(f'config file url:/{self.config_url} does not have directors.json!')
            return False

    async def on_message(self, msg: Message) -> None:
        talker = msg.talker()

        # 1. 判断是否是自己发送的消息\weixin service\room message
        if talker.contact_id == msg.is_self() or talker.contact_id == "weixin":
            return

        if msg.type() != MessageType.MESSAGE_TYPE_TEXT:
            return

        # 3. rooms
        if msg.room() and msg.room().room_id in self.rooms:
            self.logger.info(msg.text())

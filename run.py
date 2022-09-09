import asyncio
import os
import sys
from wechaty import Wechaty, WechatyOptions
from antigen_bot.plugins.pangutraining import PanGuTrainingPlugin
from antigen_bot.plugins.lurker import Lurker


async def final_failure_handler(*args, **kwargs):
    sys.exit()

if __name__ == "__main__":
    # load_dotenv()
    options = WechatyOptions(
        port=int(os.environ.get('PORT', 8004)),
    )
    bot = Wechaty(options)
    bot.use([
        PanGuTrainingPlugin(),
        Lurker(),
    ])
    asyncio.run(bot.start())

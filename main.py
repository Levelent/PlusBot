import discord
from discord.ext import commands
from datetime import datetime
from json import loads


def token_retrieve(reference):
    with open("token.json", "r", encoding="utf-8") as file:
        token_dict = loads(file.read())
    return token_dict[reference]


class BotCore(commands.Bot):  # discord.ext.commands.Bot is a subclass of discord.Client
    def __init__(self, **options):
        super().__init__(**options)
        self.start_time = datetime.utcnow()

    async def on_ready(self):
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self, msg):
        if not msg.author.bot and not str(msg.channel.type) == "text":
            await msg.channel.send("Sorry, commands don't work in DMs. Try talking to me on a server instead!")
            return
        if str(msg.guild.me.id) in msg.content.lower() or msg.guild.me.name.lower() in msg.content.lower():
            await msg.add_reaction("\U0001F44B")  # Adds the wave reaction
        await bot.process_commands(msg)


# Initialising the bot client
bot = BotCore(description="A Bot Designed for the r/6thForm Discord.",
              activity=discord.Game("with numbers"),  # "playing" is prefixed at the start of the status
              command_prefix="plus.")
bot.load_extension('plus')
bot.remove_command('help')

# The bot token should be put in api_keys.json
bot.run(token_retrieve("discord"))

import discord
import logging
from discord.ext import commands
from datetime import datetime
from json import load


def token_retrieve(reference):
    with open("token.json", "r", encoding="utf-8") as file:
        token_dict = load(file)
    return token_dict[reference]


class BotCore(commands.Bot):  # discord.ext.commands.Bot is a subclass of discord.Client
    def __init__(self, **options):
        super().__init__(**options)
        self.start_time = datetime.utcnow()

    async def on_ready(self):
        print(f'Logged on as {self.user}!')

    async def on_message(self, msg):
        # Stops users from sending commands in DMs
        if not msg.author.bot and not str(msg.channel.type) == "text":
            await msg.channel.send("Sorry, commands don't work in DMs. Try talking to me on a server instead!")
            return
        # If mentioned in chat, reacts with a wave
        if str(msg.guild.me.id) in msg.content.lower() or msg.guild.me.name.lower() in msg.content.lower():
            await msg.add_reaction('👋')
        await bot.process_commands(msg)


logging.basicConfig(level=logging.INFO)
# Initialising the bot client
bot = BotCore(description="Florin would be proud.",
              activity=discord.Game("with numbers"),  # "playing" is prefixed at the start of the status
              command_prefix="plus.")
bot.load_extension('plus')
bot.remove_command('help')

# The bot token should be put in api_keys.json
bot.run(token_retrieve("discord"))

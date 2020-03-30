from discord.ext import commands, tasks
from discord import Embed
from discord.errors import NotFound
from json import load, dumps
from asyncio import sleep
from time import time


# Note that the Message ID has to be stored as a string.
def get_all_data():
    with open("data.json") as data_f:
        return load(data_f)


def update_data(data):
    with open("data.json", "w") as data_f:
        data_f.write(dumps(data))


# Only counts messages created in the last X days.
def get_recent_data(days):
    data = get_all_data()
    msg_data = data["messages"]
    msg_data_new = {}
    for key, value in msg_data.items():
        unix_now = int(time())
        if (unix_now - key["unix_timestamp"]) < (days * 86400):  # The number of seconds per day
            msg_data_new[key] = value

    return {"messages": msg_data_new, "users": data["users"]}


def get_settings():
    with open("settings.json") as set_f:
        s_data = set_f
    return load(s_data)


def update_settings(s_data):
    with open("settings.json", "w") as set_f:
        set_f.write(dumps(s_data))


class Plus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        s_data = get_settings()
        # These properties can be modified in the script.
        self.chl_id = s_data["chl_id"]
        self.threshold = s_data["threshold"]
        self.emote = s_data["emote"]

        # These properties will be uploaded to 'data.json' periodically
        self.message_store = {}  # '<msg id>': ('timestamp': <unix time int>, 'reacts': <star num>)
        self.user_store = {}

        self.update_stores()
        self.data_transfer.start()

    def update_stores(self):
        data = get_recent_data(14)
        self.message_store = data["messages"]
        self.user_store = data["users"]

    # Grabs previous data from file, updates and writes back to file.
    @tasks.loop(minutes=5)
    async def data_transfer(self):
        data = get_all_data()

        msg_data = data["messages"]
        for key, value in self.message_store.items():
            msg_data[key] = value

        user_data = data["users"]
        for key, value in self.user_store.items():
            user_data[key] = value

        combine = {"messages": msg_data, "users": user_data}
        update_data(combine)

    @data_transfer.before_loop
    async def before_transfer(self):
        await self.bot.wait_until_ready()
        await sleep(120)

    def get_emote(self):
        if isinstance(self.emote, int):
            return self.bot.get_emoji(self.emote)
        return self.emote

    # Only cares about messages in the last 14 days
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # TODO: Solve duplicate glitch
        emote = self.get_emote()

        if reaction.emoji != emote or self.chl_id is None or user.bot:
            return

        print(f"Got: {reaction}")

        if reaction.message.id in self.message_store:

            msg_tuple = self.message_store[reaction.message.id]
            star_msg = await self.bot.get_channel(self.chl_id).fetch_message(self.message_store[reaction.message.id][0])
            num = reaction.count
            if self.bot.get_user(self.message_store[reaction.message.id][1]) in await reaction.users().flatten():
                num -= 1
            await star_msg.edit(content=f" {str(emote)} **{num}** | {reaction.message.channel.mention}")
            return

        num = reaction.count
        print(num)
        if reaction.message.author in await reaction.users().flatten():
            num -= 1
        print(num)

        if num >= self.threshold:
            await self.make_new(reaction.message)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        # TODO: sort out what happens when a user removes a reaction
        # Note: it might disappear from starboard, or not at all if it's the message author!
        pass

    @commands.Cog.listener()
    async def on_reaction_clear(self, message, reactions):
        # TODO: this is probably one of the nicer cases to deal with
        pass

    async def make_new(self, react_msg):
        em = Embed(colour=0x8B008B,
                   description=f"[[Jump to original]({react_msg.jump_url})]\n\n{react_msg.content}")
        em.set_author(name=str(react_msg.author), icon_url=react_msg.author.avatar_url)

        # What if it's not an image?
        if len(react_msg.attachments) != 0:
            attachments = react_msg.attachments
            em.set_image(url=attachments[0].url)

        emote_num = self.threshold
        out_chl = self.bot.get_channel(self.chl_id)
        out_msg = await out_chl.send(f" {self.get_emote()}**{emote_num}** | {react_msg.channel.mention}", embed=em)

        msg_obj = {"star_msg_id": out_msg.id, "user_id": react_msg.author.id, "unix_timestamp": int(time())}
        self.message_store[react_msg.id] = msg_obj

    async def update_count(self, react_msg, log_msg):
        pass

    @commands.command()
    @commands.has_guild_permissions(manage_server=True)
    async def updateall(self, ctx):
        emote = self.get_emote()

        messages = {}
        for chl in ctx.guild.text_channels:
            async for msg in chl.history(oldest_first=True):
                for react in msg.reactions:
                    if react.emoji == emote:
                        # Check if there's a self-react
                        id_list = []
                        for user in await react.users().flatten():
                            id_list.append(user.id)
                        self_react_check = msg.author.id in id_list
                        # If self-react, subtract 1 from counter
                        react_num = react.count - self_react_check

                        if react_num >= self.threshold:
                            # Need to put into more permanent structure
                            messages[msg.created_at] = (msg, react_num)
                            break

        for msg in sorted(messages):
            await self.make_new(msg)

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def setchannel(self, ctx, *, target=None):
        if target is None:
            self.chl_id = None
            await ctx.channel.send("Starboard channel removed.")
            return
        if len(ctx.message.channel_mentions) != 1:
            await ctx.channel.send("Channel not found. Make sure you pass through the channel mention, not the name.")
            return
        log_chl = ctx.message.channel_mentions[0]
        self.chl_id = log_chl.id
        await ctx.channel.send(f"Starboard channel updated to: {log_chl.mention}")

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def setthreshold(self, ctx, value="5"):
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Hey, uh, you might want to actually use an integer there.")
            return
        if value < 1:
            await ctx.send(f"Ah yes, a threshold of {value} messages. That makes perfect sense.")
            return
        elif value > 9000000000:
            await ctx.send("What you entered there is literally larger than the population of the earth. Get help.")
        self.threshold = value
        await ctx.channel.send(f"Reaction threshold updated to: {value}")

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def setemote(self, ctx, emote="⭐"):
        if emote.isdigit():
            e = self.bot.get_emoji(int(emote))
            if e is None:
                await ctx.send("The ID entered does not match any custom emote.")
            self.emote = int(emote)
            await ctx.send(f"Set emote to {str(e)}.")
            return

        try:
            await ctx.message.add_reaction(emote)
            self.emote = emote
            await ctx.send(f"Set emote to {self.emote}.")
        except NotFound:
            await ctx.send("What you entered is neither a standard emote, nor a custom emote id.")

    @commands.command()
    async def leaderboard(self, ctx):
        # Todo: Return top X users in embed, should probably take some code snippets from other projects.
        pass


def setup(bot):
    bot.add_cog(Plus(bot))

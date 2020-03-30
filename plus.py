from discord.ext import commands, tasks
from discord import Embed, Member, Object
from discord.errors import NotFound
from json import load, dumps
from asyncio import sleep
from time import time
from typing import Optional


# Note that the Message ID has to be stored as a string.
def get_all_data():
    with open("data.json") as data_f:
        return load(data_f)


def update_data(data):
    with open("data.json", "w") as data_f:
        data_f.write(dumps(data))


# Only counts messages created in the last X days. Gets all users.
def get_recent_data(days):
    data = get_all_data()
    msg_data = data["messages"]
    msg_data_new = {}
    for key, value in msg_data.items():
        print(key)
        print(value)
        unix_now = int(time())
        if (unix_now - value["unix_timestamp"]) < (days * 86400):  # The number of seconds per day
            msg_data_new[key] = value

    return {"messages": msg_data_new, "users": data["users"]}


def get_settings():
    with open("settings.json", encoding="utf8") as set_f:
        s_data = set_f
        return load(s_data)


def update_settings(s_data):
    with open("settings.json", "w", encoding="utf8") as set_f:
        set_f.write(dumps(s_data))


async def true_react_count(reaction):
    self_react_check = reaction.message.author in await reaction.users().flatten()
    # If self-react, subtract 1 (True) from counter
    return reaction.count - self_react_check


class ServerSettings:
    def __init__(self, chl):
        self.channel = chl


class Plus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        s_data = get_settings()
        # These properties can be modified in the script.
        self.chl_id = s_data["chl_id"]
        self.threshold = s_data["threshold"]
        self.emote = s_data["emote"]
        self.remove_deleted = s_data["remove_deleted"]

        # These properties will be uploaded to 'data.json' periodically

        # '<msg id>': {"star_msg_id": <int id>, "user_id": <int id>, "unix_timestamp": <int>, "count": <int>}
        self.message_store = {}

        # '<user id>': {'counted_msgs': [<message ids>], 'total_reacts': <star num>}
        self.user_store = {}  # TODO: Implement user store

        self.update_stores()
        self.data_transfer.start()

    def update_stores(self):
        data = get_recent_data(14)
        self.message_store = data["messages"]
        self.user_store = data["users"]

    def is_remove_deleted(self):
        return self.remove_deleted

    # Grabs previous data from file, updates and writes back to file.
    @tasks.loop(minutes=5)
    async def data_transfer(self):
        # Transfer message data
        data = get_all_data()

        msg_data = data["messages"]
        for key, value in self.message_store.items():
            msg_data[key] = value

        user_data = data["users"]
        for key, value in self.user_store.items():
            # TODO Recalculate numbers from stored messages
            user_data[key] = value

        combine = {"messages": msg_data, "users": user_data}
        update_data(combine)

        # Transfer settings data
        s_data = {
            "chl_id": self.chl_id,
            "threshold": self.threshold,
            "emote": self.emote,
            "remove_deleted": self.remove_deleted
        }
        update_settings(s_data)
        print("Saved data to file.")

    @data_transfer.before_loop
    async def before_transfer(self):
        await self.bot.wait_until_ready()
        await sleep(120)

    def get_emote(self):
        if isinstance(self.emote, int):
            return self.bot.get_emoji(self.emote)
        return self.emote

    async def get_star_msg(self, msg_id):
        star_chl = self.bot.get_channel(self.chl_id)
        if star_chl is None:
            print("!! Starboard Channel Deleted.")
            return None
        try:
            star_msg = await star_chl.fetch_message(msg_id)
        except NotFound:
            print("! Starboard Message Deleted.")
            return None
        return star_msg

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if self.chl_id is None:  # No starboard channel
            return

        emote = self.get_emote()

        if payload.emoji.id != emote.id:  # Incorrect star emote
            return

        # if (payload.message_id) ...
        # TODO: Only care about messages in the last 14 days

        user = self.bot.get_user(payload.user_id)
        if user.bot:  # A bot user
            return

        channel = await self.bot.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        for reaction in message.reactions:
            if reaction.emoji.id == payload.emoji.id:
                await self.reaction_count_handler(reaction, user, emote)
                return
        print("Reaction removed before fetched.")

    async def reaction_count_handler(self, reaction, user, emote):
        count = await true_react_count(reaction)
        print(f"Got reaction {count} from {user} in {str(reaction.message.channel)} on {reaction.message.id}")

        if reaction.message.id in self.message_store:
            print("Updating existing entry")
            msg_dict = self.message_store[reaction.message.id]
            print(msg_dict)

            star_msg = await self.get_star_msg(msg_dict["star_msg_id"])
            if star_msg is None:
                return

            print(f"{msg_dict['count']} -> {count}")
            msg_dict["count"] = count
            await star_msg.edit(content=f"{str(emote)} **{count}** | {reaction.message.channel.mention}")
            return

        # TODO: Solve duplicate bug at threshold?

        if count >= self.threshold:
            print("Making new entry")
            await self.make_new(reaction.message, count)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        # Note: it might disappear from starboard, or not at all if it's the message author! Might also delete entirely.
        # Remove if number of reactions hits drops below threshold.
        stored_count = self.message_store[reaction.message.id]["count"]
        print(f"Removed reaction {stored_count} from {user} in {str(reaction.message.channel)} on {reaction.message.id}")

        if reaction.message.id not in self.message_store:
            return
        count = await true_react_count(reaction)
        if count < self.threshold:
            await self.message_store_remove(reaction.message.id)
        else:
            self.message_store[reaction.message.id]["count"] = count

    async def message_store_remove(self, msg_id):
        # Won't remove anything from store if the message isn't there
        msg_dict = self.message_store.pop(msg_id, None)
        if msg_dict:
            print(f"Message deleted: {msg_dict}")
            star_msg = await self.get_star_msg(msg_dict["star_msg_id"])
            if star_msg is None:
                return
            print(f"Linked Message deleted: {star_msg}")
            await star_msg.delete()

            # Delete the message in the client itself
            # Should also remove in the users where necessary

    @commands.Cog.listener()
    async def on_reaction_clear(self, message, _):  # _ means we ignore the reaction parameter
        await self.message_store_remove(message.message_id)

    @commands.Cog.listener()
    @commands.check(is_remove_deleted)
    async def on_raw_message_delete(self, payload):
        await self.message_store_remove(payload.message_id)

    @commands.Cog.listener()
    @commands.check(is_remove_deleted)
    async def on_raw_bulk_message_delete(self, payload):
        for msg_id in payload.message_ids:
            await self.message_store_remove(msg_id)

    async def make_new(self, react_msg, count: int):
        size_limit = min(len(react_msg.content), 2000)
        em = Embed(
            colour=0x0a9231,
            description=f"{react_msg.content[:size_limit]}\n\n[[Jump to original]({react_msg.jump_url})]",
            timestamp=react_msg.created_at
        )
        em.set_author(name=str(react_msg.author), icon_url=react_msg.author.avatar_url)

        if len(react_msg.attachments) != 0:
            attachments = react_msg.attachments
            # TODO: What if it's not an image?
            em.set_image(url=attachments[0].url)

        out_chl = self.bot.get_channel(self.chl_id)

        out_msg = await out_chl.send(f" {self.get_emote()} **{count}** | {react_msg.channel.mention}", embed=em)

        msg_obj = {
            "star_msg_id": out_msg.id,
            "user_id": react_msg.author.id,
            "unix_timestamp": int(react_msg.created_at.timestamp()),
            "count": count
        }
        print(f"Created {int(react_msg.created_at.timestamp())} in {react_msg.channel.name} | {count}")
        self.message_store[react_msg.id] = msg_obj

        return out_msg

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def catchup(self, ctx, after_id: int = None):
        emote = self.get_emote()

        if after_id is None:
            after = None
        else:
            after = Object(after_id).created_at

        messages = []
        for chl in ctx.guild.text_channels:
            print(chl.name)
            async for msg in chl.history(limit=None, after=after, oldest_first=True):
                for react in msg.reactions:
                    if react.emoji == emote:
                        # Check if there's a self-react
                        self_react_check = msg.author in await react.users().flatten()
                        # If self-react, subtract 1 from counter
                        react_num = react.count - self_react_check

                        if react_num >= self.threshold:
                            print(react_num)
                            # TODO: Need to put into more permanent structure
                            messages.append((int(msg.created_at.timestamp()), msg, react_num))
                        break

        print(f"{len(messages)} messages total")
        for _, msg, react_num in sorted(messages, key=lambda item: item[0]):
            await self.make_new(msg, react_num)

    @commands.command(name="channel")
    @commands.has_guild_permissions(manage_messages=True)
    async def set_channel(self, ctx, *, target=None):
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

    @commands.command(name="threshold")
    @commands.has_guild_permissions(manage_messages=True)
    async def set_threshold(self, ctx, value="5"):
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Hey, uh, you might want to actually use an integer there.")
            return
        if value < 1:
            await ctx.send(f"Ah yes, a threshold of {value} messages. That makes perfect sense.")
            return
        self.threshold = value
        await ctx.channel.send(f"Reaction threshold updated to: {value}")

    @commands.command(name="emote")
    @commands.has_guild_permissions(manage_messages=True)
    async def set_emote(self, ctx, emote="⭐"):
        if emote.isdigit():
            e = self.bot.get_emoji(int(emote))
            if e is None:
                await ctx.send("The ID entered does not match any custom emote.")
                return
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
    async def stats(self, _, target_user: Optional[Member] = None):
        # TODO If no arguments, return top X users by 'stars', and top X 'starred' messages (only the IDs).
        if target_user is None:

            return

        # TODO If a user ID is passed, return top X starred messages of the user, with total emote count
        pass


def setup(bot):
    bot.add_cog(Plus(bot))

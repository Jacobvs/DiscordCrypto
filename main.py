import json
from typing import Dict, List, Set, Union

import aiomysql
import discord
import logging
import urllib3
import os
import datetime
from discord.ext import commands, tasks
from dotenv import load_dotenv
import sql
from cogs.log import verify_log, VerifyAction

load_dotenv()

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)
urllib3.disable_warnings()

intents = discord.Intents.default()
intents.members = True
intents.typing = False
intents.presences = False

token = os.getenv('DISCORD_TOKEN')


def get_prefix(client, message):
    """Returns the prefix for the specified server"""
    if message.guild is None:
        return "!"

    with open('data/prefixes.json', 'r') as f:
        prefixes = json.load(f)

    return prefixes[str(message.guild.id)]

class CryptoBot(commands.Bot):

    def __init__(self):
        super(CryptoBot, self).__init__(command_prefix=get_prefix, intents=intents)

        self.owner_id = 196282885601361920
        self.remove_command("help")

        for filename in os.listdir('./cogs/'):
            if filename.endswith('.py'):
                self.load_extension(f'cogs.{filename[:-3]}')
        self.OCR_TOKEN = os.getenv('OCR_TOKEN')
        self.CMC_TOKEN = os.getenv('CMC_TOKEN')
        self.IMAGEKIT_TOKEN = os.getenv('IMAGEKIT_TOKEN')

        self.start_time: datetime = None
        self.pool: aiomysql.pool = None
        self.variables: Dict[int: Dict[str: Union[bool, int, List[str], Dict[str, discord.Role], Dict[str, discord.TextChannel]]]] = {}
        self.spoken = {}
        self.soft_muted = set([])
        self.sent_messages = {}
        self.banned_photos = set([])
        self.persistent_views_added = False
        self.pending_verification: Set[int] = set([])
        self.adjective_list: Set[str] = set(line.strip() for line in open('data/english-adjectives.txt'))
        self.noun_list: Set[str] = set(line.strip() for line in open('data/english-nouns.txt'))

        with open('data/banned_names.json') as f:
            self.banned_names: dict = json.load(f)

        self.warning_embed = discord.Embed(title="⚠️ Warning!", color=discord.Color.orange())
        self.error_embed = discord.Embed(title="❌ ERROR!", color=discord.Color.red())

        with open('data/variables.json', 'r') as file:
            self.maintenance_mode = json.load(file).get("maintenance_mode")

    async def on_ready(self):
        """Wait until bot has connected to discord"""
        print("Connected to discord")
        self.start_time = datetime.datetime.now()
        self.pool = await aiomysql.create_pool(host=os.getenv("MYSQL_HOST"), port=3306, user='jacobvs', password=os.getenv("MYSQL_PASSWORD"),
                                               db='mysql', loop=bot.loop, connect_timeout=60)
        print("Connected to DB")

        # Cache variables in memory & convert ID's to objects
        self.build_guild_db()

        if not bot.persistent_views_added:
            # Register the persistent view for listening here.
            # Note that this does not send the view to any message.
            # In order to do this you need to first send a message with the View, which is shown below.
            # If you have the message_id you can also pass it as a keyword argument, but for this example
            # we don't have one.
            from views.verify_view import VerifyView
            self.add_view(VerifyView(bot))
            self.persistent_views_added = True

        for g in bot.guilds:
            self.spoken[g.id] = set()

        data = await sql.get_all_logs(bot.pool)
        for record in data:
            if record[sql.log_cols.msg_count] > 0:
                self.spoken.get(record[sql.log_cols.gid], set()).add(record[sql.log_cols.uid])
            if record[sql.log_cols.banned_photo]:
                self.banned_photos.add((record[sql.log_cols.gid], record[sql.log_cols.photo_hash]))

        try:
            await self.cleanup()
        except BaseException:
            pass

        update_msg_counts.start()

        # Set Presence to reflect bot status
        if self.maintenance_mode:
            await self.change_presence(status=discord.Status.idle, activity=discord.Game("IN MAINTENANCE MODE!"))
        else:
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"!help"))

        with open('data/reminders.json') as f:
            reminders = json.load(f)
            for gid in reminders:
                name = reminders[gid]['name']
                photo = reminders[gid]['photo']
                for uid in reminders[gid]:
                    if uid.isdigit():
                        user = self.get_user(int(uid))
                        if user and reminders[gid] and reminders[gid][uid]:
                            for r in reminders[gid][uid]:
                                from cogs import tools
                                total_seconds = (datetime.datetime.utcfromtimestamp(int(r[0])) - datetime.datetime.utcnow()).total_seconds()
                                self.loop.create_task(tools.reminder(user, gid, name, photo, total_seconds, r[1], r[2], r[3], r[4]))

        print(f'{bot.user.name} is now online!')

    def build_guild_db(self):
        with open("data/variables.json", "r") as f:
            data = json.load(f)

        for g in data:
            try:
                guild = self.get_guild(int(g))
                if guild is None:
                    continue
            except ValueError:
                continue

            variables = {}
            for record in data[g]:
                if record == 'roles':
                    for obj in data[g][record]:
                        try:
                            _role = guild.get_role(int(data[g][record][obj]))
                        except ValueError:
                            _role = None
                        variables[obj] = _role
                elif record == 'channels':
                    for obj in data[g][record]:
                        try:
                            _channel = guild.get_channel(int(data[g][record][obj]))
                        except ValueError:
                            _channel = None
                        variables[obj] = _channel
                else:
                    variables[record] = data[g][record]

            self.variables[int(g)] = variables

    async def cleanup(self):
        for g in self.guilds:
            if g.id in self.variables:
                data = self.variables[g.id]
                # Cleanup captcha channel
                captcha_channel = data['captcha_channel']
                no_older_than = datetime.datetime.utcnow() - datetime.timedelta(days=14) + datetime.timedelta(seconds=1)

                def check(msg):
                    return not msg.pinned

                await captcha_channel.purge(check=check, after=no_older_than, bulk=True)

        from cogs.verification import Verification
        verify_cog = Verification(self)
        num = 0

        for m in self.get_all_members():
            if not m.bot:
                temp_role: discord.Role = self.variables[m.guild.id]['temporary_role']
                if len(m.roles) == 1 and not m.pending:
                    await verify_log(self, m, VerifyAction.COMPLETE_SCREENING)
                    await m.add_roles(temp_role)

                if temp_role in m.roles:
                    num += 1
                    self.loop.create_task(verify_cog.recheck_verification(m))

        print(f"# Users without roles: {num}")


bot = CryptoBot()


@bot.command(usage="load <cog>")
@commands.is_owner()
async def load(ctx, extension):
    """Load specified cog"""
    extension = extension.lower()
    bot.load_extension(f'cogs.{extension}')
    await ctx.send('{} has been loaded.'.format(extension.capitalize()))


@bot.command(usage="unload <cog>")
@commands.is_owner()
async def unload(ctx, extension):
    """Unload specified cog"""
    extension = extension.lower()
    bot.unload_extension(f'cogs.{extension}')
    await ctx.send('{} has been unloaded.'.format(extension.capitalize()))


@bot.command(usage="reload <cog/guilds/utils/all>")
@commands.is_owner()
async def reload(ctx, extension):
    """Reload specified cog"""
    extension = extension.lower()
    if extension == 'guilds':
        bot.build_guild_db()
        extension = 'Guild Database'
    else:
        bot.reload_extension(f'cogs.{extension}')
    await ctx.send('{} has been reloaded.'.format(extension.capitalize()))


@bot.command(usage="maintenance")
@commands.is_owner()
async def maintenance(ctx):
    if bot.maintenance_mode:
        bot.maintenance_mode = False
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"!help"))
        await ctx.send("Maintenance mode has been turned off!")
    else:
        bot.maintenance_mode = True
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game("IN MAINTENANCE MODE!"))
        # with open('data/queues.pkl', 'wb') as file:
        #     pickle.dump(bot.queues, file, pickle.HIGHEST_PROTOCOL)
        #
        # print('Saved queue to file')
        await ctx.send("Maintenance mode has been turned on!")
    with open("data/variables.json", 'r+') as f:
        data = json.load(f)
        data["maintenance_mode"] = bot.maintenance_mode
        f.seek(0)
        json.dump(data, f)
        f.truncate()


@bot.check
async def maintenance_mode(ctx):
    if bot.maintenance_mode:
        if await bot.is_owner(ctx.author):
            return True
        embed = discord.Embed(title="Error!", description="Cryptographer has been put into maintenance mode by the developer! "
                                                          "This means bugs are being fixed or new features are being added.\n"
                                                          "Please be patient and if this persists for too long, contact <@196282885601361920>.",
                              color=discord.Color.orange())
        await ctx.send(embed=embed)
        return False
    return True


@bot.check
async def bot_channel(ctx):
    db = ctx.bot.variables.get(ctx.guild.id)
    if ctx.command.name in db['bot_channel_only']:
        channel = db['bots_channel']
        if channel and ctx.channel != channel:
            ctx.command.reset_cooldown(ctx)
            await ctx.send(f"This command can only be used in {channel.mention}. Please re-run the command there.", delete_after=30)
            return False
    return True


@tasks.loop(minutes=5)
async def update_msg_counts():
    print(f"Updating message counts! {len(bot.sent_messages)} new changes!")
    data = [(v, k[0], k[1]) for k, v in bot.sent_messages.items()]
    if len(data) > 200:
        bot.sent_messages = {}
        async with bot.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "UPDATE crypto.logging SET msg_count = msg_count + %s WHERE gid = %s AND uid = %s"
                await cursor.executemany(sql, data)
                await conn.commit()


print("Attempting to connect to Discord")
bot.run(token)

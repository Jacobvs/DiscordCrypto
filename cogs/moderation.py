import asyncio
import datetime
import difflib
import json
import logging
import textwrap
from collections import Counter, OrderedDict

import aiohttp
import discord
from discord.ext import commands
from unidecode import unidecode

import checks
import sql
import utils


logger = logging.getLogger('discord')


class Moderation(commands.Cog):
    """Commands for user/server management"""

    def __init__(self, client):
        self.client = client

    @commands.command(usage='listall <role>', description="List all members with a role")
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), checks.is_staff_check())
    async def listall(self, ctx, role: discord.Role, mention: str = ""):
        if mention:
            nsections = int(len(role.members)/20)-1
            embed = discord.Embed(title=f"Members with the role: {role.name}", color=role.color)
            for i in range(nsections):
                embed.add_field(name="Members", value="".join([m.mention for m in role.members[20*i:20*(i+1)]]), inline=False)
            await ctx.send(embed=embed)
        else:
            mstrs = []
            for m in role.members:
                if " | " in m.display_name:
                    mstrs.extend(m.display_name.split(" | "))
                else:
                    mstrs.append(m.display_name)
            str = f"[{', '.join([''.join([c for c in m if c.isalpha()]) for m in mstrs])}]"
            await ctx.send(str)

    @commands.command(usage="listvc", description="Return a list of people in a VC")
    @commands.guild_only()
    @checks.is_staff_check()
    async def listvc(self, ctx):
        if not ctx.author.voice:
            return await ctx.send("You must be in a VC to use this command!")

        mstrs = []
        for m in ctx.author.voice.channel.members:
            if " | " in m.display_name:
                mstrs.extend(m.display_name.split(" | "))
            else:
                mstrs.append(m.display_name)
        str = '["' + '", "'.join([''.join([c for c in m if c.isalpha()]) for m in mstrs]) + '"]'
        await ctx.send(str)

    @commands.command(usage="change_prefix <prefix>", description="Change the bot's prefix for all commands.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def change_prefix(self, ctx, prefix):
        with open('data/prefixes.json', 'r') as file:
            prefixes = json.load(file)

        prefixes[str(ctx.guild.id)] = prefix

        with open('data/prefixes.json', 'w') as file:
            json.dump(prefixes, file, indent=4)

        await ctx.send(f"The prefix for this server has been changed to '{prefix}'.")

    @commands.command(usage="find <nickname>", description="Find a user by the specified nickname.")
    @commands.guild_only()
    @checks.is_staff_check()
    async def find(self, ctx, member):
        member = await utils.MemberLookupConverter().convert(ctx, member)

        if member.voice is None:
            vc = '❌'
        else:
            vc = f"`{member.voice.channel.name}`"

        desc = f"Found {member.mention} with the name: __{member.display_name}__)\nVoice Channel: {vc}"

        embed = discord.Embed(description=desc, color=discord.Color.green())

        embed.add_field(name="Punishments:", value="No punishment or blacklist logs found!")
        await ctx.send(embed=embed)

    @commands.command(usage='testdm <member> <msg>', description='Test sending a dm to specified member')
    @commands.is_owner()
    async def testdm(self, ctx, member: discord.Member, *, message):
        try:
            await member.send(content=message)
        except discord.Forbidden:
            await ctx.send("FORBIDDEN!")

    @commands.command(usage='testrole <member> <msg>', description='Test adding & removing roles from a member')
    @commands.is_owner()
    async def testrole(self, ctx, member: discord.Member, role: discord.Role, ntimes:int=100):
        ntimes = 100 if ntimes > 100 else 20 if ntimes < 20 else ntimes
        for i in range(ntimes):
            await member.add_roles(role)
            await member.remove_roles(role)
            if i % 10 == 0:
                await ctx.send(f'{i}/{ntimes}')

    @commands.command(usage='changename <member> <newname>', description="Change the users name.")
    @commands.guild_only()
    @checks.is_staff_check()
    async def changename(self, ctx, member: utils.MemberLookupConverter, newname):
        embed = None
        try:
            await member.edit(nick=newname)
        except discord.Forbidden:
            embed = discord.Embed(title="Error!", description=f"There was an error changing this person's name in {ctx.guild.name} (Perms).\n"
                                                              f"Please change their nickname to this manually: ` {newname} `", color=discord.Color.red())

        if embed is None:
            embed = discord.Embed(title="Success!", description=f"`{newname}` is now the name of {member.mention}.",
                                  color=discord.Color.green())
        return await ctx.send(embed=embed)


    # @commands.command(usage='ban <member>', description="Ban a member from the server")


    # @commands.command(usage='addalt <member> <altname>', description="Add an alternate account to a user (limit 2).")
    # @commands.guild_only()
    # @checks.is_staff_check()
    # async def addalt(self, ctx, member: utils.MemberLookupConverter, altname):
    #
    #     name = member.display_name
    #
    #     name += f" | {altname}"
    #     try:
    #         await member.edit(nick=name)
    #     except discord.Forbidden:
    #         return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
    #                               f"Please copy this and set their nickname manually: `{name}`\n{member.mention}")
    #
    #     embed = discord.Embed(title="Success!", description=f"`{altname}` was added as an alt to {member.mention}.",
    #                           color=discord.Color.green())
    #     await ctx.send(embed=embed)
    #
    # @commands.command(usage='removealt <member> <altname>', description="Remove an alt from a player.")
    # @commands.guild_only()
    # @checks.is_staff_check()
    # async def removealt(self, ctx, member: utils.MemberLookupConverter, altname):
    #     clean_names = []
    #     if altname.lower() in member.display_name.lower():
    #         names = member.display_name.split(" | ")
    #         for n in names:
    #             if n.lower() != altname.lower():
    #                 clean_names.append(n)
    #     nname = " | ".join(clean_names)
    #
    #     try:
    #         await member.edit(nick=nname)
    #     except discord.Forbidden:
    #         return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
    #                               f"Please copy this and replace their nickname manually: ` | {nname}`\n{member.mention}")
    #
    #     embed = discord.Embed(title="Success!", description=f"`{altname}` was removed as an alt to {member.mention}.",
    #                           color=discord.Color.green())
    #     await ctx.send(embed=embed)

    @commands.command(usage="purge <num> [filter_type: all / contains / from] [filter: 'word' / 'sentence or words' / @member]",
                      description="Removes [num] messages from the channel\nTo delete all messages do: `purge <num> all`\nTo delete messages containing words or a sentence do: "
                                  "`purge <num> contains 'word'` or `purge <num> contains 'sentence to search'`\nTo purge messages from a member do: `purge <num> from @member`")
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_messages=True), commands.is_owner())
    async def purge(self, ctx, num=5, type=None, filter=None):
        num += 1
        if not isinstance(num, int):
            await ctx.send("Please pass in a number of messages to delete.")
            return

        no_older_than = datetime.datetime.utcnow() - datetime.timedelta(days=14) + datetime.timedelta(seconds=1)
        if type:
            type = type.lower()
            if type == 'all':
                def check(msg):
                    return True
            elif type == 'contains':
                def check(msg):
                    return str(filter).lower() in msg.content.lower()
            elif type == 'from':
                try:
                    converter = discord.ext.commands.UserConverter()
                    mem = await converter.convert(ctx, filter)
                except discord.ext.commands.BadArgument as e:
                    return ctx.send(f"No members found with the name: {filter}")

                def check(msg):
                    return msg.author == mem
            else:
                return await ctx.send(f'`{type}` is not a valid filter type! Please choose from "all", "contains", "from"')
        else:
            def check(msg):
                return not msg.pinned

        messages = await ctx.channel.purge(limit=num, check=check, after=no_older_than, bulk=True)
        # if len(messages) < num:
        #     return await ctx.send("You are trying to delete messages that are older than 15 days. Discord API doesn't "
        #                           "allow bots to do this!\nYou can use the nuke command to completely clean a "
        #                           "channel.", delete_after=10)
        await ctx.send(f"Deleted {len(messages) - 1} messages.", delete_after=5)

    @commands.command(usage='nuke', description="Deletes all the messages in a channel.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx, confirmation=""):
        if confirmation == "I confirm this action.":
            newc = await ctx.channel.clone()
            await newc.edit(position=ctx.channel.position)
            await ctx.channel.delete()
        else:
            return await ctx.send('Please confirm you would like to do this by running: `!nuke "I confirm this '
                                  'action."`\n**__THIS WILL DELETE ALL MESSAGES IN THE CHANNEL!__**')

    @commands.command(usage='findduplicates [num_repeats]', description="Find accounts that have duplicate names in the server over specified threshold.")
    @commands.guild_only()
    @checks.is_staff_check()
    async def findduplicates(self, ctx, num: int = 5):
        if num < 4:
            return await ctx.send("Please specify a number higher than 3!")

        duplicates = [f"{m} –– **{v}** duplicates\n" for m, v in Counter([unidecode(m.name) for m in ctx.guild.members]).items() if v > num]
        # for r in duplicates:
        #     similar = difflib.get_close_matches(r, duplicates, cutoff=0.75)
        #     if similar:
        #         final.remove()

        embed = discord.Embed(title=f"Found {len(duplicates)} duplicated names!", color=discord.Color.green())
        desc = "".join(duplicates)
        if desc:
            lines = textwrap.wrap(desc, width=1024, replace_whitespace=False, break_on_hyphens=False)  # Wrap message before max len of field of 1024
            for i, l in enumerate(lines, start=1):
                embed.add_field(name=f"Names: ({i}/{len(l)})", value=l, inline=False)
        else:
            embed.description = "No Duplicated names with an occurence of >{num} were found!"
        await ctx.send(embed=embed)
        for r in duplicates:
            if len(r.split(' ––')[0]) < 4:
                await ctx.send(f"Short name: `{r.split(' ––')[0]}` | {r.split(' –– ')[1]}")

    @commands.command(usage='finduzero', description='Find members with fully unicode names.')
    @checks.is_staff_check()
    async def finduzero(self, ctx):
        await ctx.send("".join([m.mention for m in ctx.guild.members if len(unidecode(m.name)) == 0]))

    @commands.command(usage='finduniname <name>', description="Find member searching by unicode character replacement.")
    @checks.is_staff_check()
    async def finduniname(self, ctx, *, name):
        nicks = []
        map = {}
        for m in ctx.guild.members:
            n = unidecode(m.name)
            nicks.append(n)
            map[n] = m
        matches = difflib.get_close_matches(name, nicks, cutoff=0.15)
        print(f"Uni Matches: {matches}")
        if matches:
            await ctx.send("".join([map.get(m).mention for m in matches]))
        else:
            await ctx.send("No matches found!")


    @commands.command(usage='softmute <member> <time>', description="Mark messages from a user as a spoiler for specified time", aliases=['smute'])
    @commands.guild_only()
    @checks.is_staff_check()
    async def softmute(self, ctx, member: utils.MemberLookupConverter, duration: utils.Duration):
        total_seconds = (duration - datetime.datetime.utcnow()).total_seconds()

        if member.bot:
            return await ctx.send(f'Cannot soft-mute `{member.display_name}` (is a bot).')
        if ctx.author.id != self.client.owner_id:
            if member.guild_permissions.manage_guild and ctx.author.id not in self.client.owner_ids:
                return await ctx.send(f'Cannot soft-mute `{member.display_name}` due to roles.')
        if (member.id, ctx.guild.id) in self.client.soft_muted:
            return await ctx.send(f"{member.display_name}__ is already Soft-Muted! Use `{ctx.prefix}rsoftmute <member>` to remove their soft-mute.")

        self.client.soft_muted.add((member.id, ctx.guild.id))
        await ctx.send(f"__{member.display_name}__ was Soft-Muted! {utils.duration_formatter(total_seconds, 'Soft-Mute')}")

        await asyncio.sleep(total_seconds)
        if (member.id, ctx.guild.id) in self.client.soft_muted:
            self.client.soft_muted.remove((member.id, ctx.guild.id))
            await ctx.send(f"\n__{member.display_name}__ was automatically removed from their Soft-Mute.")

    @commands.command(usage='rsoftmute <member>', description="Remove a member from their soft-mute", aliases=['rsmute'])
    @commands.guild_only()
    @checks.is_staff_check()
    async def rsoftmute(self, ctx, member: utils.MemberLookupConverter):
        if (member.id, ctx.guild.id) not in self.client.soft_muted:
            return await ctx.send(f"{member.display_name}__ is not currently Soft-Muted!")

        self.client.soft_muted.remove((member.id, ctx.guild.id))
        await ctx.send(f"__{member.display_name}__ was removed from their Soft-Mute!")

    @commands.command(usage='unban <ID>', description='Unban a specified user/id')
    @commands.guild_only()
    @checks.is_staff_check()
    async def unban(self, ctx, user: discord.User):
        await ctx.guild.unban(user=user, reason=f"Unban command execution by: {ctx.author.name}")
        await ctx.send(embed=discord.Embed(title="Success!",
                                           description=f"{user.mention} ({user.name}#{user.discriminator}) was successfully unbanned.", color=discord.Color.green()))


    @commands.command(usage='cleancaptcha', description='Clean up captcha channel.')
    @commands.guild_only()
    @checks.is_staff_check()
    async def cleancaptcha(self, ctx):

        tasks = asyncio.all_tasks(self.client.loop)
        print(tasks)


        # m = await ctx.send("Purging Captcha channel & sending new verification requests! Please Wait...")
        #
        # await main.cleanup()

    @commands.command(usage="cleanreports", description="Clean up spam reports channel, moving resolved cases to log channel")
    @commands.guild_only()
    @checks.is_staff_check()
    async def cleanreports(self, ctx):
        reports_channel = self.client.variables[ctx.guild.id]['spam_reports']
        if not reports_channel:
            return await ctx.send("Error! No configured spam reports channel!")

        log_channel = self.client.variables[ctx.guild.id]['log_channel']

        async for message in reports_channel.history():
            if message.author == self.client.user:
                if message.embeds:
                    embed = message.embeds[0]
                    if "Resolved" in embed.title:
                        try:
                            await log_channel.send(embed=embed)
                            await message.delete()
                        except discord.DiscordException:
                            pass

        await ctx.send("Success! Messages were successfully cleaned from the reports-channel.")


    @commands.command(usage="findwordlist [suppress_embeds?: true/false]", description="Find members matching wordlist naming pattern")
    @commands.guild_only()
    @checks.is_staff_check()
    async def findwordlist(self, ctx, suppress=False):
        mems = []
        new_mems = []
        for m in ctx.guild.members:
            # if m.name.istitle():
            #     words = m.name.lower().split()
            #     if words[0] in self.client.adjective_list or (len(words) == 2 and words[1] in self.client.noun_list):
            #         hours, rem = divmod((datetime.datetime.utcnow() - m.created_at).total_seconds(), 3600)
            #         if hours < 12:
            #             new_mems.append(m)
            #         else:
            #             mems.append(m)
            if m.name[-1].isdigit():
                words = m.name[:-1]
                index = None

                for i, c in enumerate(words):
                    if c.isupper():
                        if index is not None:
                            index = None
                            break
                        index = i

                if index:
                    first_word = words[:index]
                    second_word = words[index:].lower()

                    if first_word in self.client.adjective_list and second_word in self.client.noun_list:
                        mems.append(m)

        msg_data = await sql.get_all_logs(self.client.pool)
        msg_data = {r[sql.log_cols.uid]: r[sql.log_cols.msg_count] for r in msg_data if r[sql.log_cols.gid] == ctx.guild.id}
        no_messages = [m for m in mems if msg_data.get(m.id, 0) == 0]
        no_messages_12 = [m for m in new_mems if msg_data.get(m.id, 0) == 0]
        one_message = [m for m in mems if msg_data.get(m.id, 0) == 1]

        if not suppress:
            both = no_messages
            both.extend(one_message)
            lines = textwrap.wrap("".join([m.mention for m in both]), width=2000)
            for l in lines:
                await ctx.send(l, delete_after=0.01)


            base_embed = discord.Embed(title=f"Results (0 Messages)", description=f"Members with wordlist name matches & no sent messages:\n__**{len(no_messages)}** members.__",
                                  color=discord.Color.blue())
            embed = base_embed
            lines = textwrap.wrap(' | '.join([m.mention for m in no_messages]), width=1024)
            for i, l in enumerate(lines, start=1):
                if len(embed) + len(l) > 6000:
                    await ctx.send(embed=embed)
                    embed.description = ""
                    embed.clear_fields()
                embed.add_field(name=f"Names: ({i}/{len(lines)})", value=l, inline=False)

            await ctx.send(embed=embed)

            embed = discord.Embed(title="Results (1 Message)", description=f"Members with wordlist name matches & 1 sent message:\n__**{len(one_message)}** members.__",
                                  color=discord.Color.blue())

            lines = textwrap.wrap(' | '.join([m.mention for m in one_message]), width=1024)
            for i, l in enumerate(lines, start=1):
                if len(embed)+ len(l) > 6000:
                    if len(embed) + len(l) > 6000:
                        await ctx.send(embed=embed)
                        embed.description = ""
                        embed.clear_fields()
                embed.add_field(name=f"Names: ({i}/{len(lines)})", value=l, inline=False)

            await ctx.send(embed=embed)

        default_0 = [m for m in no_messages if m.avatar == m.default_avatar]
        default_1 = [m for m in one_message if m.avatar == m.default_avatar]


        await ctx.send(f"Wordlist name detection sums:\n**{len(no_messages)}** members with no messages\n**{len(one_message)}** members with 1 message"
                       f"\n\n**{len(default_0)}** members with no messages & default pfp\n**{len(default_1)}** members with 1 message & default pfp"
                       f"\n**{len(new_mems)}** members with account creation newer than 12 hours")

        embed = discord.Embed(title="Actions:", description="1️⃣ - to KICK all accounts with 0 messages.\n2️⃣ - to KICK all accounts with 0 messages & default pfp"
                                                            "\n3️⃣ - to KICK all accounts <12 hours old.\n4️⃣ - to BAN all accounts with 0 messages.\n5️⃣- to BAN all accounts "
                                                            "with 0 messages & default pfp\n\n❌ - to take no "
                                                            "actions",
                              color=discord.Color.orange())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("1️⃣")
        await msg.add_reaction("2️⃣")
        await msg.add_reaction("3️⃣")
        await msg.add_reaction("4️⃣")
        await msg.add_reaction("5️⃣")
        await msg.add_reaction("❌")

        should_ban = False

        def check(payload):
            return payload.user_id == ctx.author.id and payload.message_id == msg.id and str(payload.emoji) in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "❌"]

        try:
            payload = await self.client.wait_for('raw_reaction_add', timeout=10800, check=check)  # Wait 1 hr max
            await msg.clear_reactions()
        except asyncio.TimeoutError:
            embed.title = "Timed out!"
            embed.description = f"Timed out! Please run `{ctx.prefix}findwordlist` again to perform actions on these results."
            embed.colour = discord.Color.red()
            return await msg.edit(embed=embed)

        if str(payload.emoji) == "1️⃣":
            kicklist = no_messages
        elif str(payload.emoji) == "2️⃣":
            kicklist = default_0
        elif str(payload.emoji) == "3️⃣":
            kicklist = new_mems
        elif str(payload.emoji) == "4️⃣":
            kicklist = no_messages
            should_ban = True
        elif str(payload.emoji) == "5️⃣":
            kicklist = default_0
            should_ban = True
        else:
            return await msg.delete()

        embed.title = f"{'Banning' if should_ban else 'Kicking'}... (0/{len(kicklist)})"
        embed.description = f"{'Banning' if should_ban else 'Kicking'} members "
        embed.description += "with 0 messages and default profile photos." if str(payload.emoji) in ["1️⃣", "2️⃣"] else "with an account creation date <12 hours old."
        embed.description += "\nPlease wait... This can take a few minutes to complete."
        embed.colour = discord.Color.gold()
        await msg.edit(embed=embed)
        # kick members here
        for i, m in enumerate(kicklist, start=1):
            if i % 100 == 0:
                embed.title = f"{'Banning' if should_ban else 'Kicking'}... ({i}/{len(kicklist)})"
                await msg.edit(embed=embed)
            if should_ban:
                await m.ban(reason=f"Name matching wordlist & {'account creation <12h' if str(payload.emoji) == '3️⃣' else 'no messages sent'} (Suspected Bot)")
            else:
                await m.kick(reason=f"Name matching wordlist & {'account creation <12h' if str(payload.emoji) == '3️⃣' else 'no messages sent'} (Suspected Bot)")

        embed.title = "Success!"
        embed.description = f"__**{len(kicklist)}** members successfully {'banned' if should_ban else 'kicked'}!__\n\nRequested by: {ctx.author.mention} " \
                            f"({ctx.author.display_name}#{ctx.author.discriminator})"
        embed.colour = discord.Color.green()
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)

    async def sync_photo_hashes(self, guild: discord.Guild, channel: discord.TextChannel):
        embed = discord.Embed(title="Fetching Photos From Discord...", description="Please wait while profile photos are retrieved from discord.\n", color=discord.Color.gold())
        embed.add_field(name="Members to be Retrieved:", value=f"{len(guild.members)} members in the server.")
        embed.timestamp = datetime.datetime.utcnow()
        msg = await channel.send(embed=embed)

        await guild.chunk()
        log_data = await sql.get_all_logs(self.client.pool)
        log_uids = {r[1] for r in log_data}
        no_hashes = {r[1] for r in log_data if r[4] is None}
        memlist: list[discord.Member] = [m for m in guild.members if (m.id in no_hashes or m.id not in log_uids) and m.avatar]
        already_hashed = len(log_uids) - len(no_hashes)

        defaults = [(guild.id, m.id, str(m.default_avatar)) for m in guild.members if (m.id in no_hashes or m.id not in log_uids) and not m.avatar]
        print(f"Defaults: {len(defaults)} ({defaults[:1]})")
        if len(defaults) > 0:
            await sql.batch_update_photo_hashes(self.client.pool, defaults)
            already_hashed += len(defaults)

        if len(memlist) == 0:
            await msg.delete()
            return True

        desc = "Please wait while member list is indexed for photo hashes.\nThis can take a long time (Est. 10m for 50,000+ members).\n"
        embed = discord.Embed(title="Checking Image Similarities...",
                              description=desc + utils.textProgressBar(already_hashed, len(memlist) + already_hashed, prefix="Progress: ", suffix="", decimals=2, length=13, fullisred=False),
                              color=discord.Color.orange())
        embed.add_field(name="Members checked:", value=f"**{already_hashed}** / {len(memlist)+already_hashed} members hashed\n__{0}__ matches found.")
        embed.set_thumbnail(url="https://i.imgur.com/nLRgnZf.gif")
        embed.set_footer(text='Elapsed: 0s | Est. Left: Calculating...')
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)


        base_url = "https://api.imagekit.io/v1/metadata?url=https://ik.imagekit.io/ugssigsf4u/avatars"
        ext = ".webp?size=64"
        headers = {'Authorization': f'Basic {self.client.IMAGEKIT_TOKEN}'}

        async def send_request(m: discord.Member, client_session: aiohttp.ClientSession, url: str, rate_limiter: utils.SephamoreRateLimiter):
            async with rate_limiter.throttle():
                response = await client_session.get(url)

            # Why are the following lines not included in the rate limiter context?
            # because all we want to control is the rate of io operations
            # and since the following lines instruct reading the response stream into memory,
            # it shouldn't block the next requests from sending
            # (unless you have limited memory or large files to ingest.
            # In that case you should add it to the context
            # but also make sure you free memory for the next requests)!
            # so we should now release the semaphore and let the
            # stream reading begin async while letting the rest of the requests go on sending
            if response.status == 429:
                rate_limiter.hit_429(response.headers)
                data = None
            elif response.status == 200:
                data = await response.json()
                data = (m.guild.id, m.id, data['pHash'])
            else:
                print(f"ERROR ({response.status} - {response.reason}): {response.url}")
                data = await response.text()
                print(f"Message: {data}")
                data = None
            response.release()

            return m, data

        sql_data: list = []
        start_time = datetime.datetime.utcnow()

        async with utils.SephamoreRateLimiter(rate_limit=10000, concurrency_limit=3000) as rate_limiter:
            async with aiohttp.ClientSession(headers=headers) as cs:
                i = 0

                async def run_tasks(task_list, count, sql_data_list):
                    last_update = 0
                    failed_list = []

                    for future in asyncio.as_completed(task_list):
                        m, data = await future
                        count += 1
                        if data is not None:
                            sql_data_list.append(data)
                        else:
                            failed_list.append(m)

                        if count % 200 == 0:
                            print(f"Updating SQL Hashes ({count})")
                            await sql.batch_update_photo_hashes(self.client.pool, sql_data_list)
                            sql_data_list.clear()

                            elapsed_s = int((datetime.datetime.utcnow() - start_time).total_seconds())
                            if elapsed_s - last_update > 15:
                                last_update = elapsed_s
                                minutes, seconds = divmod(elapsed_s, 60)
                                l_min, l_secs = divmod(int((elapsed_s / count) * len(memlist)), 60)
                                embed.description = desc + utils.textProgressBar(count + already_hashed, len(memlist) + already_hashed, prefix="Progress: ", suffix="", decimals=2, length=13,
                                                                                 fullisred=False)
                                embed.set_footer(text=f'Elapsed: {minutes}m{seconds}s | Est. Left: {l_min}m{l_secs}s')
                                embed.set_field_at(0, name="Members hashes:", value=f"**{count + already_hashed}** / {len(memlist) + already_hashed} members checked\n{len(failed_list)} members "
                                                                                    f"failed to be retrieved.")
                                await msg.edit(embed=embed)

                    return count, sql_data_list, failed_list

                tasks = [send_request(m, client_session=cs, url=url, rate_limiter=rate_limiter) for m, url in
                         [(m, f"{base_url}/{m.id}/{m.avatar}{ext}") for m in memlist]
                         ]
                i, sql_data, failed = await run_tasks(tasks, i, sql_data)
                print("DONE.. Trying failed again.")

                tasks = [send_request(m, client_session=cs, url=url, rate_limiter=rate_limiter) for m, url in
                         [(m, f"{base_url}/{m.id}/{m.avatar}{ext}") for m in failed]
                         ]
                i, sql_data, failed = await run_tasks(tasks, i, sql_data)


        print("Updating Final SQL Hashes")
        await sql.batch_update_photo_hashes(self.client.pool, sql_data)
        print("Done updating.")

        await channel.send("Failed to get:\n" + "".join([m.mention for m in failed]))
        embed = discord.Embed(title="Success!", description=f"Added **{len(memlist)}** profile hashes to the database!", color=discord.Color.blue())
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)
        return True

    @commands.command(usage="photoblacklist <user>")
    @commands.guild_only()
    @checks.is_staff_check()
    async def photoblacklist(self, ctx, user: discord.User):

        if user.avatar == user.default_avatar:
            raise discord.ext.commands.BadArgument(message="Cannot photo-blacklist a user with a default profile photo!")

        res = await self.sync_photo_hashes(ctx.guild, ctx.channel)
        if not res:
            await ctx.send(f"PFP Hashing failed! Results shown may not be fully accurate! Please run `{ctx.prefix}syncphotohashes` to get accurate results.")

        log_data = await sql.get_all_logs(self.client.pool)

        photo_hash = next((r[4] for r in log_data if r[1] == user.id), None)
        if not photo_hash:
            photo_hash = await utils.get_photo_hash(self.client, user)
            if not photo_hash:
                return await ctx.send(f"No PFP Hash for the specified user! Please run `{ctx.prefix}syncphotohashes` to sync this user's profile photo.")
            elif any(r[0] == user.id for r in log_data):
                await sql.update_photo_hash(self.client.pool, user.id, photo_hash, ctx.guild.id, new=False)
            else:
                await sql.update_photo_hash(self.client.pool, user.id, photo_hash, ctx.guild.id)

        log_matches = {r[1] for r in log_data if r[4] and (r[4] == photo_hash or utils.hamming_distance(r[4], photo_hash) < 5)}
        matches = [m for m in ctx.guild.members if m.id in log_matches]

        embed = discord.Embed(title="Success!", description=f"**{len(matches)}** members with identical profile photos found!\n\nTo ban all detected members & __blacklist this "
                                                            f"photo__,\nClick the ✅ to confirm.\nClick the ❌ to ignore this result.", color=discord.Color.green())
        embed.add_field(name="Photo Hash:", value=photo_hash)
        embed.set_thumbnail(url=user.avatar)
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        msg = await ctx.send(embed=embed)
        if len(matches) > 0:
            await ctx.send(f"Example Detections ({'20' if len(matches) > 20 else len(matches)}/{len(matches)}):\n{''.join([m.mention for m in matches[:20]])}")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(payload):
            return payload.user_id == ctx.author.id and payload.message_id == msg.id and str(payload.emoji) in ["✅", "❌"]

        try:
            payload = await self.client.wait_for('raw_reaction_add', timeout=10800, check=check)  # Wait 1 hr max
            await msg.clear_reactions()
        except asyncio.TimeoutError:
            embed.title = "Timed out!"
            embed.description = f"Timed out! Please run `{ctx.prefix}photoblacklist` again to perform any actions."
            embed.colour = discord.Color.red()
            return await msg.edit(embed=embed)

        if str(payload.emoji) == "❌":
            embed.title = "Cancelled!"
            embed.description = f"No members were banned. No photos were added to the blacklist\nPlease run `{ctx.prefix}photoblacklist` again to perform any actions."
            embed.colour = discord.Color.red()
            return await msg.edit(embed=embed)
        else:
            self.client.banned_photos.add((ctx.guild.id, photo_hash))
            await sql.set_banned_photo(self.client.pool, ctx.guild.id, user.id, banned=True)

            matches.append(user)

            embed.title = f"Banning Matches... (0/{len(matches)})"
            embed.description = "Please wait... This can take a few minutes to complete."
            embed.set_thumbnail(url=user.avatar)
            embed.colour = discord.Color.gold()
            await msg.edit(embed=embed)

            # kick members here
            for i, m in enumerate(matches, start=1):
                if i % 10 == 0:
                    embed.title = f"Banning... ({i}/{len(matches)})"
                    await msg.edit(embed=embed)
                await ctx.guild.ban(m, reason=f"PFP matching blacklisted profile photo.")

            embed.title = "Success!"
            embed.description = f"__**{len(matches)}** members successfully banned!__\n\nRequested by: {ctx.author.mention} ({ctx.author.display_name}#{ctx.author.discriminator})"
            embed.colour = discord.Color.green()
            embed.set_footer(text="©Cryptographer")
            embed.timestamp = datetime.datetime.utcnow()
            await msg.edit(embed=embed)


    @commands.command(usage="syncphotohashes", description="Sync all photo hashes for this server.")
    @commands.guild_only()
    @checks.is_staff_check()
    @commands.max_concurrency(1, per=discord.ext.commands.BucketType.guild)
    async def syncphotohashes(self, ctx):
        await self.sync_photo_hashes(ctx.guild, ctx.channel)

    @commands.command(usage="creationdate <user>")
    async def creationdate(self, ctx, user:discord.User):
        elapsed_seconds = (datetime.datetime.utcnow()-user.created_at).total_seconds()

        embed = discord.Embed(description=f"Time since creation: {utils.duration_formatter(elapsed_seconds)}\n\n"
                                          f"Created:{user.created_at.strftime('%b %d %Y %H:%M:%S %p')}", color=discord.Color.green())
        embed.set_author(name=user.name, icon_url=user.avatar)
        embed.set_thumbnail(url=user.avatar)
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=embed)

    # @commands.command(usage='pban <user> <reason>')
    # @commands.is_owner()
    # async def pban(self, ctx, user: discord.User, *, reason):
    #     # embed = discord.Embed(title="Ban Notice", description=f"You have been permanently banned from all servers this bot is in for the reason:\n{reason}",
    #     #                       color=discord.Color.red())
    #     # try:
    #     #     await user.send(embed=embed)
    #     # except discord.Forbidden:
    #     #     pass
    #
    #     for server in self.client.guilds:
    #         try:
    #             await server.ban(user)
    #             await ctx.send(f"Successfully banned from {server.name}")
    #         except discord.Forbidden:
    #             await ctx.send(f"Failed to ban in {server.name}")
    #     await ctx.send("Done.")

    @commands.command(usage='photoduplicates', description="Find members with duplicate profile photos.")
    @commands.guild_only()
    @checks.is_staff_check()
    async def photoduplicates(self, ctx):
        await self.sync_photo_hashes(ctx.guild, ctx.channel)

        data = await sql.get_all_logs(self.client.pool)
        user_dict = {}

        for r in data:
            if r[sql.log_cols.gid] == ctx.guild.id:
                user_dict[r[sql.log_cols.uid]] = (r[sql.log_cols.msg_count], r[sql.log_cols.photo_hash])

        duplicates = {}

        for m in ctx.guild.members:
            if m.id in user_dict:
                if user_dict[m.id][1] not in ["red", "orange", "grey", "green", "blurple"]:
                    lst = duplicates.get(user_dict[m.id][1], None)
                    if not lst:
                        lst = [m]
                    else:
                        lst.append(m)
                    duplicates[user_dict[m.id][1]] = lst

        duplicates = dict((k,v) for k,v in duplicates.items() if len(v) > 3)

        duplicates = OrderedDict(sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True))


        output = f"**Duplicate Profile Photo Results:**\n__{len(duplicates)}__ unique profile photos with >3 members\n\n"
        for k, v in duplicates.items():
            output += f"**{len(v)}** - {v[0].mention}\n"

        lines = textwrap.wrap(output, width=1024, replace_whitespace=False, break_on_hyphens=False)  # Wrap message before max len of field of 1024
        for l in lines:
            await ctx.send(l)


def setup(client):
    client.add_cog(Moderation(client))


def is_not_pinned(msg):
    return False if msg.pinned else True

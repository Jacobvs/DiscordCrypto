import asyncio
import datetime
import difflib
import functools
import hashlib
import io
import json
import logging as logger
import os
from PIL import ImageChops, Image
import textwrap
from collections import Counter

import aiohttp
import discord
from discord.ext import commands
from unidecode import unidecode

import checks
import sql
import utils


logger = logger.getLogger('discord')


class Moderation(commands.Cog):
    """Commands for user/server management"""

    def __init__(self, client):
        self.client = client


    # @commands.command(usage='manualverify <member>', description='Manually verify a user in the server')
    # @commands.guild_only()
    # @checks.is_staff_check()

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

    @commands.command(usage='addalt <member> <altname>', description="Add an alternate account to a user (limit 2).")
    @commands.guild_only()
    @checks.is_staff_check()
    async def addalt(self, ctx, member: utils.MemberLookupConverter, altname):

        name = member.display_name

        name += f" | {altname}"
        try:
            await member.edit(nick=name)
        except discord.Forbidden:
            return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
                                  f"Please copy this and set their nickname manually: `{name}`\n{member.mention}")

        embed = discord.Embed(title="Success!", description=f"`{altname}` was added as an alt to {member.mention}.",
                              color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(usage='removealt <member> <altname>', description="Remove an alt from a player.")
    @commands.guild_only()
    @checks.is_staff_check()
    async def removealt(self, ctx, member: utils.MemberLookupConverter, altname):
        clean_names = []
        if altname.lower() in member.display_name.lower():
            names = member.display_name.split(" | ")
            for n in names:
                if n.lower() != altname.lower():
                    clean_names.append(n)
        nname = " | ".join(clean_names)

        try:
            await member.edit(nick=nname)
        except discord.Forbidden:
            return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
                                  f"Please copy this and replace their nickname manually: ` | {nname}`\n{member.mention}")

        embed = discord.Embed(title="Success!", description=f"`{altname}` was removed as an alt to {member.mention}.",
                              color=discord.Color.green())
        await ctx.send(embed=embed)

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
    async def findduplicates(self, ctx, num: int):
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

    @commands.command(usage="findwordlist [suppress_embeds?: true/false]", description="Find members matching wordlist naming pattern")
    @commands.guild_only()
    @checks.is_staff_check()
    async def findwordlist(self, ctx, suppress=False):
        mems = [m for m in ctx.guild.members if all(w in self.client.wordlist for w in m.name.lower().split()) and m.name.istitle()]
        print(len(mems))
        print([m.name for m in mems[:10]])
        msg_data = await sql.get_all_logs(self.client.pool)
        msg_data = {r[1]: r[2] for r in msg_data if r[0] == ctx.guild.id}
        no_messages = [m for m in mems if msg_data.get(m.id, 0) == 0]
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

        default_0 = [m for m in no_messages if m.avatar_url == m.default_avatar_url]
        default_1 = [m for m in one_message if m.avatar_url == m.default_avatar_url]


        await ctx.send(f"Wordlist name detection sums:\n**{len(no_messages)}** members with no messages\n**{len(one_message)}** members with 1 message"
                       f"\n\n**{len(default_0)}** members with no messages & default pfp\n**{len(default_1)}** members with 1 message & default pfp")

        embed = discord.Embed(title="Actions:", description="1️⃣ - to kick all accounts with 0 messages.\n2️⃣ - to kick all accounts with 0 messages & default pfp"
                                                            "\n❌ - to take no actions", color=discord.Color.orange())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("1️⃣")
        await msg.add_reaction("2️⃣")
        await msg.add_reaction("❌")

        def check(payload):
            return payload.user_id == ctx.author.id and payload.message_id == msg.id and str(payload.emoji) in ["1️⃣", "2️⃣", "❌"]

        try:
            payload = await self.client.wait_for('raw_reaction_add', timeout=10800, check=check)  # Wait 1 hr max
        except asyncio.TimeoutError:
            embed.title = "Timed out!"
            embed.description = f"Timed out! Please run `{ctx.prefix}findwordlist` again to perform actions on these results."
            embed.colour = discord.Color.red()
            return await msg.edit(embed=embed)

        if str(payload.emoji) == "1️⃣":
            kicklist = no_messages
        elif str(payload.emoji) == "2️⃣":
            kicklist = default_0
        else:
            return await msg.delete()

        embed.title = f"Kicking... (0/{len(kicklist)})"
        embed.description = "Kicking members with 0 messages"
        embed.description += " and default profile photos" if str(payload.emoji) == "2️⃣" else ""
        embed.description += "\nPlease wait... This can take a few minutes to complete."
        embed.colour = discord.Color.gold()
        await msg.edit(embed=embed)
        # kick members here
        for i, m in enumerate(kicklist, start=1):
            if i % 100 == 0:
                embed.title = f"Kicking... ({i}/{len(kicklist)})"
                await msg.edit(embed=embed)
            await m.kick(reason=f"Name matching wordlist & no messages sent (Suspected Bot)")

        embed.title = "Success!"
        embed.description = f"__**{len(kicklist)}** members successfully kicked!__\n\nRequested by: {ctx.author.mention} ({ctx.author.display_name}#{ctx.author.discriminator})"
        embed.colour = discord.Color.green()
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)

    # GIF = b'\x47\x49\x46\x38\x37\x61'
    # PNG = b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'
    # JPG = b'\xFF\xD8\xFF\xD8'
    # JPEG = b'\xFF\xD8\xFF\xE0\x00\x10\x4A\x46\x49\x46\x00\x01'
    # WEBP = b'\x52\x49\x46\x46'
    # len_mapping = {'JPG': len(JPG), 'JPEG': len(JPEG), 'PNG': len(PNG), 'GIF': len(GIF), 'WEBP': len(WEBP)}
    #
    # def chop_header(arg: bytes):
    #     if arg.startswith((GIF, PNG, JPG, JPEG, WEBP)):
    #         if arg.startswith(GIF):
    #             print("GIF")
    #             return arg[len_mapping['GIF']:]
    #         if arg.startswith(PNG):
    #             print("PNG")
    #             return arg[len_mapping['PNG']:]
    #         if arg.startswith(JPG):
    #             print("JPG")
    #             return arg[len_mapping['JPG']:]
    #         if arg.startswith(JPEG):
    #             print("JPEG")
    #             return arg[len_mapping['JPEG']:]
    #         if arg.startswith(WEBP):
    #             print("WEBP")
    #             return arg[len_mapping['WEBP']:]
    #     raise ValueError('Bytes didnt match expected headers')
    #
    #
    # b1 = chop_header(await user1.avatar_url.read())
    # b2 = chop_header(await user2.avatar_url.read())
    #
    # print(b1)
    #
    # print(len(b1))
    # print(len(b2))
    # print(b1==b2)

    @commands.command(usage="photoblacklist <user>")
    @commands.guild_only()
    @checks.is_staff_check()
    async def photoblacklist(self, ctx, user: discord.User):
        photo_hash = hash(await user.avatar_url_as(format='jpg', size=64).read())
        await sql.update_photo_hash(self.client.pool, user.id, photo_hash)

        await ctx.guild.chunk()
        msg_data = await sql.get_all_logs(self.client.pool)
        msg_data = {r[1]: r[2] for r in msg_data if r[0] == ctx.guild.id}
        memlist = [m for m in ctx.guild.members if msg_data.get(m.id, 0) < 10]

        embed = discord.Embed(title="Fetching Photos From Discord...", description="Please wait while profile photos are retrieved from discord.\n", color=discord.Color.gold())
        embed.add_field(name="Members to be Retrieved:", value=f"{len(memlist)} members in the server with msg counts <10.")
        embed.timestamp = datetime.datetime.utcnow()
        msg = await ctx.send(embed=embed)

        filtered: list[tuple[discord.Member, str]] = []
        for m in memlist:
            av = m.avatar_url_as(format='jpg', size=64)
            if av != m.default_avatar_url:
                filtered.append((m, av))
        print(len(filtered))
        await ctx.send(len(filtered))

        embed = discord.Embed(title="Checking Image Similarities...", description="Please wait while member list is indexed for photo hashes."
                                                                                  "This can take up to 30 minutes with >50,000 members.", color=discord.Color.orange())
        embed.add_field(name="Members checked:", value=f"**0** / {len(memlist)} members checked\n__{0}__ matches found.")
        embed.set_thumbnail(url="https://i.imgur.com/nLRgnZf.gif")
        embed.set_footer(text='Elapsed: 0s | Est. Left: Calculating...')
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)

        matches: list[discord.Member] = []
        failed: list[discord.Member] = []
        sql_data: list = []

        starttime = datetime.datetime.utcnow()
        last_update = 0

        for i, (m, av) in enumerate(filtered, start=1):
            if i % 15 == 0:
                elapsed_s = (datetime.datetime.utcnow() - starttime).total_seconds()
                if elapsed_s - last_update > 30:
                    last_update = elapsed_s
                    minutes, seconds = divmod(elapsed_s, 60)
                    l_min, l_secs = divmod(int((elapsed_s/i)*len(filtered)), 60)
                    embed.set_footer(text=f'Elapsed: {minutes}m{seconds}s | Est. Left: {l_min}m{l_secs}s')
                    embed.set_field_at(0, name="Members checked:", value=f"**{i}** / {len(memlist)} members checked\n__{len(matches)}__ matches found.\n{len(failed)} members "
                                                                         f"failed to be retrieved.")
                    await msg.edit(embed=embed)

            if i % 100 == 0:
                print("Updating SQL Hashes")
                await sql.batch_update_photo_hashes(self.client.pool, sql_data)
                print("Done updating.")
                sql_data = []

            if len(failed) > 20:
                embed = discord.Embed(title="Error!", description="Failed to retrieve >20 members profile photos! Please try this command again later.", color=discord.Color.red())
                return await msg.edit(embed=embed)

            try:
                m_hash = hash(await m.avatar_url_as(format='jpg', size=64).read())
                if photo_hash == m_hash:
                    matches.append(m)
                    sql_data.append((m.id, m_hash))
            except discord.DiscordException:
                print("FAILED")
                failed.append(m)

        embed = discord.Embed(title="Success!", description=f"**{len(matches)}** members with identical profile photos found!\n\nTo ban all detected members & blacklist this "
                                                            f"photo, click the ✅\nClick the ❌ to ignore this result.", color=discord.Color.green())
        embed.set_thumbnail(url=user.avatar_url)
        embed.set_footer(text="©Cryptographer")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(embed=embed)
        await ctx.send(f"Example Detections ({'20' if len(matches) > 20 else len(matches)}/{len(matches)}):\n{''.join([m.mention for m in matches[:20]])}")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(payload):
            return payload.user_id == ctx.author.id and payload.message_id == msg.id and str(payload.emoji) in ["✅", "❌"]

        try:
            payload = await self.client.wait_for('raw_reaction_add', timeout=10800, check=check)  # Wait 1 hr max
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
            self.client.banned_photos[ctx.guild.id] = self.client.banned_photos.get(ctx.guild.id, set()).append(photo_hash)
            await sql.set_banned_photo(self.client.pool, ctx.guild.id, user.id, banned=True)

            matches.append(user)

            embed.title = f"Banning Matches... (0/{len(matches)})"
            embed.description = "Please wait... This can take a few minutes to complete."
            embed.set_thumbnail(url=user.avatar_url)
            embed.colour = discord.Color.gold()
            await msg.edit(embed=embed)

            # kick members here
            for i, m in enumerate(matches, start=1):
                if i % 100 == 0:
                    embed.title = f"Kicking... ({i}/{len(matches)})"
                    await msg.edit(embed=embed)
                await m.ban(reason=f"PFP matching blacklisted profile photo.")

            embed.title = "Success!"
            embed.description = f"__**{len(matches)}** members successfully banned!__\n\nRequested by: {ctx.author.mention} ({ctx.author.display_name}#{ctx.author.discriminator})"
            embed.colour = discord.Color.green()
            embed.set_footer(text="©Cryptographer")
            embed.timestamp = datetime.datetime.utcnow()
            await msg.edit(embed=embed)




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



def setup(client):
    client.add_cog(Moderation(client))


def is_not_pinned(msg):
    return False if msg.pinned else True


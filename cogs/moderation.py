import asyncio
import datetime
import json
import logging as logger

import aiohttp
import discord
from discord.ext import commands

import checks
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

    @commands.command(usage='testdm <member> <msg>')
    @commands.is_owner()
    async def testdm(self, ctx, member: discord.Member, *, message):
        try:
            await member.send(content=message)
        except discord.Forbidden:
            await ctx.send("FORBIDDEN!")

    @commands.command(usage='testrole <member> <msg>')
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


    @commands.command(usage='cleancaptcha', description='Clean up captcha channel.')
    @commands.guild_only()
    @checks.is_staff_check()
    async def cleancaptcha(self, ctx):

        tasks = asyncio.all_tasks(self.client.loop)
        print(tasks)


        # m = await ctx.send("Purging Captcha channel & sending new verification requests! Please Wait...")
        #
        # await main.cleanup()





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

import asyncio
import json
import textwrap
from datetime import datetime, timedelta
from os import listdir
from os.path import join, isfile

import discord
import psutil
from discord.ext import commands

import checks
from utils import EmbedPaginator


class Core(commands.Cog):
    """Houses core commands & listeners for the bot"""

    def __init__(self, client):
        self.client = client

    @commands.command(usage="testimg <channel>", description='test an image link')
    async def testimg(self, ctx, channel: discord.TextChannel):
        m = await ctx.send(file=discord.File(open('data/test.png', 'rb')))
        img = m.attachments[0]
        await ctx.send(f"image url: {img.url}")
        await channel.send(img.url)
        await m.delete()

    @commands.command(usage="uptime", description="Tells how long the bot has been running.")
    async def uptime(self, ctx):
        uptime_seconds = round((datetime.now() - self.client.start_time).total_seconds())
        await ctx.send(f"Current Uptime: {'{:0>8}'.format(str(timedelta(seconds=uptime_seconds)))}")

    @commands.command(usage="status", description="Retrieve the bot's status.")
    async def status(self, ctx):
        embed = discord.Embed(title="Bot Status", color=discord.Color.dark_gold())
        embed.add_field(name="Bot latency:", value=f"**`{round(self.client.latency * 1000, 2)}`** Milliseconds.")
        mcount = 0
        for g in self.client.guilds:
            mcount += g.member_count
        embed.add_field(name="Connected Servers:",
                        value=f"**`{len(self.client.guilds)}`** servers with **`{mcount}`** total members.")
        embed.add_field(name="\u200b", value="\u200b")
        lines = line_count('/home/ubuntu/DiscordCryptoBot/') + line_count('/home/ubuntu/DiscordCryptoBot/cogs')
        embed.add_field(name="Lines of Code:", value=f"**`{lines}`** lines of code.")
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(name="Server Status:",
                        value=(f"```yaml\nServer: AWS Compute (Ubuntu 18.04)\nCPU: {psutil.cpu_percent()}% utilization."
                               f"\nMemory: {psutil.virtual_memory().percent}% utilization."
                               f"\nDisk: {psutil.disk_usage('/').percent}% utilization."
                               f"\nNetwork: {round(psutil.net_io_counters().bytes_recv * 0.000001)} MB in "
                               f"/ {round(psutil.net_io_counters().bytes_sent * 0.000001)} MB out.```"), inline=False)
        embed.add_field(name="Development Progress", value="To see what I'm working on, click here:\nhttps://github.com/Jacobvs/DiscordCrypto/projects/1", inline=False)
        if ctx.guild:
            appinfo = await self.client.application_info()
            embed.add_field(name=f"Bot author:", value=f"{appinfo.owner.mention} - DM me if something's broken or to request a feature!",
                            inline=False)
        else:
            embed.add_field(name=f"Bot author:", value="__Darkmatter#7321__ - DM me if something's broken or to request a feature!",
                            inline=False)
        await ctx.send(embed=embed)

    @commands.command(usage="rolecount [role]", description="Counts the number of people who have a role, If no role is specified it counts everyone.")
    async def rolecount(self, ctx, *, role: discord.Role = None):
        if not role:
            name = " the server"
            nmembers = ctx.guild.member_count
            color = discord.Color.gold()
        else:
            name = role.name
            nmembers = len(role.members)
            color = role.color
        embed = discord.Embed(color=color).add_field(name=f"Members in {name}", value=f"{nmembers:,}")
        await ctx.send(embed=embed)

    @commands.bot_has_permissions(add_reactions=True)
    @commands.command(usage="help [command/cog]",
                      aliases=["h"], description="Shows the help menu or information for a specific command or cog when specified.")
    async def help(self, ctx, *, opt: str = None):
        if opt:
            cog = self.client.get_cog(opt.capitalize())
            if not cog:
                command = self.client.get_command(opt.lower())
                if not command:
                    return await ctx.send(
                        embed=discord.Embed(description=f"That command/cog does not exist. Use `{ctx.prefix}help` to see all the commands.",
                                            color=discord.Color.red(), ))

                embed = discord.Embed(title=command.name, description=command.description, colour=discord.Color.blue())
                usage = "\n".join([ctx.prefix + x.strip() for x in command.usage.split("\n")])
                embed.add_field(name="Usage", value=f"```{usage}```", inline=False)
                if len(command.aliases) > 1:
                    embed.add_field(name="Aliases", value=f"`{'`, `'.join(command.aliases)}`")
                elif len(command.aliases) > 0:
                    embed.add_field(name="Alias", value=f"`{command.aliases[0]}`")
                return await ctx.send(embed=embed)
            cog_commands = cog.get_commands()
            embed = discord.Embed(title=opt.capitalize(), description=f"{cog.description}\n\n`<>` Indicates a required argument.\n"
                                                                      "`[]` Indicates an optional argument.\n", color=discord.Color.blue(), )
            embed.set_author(name=f"{self.client.user.name} Help Menu", icon_url=self.client.user.avatar_url)
            embed.set_thumbnail(url=self.client.user.avatar_url)
            embed.set_footer(
                text=f"Use {ctx.prefix}help <command> for more information on a command.")
            for cmd in cog_commands:
                if cmd.hidden is False:
                    name = ctx.prefix + cmd.usage
                    if len(cmd.aliases) > 1:
                        name += f" | Aliases – `{'`, `'.join([ctx.prefix + a for a in cmd.aliases])}`"
                    elif len(cmd.aliases) > 0:
                        name += f" | Alias – {ctx.prefix + cmd.aliases[0]}"
                    embed.add_field(name=name, value=cmd.description, inline=False)
            return await ctx.send(embed=embed)

        all_pages = []
        page = discord.Embed(title=f"{self.client.user.name} Help Menu",
                             description="Thank you for using Cryptographer! Please direct message `Darkmatter#7321` if you find bugs or have suggestions!",
                             color=discord.Color.blue(), )
        page.set_thumbnail(url=self.client.user.avatar_url)
        page.set_footer(text="Use the reactions to flip pages.")
        all_pages.append(page)
        page = discord.Embed(title=f"{self.client.user.name} Help Menu", colour=discord.Color.blue())
        page.set_thumbnail(url=self.client.user.avatar_url)
        page.set_footer(text="Use the reactions to flip pages.")
        page.add_field(name="About Cryptographer",
                       value="This bot was built to as a way to give back to the Crypto community by allowing for better member management (reduced spam & bots!) within discord, "
                             "and provides useful features related to crypto for all users!", inline=False, )
        page.add_field(name="Getting Started",
                       value=f"For a full list of commands, see `{ctx.prefix}help`. Browse through the various commands to get comfortable with using "
                             "them, and as always if you have questions or need help – DM `Darkmatter#7321`!", inline=False, )
        all_pages.append(page)
        for _, cog_name in enumerate(sorted(self.client.cogs)):
            if cog_name in ["Owner", "Admin"]:
                continue
            cog = self.client.get_cog(cog_name)
            cog_commands = cog.get_commands()
            if len(cog_commands) == 0:
                continue
            page = discord.Embed(title=cog_name, description=f"{cog.description}\n\n`<>` Indicates a required argument.\n"
                                                             "`[]` Indicates an optional argument.\n",
                                 color=discord.Color.blue(), )
            page.set_author(name=f"{self.client.user.name} Help Menu", icon_url=self.client.user.avatar_url)
            page.set_thumbnail(url=self.client.user.avatar_url)
            page.set_footer(text=f"Use the reactions to flip pages | Use {ctx.prefix}help <command> for more information on a command.")
            for cmd in cog_commands:
                if cmd.hidden is False:
                    name = ctx.prefix + cmd.usage
                    if len(cmd.aliases) > 1:
                        name += f" | Aliases – `{'`, `'.join([ctx.prefix + a for a in cmd.aliases])}`"
                    elif len(cmd.aliases) > 0:
                        name += f" | Alias – `{ctx.prefix + cmd.aliases[0]}`"
                    page.add_field(name=name, value=cmd.description, inline=False)
            all_pages.append(page)
        paginator = EmbedPaginator(self.client, ctx, all_pages)
        await paginator.paginate()

    @commands.command(name='commands', usage="commands", description="View a full list of all available commands.",
                      aliases=["cmd", "cmds"])
    async def commandlist(self, ctx):
        embed = discord.Embed(title="Command List", description="A full list of all available commands.\n", color=discord.Color.teal())
        for _, cog_name in enumerate(sorted(self.client.cogs)):
            if cog_name in ["Owner", "Admin"]:
                continue
            cog = self.client.get_cog(cog_name)
            cog_commands = cog.get_commands()
            if len(cog_commands) == 0:
                continue
            cmds = "```yml\n" + ", ".join([ctx.prefix + cmd.name for cmd in cog_commands]) + "```"
            embed.add_field(name=cog.qualified_name + " Commands", value=cmds, inline=False)
        await ctx.send(embed=embed)

    @commands.command(usage='configure', description="Configure the bot's settings for this server")
    @commands.check_any(commands.has_permissions(administrator=True), commands.is_owner())
    async def configure(self, ctx):
        with open('data/variables.json') as f:
            variables = json.load(f)

        embed = discord.Embed(title="Configuration", description="Please mention or type the name of the channel in which captcha verification will occur.", color=discord.Color.teal())
        final_embed = discord.Embed(title="Success!", description="Your configuration settings have been saved! Please review your current settings below.",
                                    color=discord.Color.green())
        setup_msg = await ctx.send(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg)
        if res is None:
            return
        variables[str(ctx.guild.id)]['channels']['captcha_channel'] = res.id
        self.client.variables[ctx.guild.id]['captcha_channel'] = res
        final_embed.add_field(name="Captcha Channel", value=res.mention)

        embed = discord.Embed(title="Configuration", description="Please mention or type the name of the channel in which bot logs will be posted.", color=discord.Color.teal())
        await setup_msg.edit(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg)
        if res is None:
            return
        variables[str(ctx.guild.id)]['channels']['log_channel'] = res.id
        self.client.variables[ctx.guild.id]['log_channel'] = res
        final_embed.add_field(name="Log Channel", value=res.mention)

        embed = discord.Embed(title="Configuration", description="Please mention or type the name of the Role to be given to new members while waiting for captcha completion.",
                              color=discord.Color.teal())
        await setup_msg.edit(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg, is_role=True)
        if res is None:
            return
        variables[str(ctx.guild.id)]['roles']['temporary_role'] = res.id
        self.client.variables[ctx.guild.id]['temporary_role'] = res
        final_embed.add_field(name="Temporary Role", value=res.mention)

        embed = discord.Embed(title="Configuration", description="Please mention or type the name of the Role to be given upon captcha completion.", color=discord.Color.teal())
        await setup_msg.edit(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg, is_role=True)
        if res is None:
            return
        variables[str(ctx.guild.id)]['roles']['verified_role'] = res.id
        self.client.variables[ctx.guild.id]['verified_role'] = res
        final_embed.add_field(name="Verified Role", value=res.mention)

        embed = discord.Embed(title="Configuration", description="Please mention or type the name of the minimum Role for access to staff commands.", color=discord.Color.teal())
        await setup_msg.edit(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg, is_role=True)
        if res is None:
            return
        variables[str(ctx.guild.id)]['roles']['min_staff_role'] = res.id
        self.client.variables[ctx.guild.id]['min_staff_role'] = res
        final_embed.add_field(name="Min. Staff Role", value=res.mention)

        embed = discord.Embed(title="Configuration", description="Please enter the minimum account age for new members in seconds. (-1 to disable this feature.)",
                              color=discord.Color.teal())
        await setup_msg.edit(embed=embed)

        res = await setup_converter(self.client, ctx, setup_msg, integer=True)
        if res is None:
            return
        variables[str(ctx.guild.id)]['min_account_age_seconds'] = res
        self.client.variables[ctx.guild.id]['min_account_age_seconds'] = res
        final_embed.add_field(name="Min Account Age", value=str(res))

        with open('data/variables.json', "w") as f:
            json.dump(variables, f, indent=4)

        await setup_msg.edit(embed=final_embed)

    @commands.command(usage="testlog", description="Send a test log message in this server.")
    async def testlog(self, ctx):
        logchannel = self.client.variables[ctx.guild.id]['log_channel']
        from cogs import logging
        await logging.send_log(self.client, ctx.guild, logchannel, discord.Embed(title="TEST"), "TEST LOG")


    @commands.command(usage='testperms <channel>', description='Show bot perms for a specified channel.')
    @commands.is_owner()
    async def testperms(self, ctx, channel: discord.TextChannel):
        perms: discord.Permissions = channel.permissions_for(ctx.me)

        attrs = [a for a in dir(perms) if not a.startswith('__') and not callable(getattr(perms, a))]
        s = ""
        for a in attrs:
            if a not in ['DEFAULT_VALUE', 'VALID_FLAGS']:
                s += f"{a} - {getattr(perms, a, 'N/A')}\n"

        await ctx.send(s)


    @commands.command(usage='banname <name>', description='Ban everyone with a specified name')
    @checks.is_staff_check()
    async def banname(self, ctx, *, name: str):
        print("attempting to ban name: " + name)
        name = str(name)
        memberlist = list(filter(lambda m: m.name == name, ctx.guild.members))
        embed = discord.Embed(title="Awaiting Confirmation...", description=f"Please confirm you'd like to ban everyone with the name:\n{name}\n\n{len(memberlist)} members would "
                                                                            "be banned by this action.", color=discord.Color.gold())
        msg = await ctx.send(embed=embed)

        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in ['✅', '❌']

        try:
            reaction, user = await self.client.wait_for('reaction_add', timeout=90,  # 90 seconds
                                                        check=check)

        except asyncio.TimeoutError as e:
            embed.color = discord.Color.red()
            embed.title = "Timed out!"
            embed.description = f"{ctx.author} did not respond in time. No members were banned."
            await msg.edit(embed=embed)
            return await msg.clear_reactions()

        resp = str(reaction.emoji)
        await msg.clear_reactions()

        if resp == '✅':
            embed.title = "Banning... Please wait!"
            embed.description = ""
            embed.set_thumbnail(url="https://i.imgur.com/nLRgnZf.gif")
            embed.color = discord.Color.orange()
            await msg.edit(embed=embed)
            for m in memberlist:
                await m.ban(reason=f'banname execution by: {ctx.author.display_name}')
            print([m.name for m in memberlist])
            await ctx.send("BANNED Members:")
            messages = textwrap.wrap(" ".join([m.mention for m in memberlist]), width=1024)
            for m in messages:
                await ctx.send(m)
            embed.set_thumbnail(url=discord.Embed.Empty)
            embed.color = discord.Color.green()
            embed.title = "Success!"
            embed.description = f"{len(memberlist)} members were successfully banned!\n\nTargeted name: {name}\nRequester: {ctx.author.mention} - ({ctx.author.display_name})"
            embed.timestamp = datetime.utcnow()
            await msg.edit(embed=embed)
        else:
            embed.color = discord.Color.red()
            embed.title = "Cancelled!"
            embed.description = f"{ctx.author} cancelled this action. No members were banned."
            await msg.edit(embed=embed)






def setup(client):
    client.add_cog(Core(client))


async def setup_converter(client, ctx, setup_msg, is_role=False, integer=False):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # Wait for author to select a channel
    while True:
        try:
            msg = await client.wait_for('message', timeout=60, check=check)
        except asyncio.TimeoutError:
            embed = discord.Embed(title="Timed out!", description=f"You didn't choose a {'role' if is_role else 'channel'} in time!", color=discord.Color.red())
            await setup_msg.edit(embed=embed)
            return None

        if str(msg.content).lower() == 'cancel':
            await setup_msg.edit(embed=discord.Embed(title='Canceled!', description='The setup process has been cancelled! No changes have been made.'))
            return None

        if integer:
            try:
                res = int(msg.content)
            except ValueError:
                await ctx.send(f"Please only type an integer (ex: `1`). Say `CANCEL` to cancel.", delete_after=8)
                continue
        else:
            try:
                if is_role:
                    res = await discord.ext.commands.RoleConverter().convert(ctx, argument=str(msg.content))
                else:
                    res = await discord.ext.commands.TextChannelConverter().convert(ctx, argument=str(msg.content))
            except discord.ext.commands.CommandError or discord.ext.commands.BadArgument:
                await ctx.send(f"Channel provided: __{msg}__ was not found. Please mention the {'role' if is_role else 'channel'} again. Say `CANCEL` to cancel.", delete_after=8)
                continue

        return res



def line_count(path):
    """Count total lines of code in specified path"""
    file_list = [join(path, file_p) for file_p in listdir(path) if isfile(join(path, file_p))]
    total = 0
    for file_path in file_list:
        if file_path[-3:] == ".py":  # Ensure only python files are counted
            try:
                count = 0
                with open(file_path, encoding="ascii", errors="surrogateescape") as current_file:
                    for _ in current_file:
                        count += 1
            except IOError:
                return -1
            if count >= 0:
                total += count
    return total

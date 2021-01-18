import asyncio
import json
from datetime import datetime, timedelta
from os import listdir
from os.path import join, isfile

import aiohttp
import discord
import psutil
from discord.ext import commands

import checks
import sql
import utils
from cogs import verification, moderation
from cogs.verification import guild_verify_react_handler, dm_verify_react_handler, Verification, subverify_react_handler
from sql import get_guild, get_user, add_new_guild, usr_cols, gld_cols
from utils import EmbedPaginator


class Core(commands.Cog):
    """Houses core commands & listeners for the bot"""

    def __init__(self, client):
        self.client = client

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
        lines = line_count('/home/ubuntu/DiscordCrypto/') + line_count('/home/ubuntu/DiscordCrypto/cogs')
        embed.add_field(name="Lines of Code:", value=f"**`{lines}`** lines of code.")
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(name="Server Status:",
                        value=(f"```yaml\nServer: AWS Compute (Ubuntu 18.04)\nCPU: {psutil.cpu_percent()}% utilization."
                               f"\nMemory: {psutil.virtual_memory().percent}% utilization."
                               f"\nDisk: {psutil.disk_usage('/').percent}% utilization."
                               f"\nNetwork: {round(psutil.net_io_counters().bytes_recv * 0.000001)} MB in "
                               f"/ {round(psutil.net_io_counters().bytes_sent * 0.000001)} MB out.```"), inline=False)
        embed.add_field(name="Development Progress", value="To see what I'm working on, click here:\nhttps://github.com/DiscordCrypto/projects/1", inline=False)
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

    # Event listeners
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Add prefix & entry in rotmg.guilds table on guild join"""
        with open('data/prefixes.json', 'r') as file:
            prefixes = json.load(file)
        prefixes.update({guild.id: '!'})
        with open('data/prefixes.json', 'w') as file:
            json.dump(prefixes, file, indent=4)

        await add_new_guild(self.client.pool, guild.id, guild.name)

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        """Remove guild from data"""
        with open('data/prefixes.json', 'r') as file:
            prefixes = json.load(file)
        prefixes.pop(str(guild.id))
        with open('data/prefixes.json', 'w') as file:
            json.dump(prefixes, file, indent=4)

        # TODO: Remove guilds and user-data from sql

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


def setup(client):
    client.add_cog(Core(client))


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

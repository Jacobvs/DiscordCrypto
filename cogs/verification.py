import asyncio
import datetime
import difflib
import functools
import io
import logging
import os
import random
import shutil
import string
import discord
import numpy as np
from discord.ext import commands
from unidecode import unidecode

import sql
import utils
from cogs.logging import send_log, action_log, verify_log, VerifyAction
from views.verify import VerifyView

logger = logging.getLogger('discord')


class Verification(discord.ext.commands.Cog):

    def __init__(self, client):
        self.client = client


    @commands.command(usage="addverimsg", description="Add the verification message")
    async def addverimsg(self, ctx):
        verified_role = self.client.variables[ctx.guild.id]['verified_role']

        if not verified_role:
            return await ctx.send("Please configure the verified role before setting up verification!")

        embed = discord.Embed(title="Server Verification", description="To prevent bot abuse, new members are required to verify in this server.\n\n"
                                                                       "__Please complete verification within **5** minutes, or you risk being kicked from the server.__\n\nPress the button below to begin the "
                                                                       "verification process.", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.set_thumbnail(url=self.client.user.avatar)
        embed.set_footer(text="©Cryptographer")

        await ctx.send(embed=embed, view=VerifyView(self.client))


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Check member against blacklists and determine bot chance
        :param member: discord.Member of new member
        :return: None, kick member to verification server (if configured), and ban if blacklist match
        """

        if member.bot:
            return

        log_channel: discord.TextChannel = self.client.variables[member.guild.id]['log_channel']

        if await self.check_banned_name(member, log_channel):
            return

        if await self.check_banned_photo(member, log_channel):
            return

        if await self.check_account_age(member, log_channel):
            return

        await self.wait_for_verification(member, log_channel)

        # await wait_for_message(self.client, member, msg_threshold=2, max_wait_s=3600, ban=False)

    async def wait_for_verification(self, member: discord.Member, log_channel: discord.TextChannel) -> None:
        captcha_channel: discord.TextChannel = self.client.variables[member.guild.id]['captcha_channel']
        time_left = 300

        async def check_status():
            if member.id in self.client.pending_verification:
                await asyncio.sleep(121)  # wait to check if timed out or completed
            # Check if member has the role yet
            return self.client.variables[member.guild.id]['verified_role'] in member.roles

        await asyncio.sleep((time_left-180))  # sleep 3m
        if self.client.variables[member.guild.id]['verified_role'] in member.roles:
            return

        if member.id not in self.client.pending_verification:
            await log_channel.send(f"{member.mention} - You will be kicked from the server in __2 minutes__ if verification has not been started before then!")

        await asyncio.sleep(180)
        if await check_status():
            return

        await verify_log(self.client, member.guild, member, VerifyAction.EXPIRED)
        await log_channel.send(f"[DEBUG: W_F_Verification] Member kicked here! 5m timeout expired!")

        await action_log(self.client, member, False, "Timed out awaiting Verification")
        return


    async def check_banned_name(self, member: discord.Member, log_channel: discord.TextChannel):
        """
        Check for banned name
        :param member: discord.Member
        :param log_channel: discord.TextChannel where log messages are sent
        :return boolean: if the member was banned or not
        """

        # First, determine if name contains unicode characters, if so - run unidecode & check against reference
        if ((not any(ord(char) < 128 for char in member.name) and unidecode(member.name) in self.client.banned_names[str(member.guild.id)][1])
                or member.name in self.client.banned_names[str(member.guild.id)][0]):  # Else, check if name matches name blacklist
            logger.info(f"Member joined with banned name: {member.name}")

            try:
                await member.ban(reason="User joined with banned name!")
                await action_log(self.client, member, True, "Banned Name")
                return True
            except discord.DiscordException:
                pass

        return False

    async def check_banned_photo(self, member: discord.Member, log_channel: discord.TextChannel):
        """
        Check for banned profile photo
        :param member: discord.Member
        :param log_channel: discord.TextChannel where log messages are sent
        :return boolean: if the member was banned or not
        """

        # First, retrieve and store (perceptual "pHash") photo hash in DB
        if not member.avatar:
            photo_hash = str(member.default_avatar)
        else:
            photo_hash = await utils.get_photo_hash(self.client, member)

        if photo_hash:
            await sql.update_photo_hash(self.client.pool, member.id, photo_hash, member.guild.id)

            # Check photo hash against blacklist or matches blacklist with 5 % similarity
            if (member.guild.id, photo_hash) in self.client.banned_photos or \
                    any(utils.hamming_distance(hsh, photo_hash) < 5 for gid, hsh in self.client.banned_photos if gid == member.guild.id):
                logger.log(f"Member joined with banned photo: {member.name} (ID: {member.id})")

                try:
                    await member.ban(reason="User joined with banned photo!")
                    await action_log(self.client, member, True, "Banned Photo")
                    return True
                except discord.DiscordException:
                    pass

        return False

    async def check_account_age(self, member: discord.Member, log_channel: discord.TextChannel):
        """
        Check if user meets minimum account age
        :param member: discord.Member
        :param log_channel: discord.TextChannel where log messages are sent
        :return boolean: if the member was banned or not
        """
        # Check for minimum account age
        min_account_age_seconds = self.client.variables[member.guild.id]['min_account_age_seconds']

        # Check the user account creation date (1 day by default)
        if min_account_age_seconds != -1:
            seconds_old = (datetime.datetime.utcnow() - member.created_at).total_seconds()
            if seconds_old < min_account_age_seconds:
                (days, hours, minutes, seconds) = utils.seconds_formatter(seconds_old)

                embed = discord.Embed(title=f"YOU HAVE BEEN KICKED FROM {member.guild.name}!",
                                      description=f"Your account creation date is less than this server's minimum!", color=discord.Color.red())
                log_embed = discord.Embed(title=f"{member.name}#{member.discriminator} has been kicked!**",
                                          description=f"Account under minimum creation date! ({seconds_old}s < {min_account_age_seconds}s minimum)!\n"
                                                      f"\n**Mention:** {member.mention}"
                                                      f"\n**Id :** {member.id}",
                                          color=discord.Color.orange())

                embed.add_field(name="Current Account Age:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)
                log_embed.add_field(name="Current Account Age:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)

                (days, hours, minutes, seconds) = utils.seconds_formatter(min_account_age_seconds)
                embed.add_field(name="Server Minimum:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)
                log_embed.add_field(name="Server Minimum:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)
                log_embed.set_footer(text=f"Joined at: {member.joined_at}")
                log_embed.timestamp = datetime.datetime.utcnow()

                await send_log(self.client, member.guild, log_channel, embed=embed, event="onJoin Account Age", action="Member Kicked")

                try:
                    await member.send(embed=embed)
                except discord.DiscordException:
                    pass

                await member.kick(reason=f"Account under minimum creation date! ({seconds_old}s < {min_account_age_seconds}s minimum)")  # Kick the user
                return True

        return False


def setup(client):
    client.add_cog(Verification(client))


async def wait_for_message(client: discord.Client, member: discord.Member, msg_threshold: int, max_wait_s: int, ban: bool):
    """
    Wait until a user sends enough messages to meet the threshold, or until timeout expires

    :param client: discord.Client
    :param member: discord.Member of user to wait upon
    :param msg_threshold: threshold of messages to meet in order to pass verification
    :param max_wait_s: max time (seconds) to wait before the member is kicked/banned
    :param ban: True to ban the member instead of kicking
    :return:
    """
    time_left = max_wait_s
    start_time = datetime.datetime.utcnow()
    sent_messages = 0

    def check(msg: discord.Message):
        return msg.author == member

    while True:  # Loop until msg threshold is met, or timeout occurs
        try:
            await client.wait_for('message', check=check, timeout=time_left)
            sent_messages += 1

            if sent_messages >= msg_threshold:
                return

            time_left = max_wait_s - (datetime.datetime.utcnow() - start_time).total_seconds()

        except asyncio.TimeoutError:
            break

        # TODO: send member an embed explaining (somewhat) why they were kicked/banned

        if ban:
            await member.ban(reason="Timeout expired before enough messages were sent.")
        else:
            await member.kick(reason="Timeout expired before enough messages were sent.")


import asyncio
import datetime
import difflib
import functools
import io
import logging
import math
import os
import random
import shutil
import string
import Augmentor
import discord
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from unidecode import unidecode

import sql
import utils
from cogs.logging import send_log

logger = logging.getLogger('discord')


class Verification(discord.ext.commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if ((not any(ord(char) < 128 for char in member.name) and unidecode(member.name) in self.client.banned_names[str(member.guild.id)][1])
                or member.name in self.client.banned_names[str(member.guild.id)][0]):

            print(f"Member joined with banned name: {member.name}")
            try:
                await member.ban(reason="User joined with banned name!")
                embed = discord.Embed(description=f"{member.mention} {member.name}#{member.discriminator}", color=discord.Color.from_rgb(0, 0, 0))
                embed.set_author(name="Banned (Blacklisted Name)", icon_url=member.avatar_url)
                embed.set_thumbnail(url=member.avatar_url)
                embed.set_footer(text=f"ID: {member.id}")
                if not all(ord(char) < 128 for char in member.name):
                    embed.add_field(name="Unicode Name:", value=f"`{member.name}` - decoded: `{member.name.encode('unicode-escape')}`")
                embed.timestamp = datetime.datetime.utcnow()
                return await self.client.variables[member.guild.id]['log_channel'].send(embed=embed)
            except discord.DiscordException:
                pass

        if not member.avatar:
            photo_hash = str(member.default_avatar)
        else:
            photo_hash = await utils.get_photo_hash(self.client, member)

        if photo_hash:
            await sql.update_photo_hash(self.client.pool, member.id, photo_hash, member.guild.id)

            if (member.guild.id, photo_hash) in self.client.banned_photos or \
                    any(utils.hamming_distance(hsh, photo_hash) < 5 for gid, hsh in self.client.banned_photos if gid == member.guild.id):
                print(f"Member joined with banned photo: {member.name} (ID: {member.id})")
                try:
                    embed = discord.Embed(description=f"{member.mention} {member.name}#{member.discriminator}", color=discord.Color.from_rgb(0, 0, 0))
                    embed.set_author(name="Banned (Blacklisted Photo)", icon_url=member.avatar_url)
                    embed.set_thumbnail(url=member.avatar_url)
                    embed.set_footer(text=f"ID: {member.id}")
                    if not all(ord(char) < 128 for char in member.name):
                        embed.add_field(name="Unicode Name:", value=f"`{member.name}` - decoded: `{member.name.encode('unicode-escape')}`")
                    embed.timestamp = datetime.datetime.utcnow()
                    await self.client.variables[member.guild.id]['log_channel'].send(embed=embed)
                    await member.ban(reason="User joined with banned photo!")
                except discord.DiscordException:
                    pass

        if member.bot or self.client.variables[member.guild.id]['maintenance_mode']:
            print('Member joined in maintenance mode!')
            return

        log_channel: discord.TextChannel = self.client.variables[member.guild.id]['log_channel']
        captcha_channel: discord.TextChannel = self.client.variables[member.guild.id]['captcha_channel']
        min_account_age_seconds = self.client.variables[member.guild.id]['min_account_age_seconds']

        member_time = f"{member.joined_at.year}-{member.joined_at.month}-{member.joined_at.day} {member.joined_at.hour}:{member.joined_at.minute}:{member.joined_at.second}"

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

                await member.send(embed=embed)
                await member.kick(reason=f"Account under minimum creation date! ({seconds_old}s < {min_account_age_seconds}s minimum)")  # Kick the user

        if self.client.variables[member.guild.id]['captcha_status']:
            # Give temporary role
            await member.add_roles(self.client.variables[member.guild.id]['temporary_role'])

            file, text, folder_path = await self.client.loop.run_in_executor(None, functools.partial(create_captcha, member))

            captcha_msg = await captcha_channel.send(
                f"{member.mention} - Please solve the captcha below to gain access to the server!",
                file=file)

            # Remove captcha folder
            try:
                shutil.rmtree(folder_path)
            except Exception as error:
                await send_log(self.client, member.guild, log_channel, embed=self.client.warning_embed, event=f"Delete captcha file failed {error}")

            # Check if it is the right user
            def check(message):
                if message.author == member and message.content != "":
                    return message.content

            password = text.split(" ")
            password = "".join(password)

            try:
                msg = await self.client.wait_for('message', timeout=120.0, check=check)
                # Check the captcha

                if msg.content.upper() == password:

                    embed = discord.Embed(description=f"{member.mention} passed the captcha.", color=0x2fa737)  # Green
                    await captcha_channel.send(embed=embed, delete_after=5)
                    # Give and remove roles
                    try:
                        veri_role = self.client.variables[member.guild.id]['verified_role']
                        if veri_role:
                            await member.add_roles(veri_role)
                    except Exception as _:
                        await send_log(self.client, member.guild, log_channel, self.client.error_embed, event=f"Failed to give member {member.mention} the verified role!")
                    try:
                        temp_role = self.client.variables[member.guild.id]['temporary_role']
                        if temp_role:
                            await member.remove_roles(temp_role)
                    except Exception as _:
                        await send_log(self.client, member.guild, log_channel, self.client.error_embed, event=f"Failed to remove the temporary role from member: {member.mention}")

                    await asyncio.sleep(3)

                    try:
                        await captcha_msg.delete()
                        await msg.delete()
                    except discord.Forbidden or discord.HTTPException:
                        await send_log(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg/ user captcha solution msg!")

                    # Logs
                    embed = discord.Embed(title=f"**{member} passed the captcha.**", description=f"**__User informations :__**\n\n**Name :** {member}\n**Id :** {member.id}",
                                          color=discord.Color.green())
                    embed.set_footer(text=f"at {member_time}")
                    await send_log(self.client, member.guild, log_channel, embed=embed, event="Successful Captcha", action=f"Verified Role Given to {member.mention}")

                else:
                    link = 'https://discord.gg/3BCVhhG'  # Create an invite
                    embed = discord.Embed(description=f"{member.mention} failed the captcha.", color=discord.Color.red())  # Red
                    await captcha_channel.send(embed=embed, delete_after=5)
                    embed = discord.Embed(title=f"Error! Incorrect Captcha!", description=f"You have been kicked from {member.guild.name}\nReason : You failed the "
                                                                                          f"captcha!\nCorrect answer: __{password}__"
                                                                                          f"\nServer link : <{link}> (Use this link to re-join the server and try again!)",
                                          color=discord.Color.red())
                    try:
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        await captcha_channel.send(f"{member.mention} - You have DM's Disabled! Please save this invite link to rejoin as you'll be kicked in 20s!", embed=embed,
                                                   delete_after=20)
                        await asyncio.sleep(20)
                    await member.kick(reason="Failed Captcha!")  # Kick the user
                    await asyncio.sleep(3)

                    try:
                        await captcha_msg.delete()
                        await msg.delete()
                    except discord.Forbidden or discord.HTTPException:
                        await send_log(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg/ user captcha solution msg!")

                    # Logs
                    embed = discord.Embed(title=f"**{member} failed the captcha!**", description=f"**__User information :__**\n\n**Name :** {member}\n**Id :** {member.id}",
                                          color=discord.Color.red())
                    embed.set_footer(text=f"at {member_time}")
                    await send_log(self.client, member.guild, log_channel, embed=embed, event="Failed Captcha", action=f"{member.mention} kicked from server")

            except asyncio.TimeoutError:
                link = 'https://discord.gg/3BCVhhG'  # Create an invite
                embed = discord.Embed(title=f"Timeout!", description=f"{member.mention} has exceeded the response time (120s)!", color=discord.Color.orange())
                await captcha_channel.send(embed=embed, delete_after=5)
                try:
                    embed = discord.Embed(title=f"Error! Captcha response timeout!", description=f"You have been kicked from {member.guild.name}\nReason : You took too long to "
                                                                                                 f"answer the captcha! (120s) \n Correct answer: __{password}__\n"
                                                                                                 f"Server link : <{link}> (Use this link to re-join the server and try again!)",
                                          color=discord.Color.red())
                    try:
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        await captcha_channel.send(f"{member.mention} - You have DM's Disabled! Please save this invite link to rejoin as you'll be kicked in 20s!", embed=embed,
                                                   delete_after=20)
                        await asyncio.sleep(20)
                    await member.kick(reason="Captcha Timeout")  # Kick the user
                except Exception as error:
                    print(f"Log failed (onJoin) : {error}")
                await asyncio.sleep(3)

                try:
                    await captcha_msg.delete()
                except discord.Forbidden or discord.HTTPException:
                    await send_log(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg!")

                # Logs
                embed = discord.Embed(title=f"**{member} timed out while answering captcha!**", description=f"**__User information :__**\n\n**Name :** {member}\n**Id :**"
                                                                                                            f" {member.id}",
                                      color=discord.Color.red())
                embed.set_footer(text=f"at {member_time}")
                await send_log(self.client, member.guild, log_channel, embed=embed, event="Captcha Timeout", action=f"{member.mention} kicked from server")

        if self.client.variables[member.guild.id]['duplicate_status']:
            # check to see if username is the same as any staff
            min_staff_role: discord.Role = self.client.variables[member.guild.id]['min_staff_role']
            staff_name_list = filter(lambda mem: mem.top_role >= min_staff_role and not mem.bot, member.guild.members)
            # print("Staff uname list:")
            # print([m.name for m in staff_name_list])

            res = difflib.get_close_matches(member.display_name, [m.name for m in staff_name_list], cutoff=0.85)
            print("Member joined with name: " + member.display_name + " | Checking similarities")
            if len(res) > 0:
                print("detected similar name!")
                embed = discord.Embed(title="Possible Impersonation Report!", description=f"User: {member.mention} - ({member.name}#{member.discriminator})\nJoined (" \
                                                                                          f"{member.joined_at.strftime('%m/%d/%Y, %H:%M:%S %Z')})\n\nDetected "
                                                                                          f"similarities with staff: {res}\n", color=discord.Color.teal())
                embed.add_field(name="Actions:", value="Click the ✅ emoji to ban this member\nClick the ❌ emoji to allow the user server access & resolve this case.")
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_author(name=member.display_name, icon_url=member.avatar_url)
                report = await self.client.variables[member.guild.id]['duplicate_reports'].send(content=f'DUPLICATE Report for UID: {member.id}', embed=embed)
                if member:
                    await report.add_reaction('✅')
                await report.add_reaction('❌')

            # check to see if member shares name with anyone in server

        try:
            def check(msg):
                return msg.author == member

            await captcha_channel.purge(limit=200, check=check)
        except discord.Forbidden:
            pass

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

                embed = discord.Embed(description=f"{member.mention} {member.name}#{member.discriminator}", color=discord.Color.from_rgb(0, 0, 0))
                embed.set_author(name="Banned (Blacklisted Name)", icon_url=member.avatar_url)
                embed.set_thumbnail(url=member.avatar_url)
                embed.set_footer(text=f"ID: {member.id}")
                if not all(ord(char) < 128 for char in member.name):
                    embed.add_field(name="Unicode Name:", value=f"`{member.name}` - decoded: `{member.name.encode('unicode-escape')}`")
                embed.timestamp = datetime.datetime.utcnow()

                await log_channel.send(embed=embed)
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

                    embed = discord.Embed(description=f"{member.mention} {member.name}#{member.discriminator}", color=discord.Color.from_rgb(0, 0, 0))
                    embed.set_author(name="Banned (Blacklisted Photo)", icon_url=member.avatar_url)
                    embed.set_thumbnail(url=member.avatar_url)
                    embed.set_footer(text=f"ID: {member.id}")
                    if not all(ord(char) < 128 for char in member.name):
                        embed.add_field(name="Unicode Name:", value=f"`{member.name}` - decoded: `{member.name.encode('unicode-escape')}`")
                    embed.timestamp = datetime.datetime.utcnow()

                    await log_channel.send(embed=embed)
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


def get_bot_chance_score(client, user: discord.User):
    """
    Generate score for new member of bot likeliness from 0-100
    0: Likely a regular user
    Items which increase score:
    +25 | Default profile picture
    +50 | Name matching wordlist
    +2 | Every day under 2 weeks of account creation date

    :param client: discord.Bot instance
    :param user: discord.User of user to check
    :return (int, boolean, boolean, int): score, default_pfp, wordlist_match, creation score
    """
    default_pfp = user.avatar_url == user.default_avatar_url
    wordlist_match = check_wordlist(client, user)
    creation_score = 2 * (14 - (user.created_at - datetime.datetime.utcnow()).days)

    score = 25 if default_pfp else 0
    score += 50 if wordlist_match else 0
    score += creation_score
    score = 0 if score < 0 else 100 if score >= 100 else score

    return score, default_pfp, wordlist_match, creation_score


def check_wordlist(client, user: discord.User):
    """
    Check if a user has a name matching the wordlist format

    :param client: discord.Bot instance
    :param user: discord.User
    :return boolean: True if match, False otherwise
    """
    if user.name[-1].isdigit():
        words = user.name[:-1]
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

            if first_word in client.adjective_list and second_word in client.noun_list:
                return True

    return False


def create_captcha(member):
    # Create captcha
    image = np.zeros(shape=(100, 350, 3), dtype=np.uint8)

    # Create image
    image = Image.fromarray(image + 255)  # +255 : black to white

    # Add text
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font="arial", size=60)

    text = ' '.join(random.choice(string.ascii_uppercase) for _ in range(6))  # + string.ascii_lowercase + string.digits

    # Center the text
    W, H = (350, 100)
    w, h = draw.textsize(text, font=font)
    draw.text(((W - w) / 2, (H - h) / 2), text, font=font, fill=(90, 90, 90))

    # Save
    ID = member.id
    folderPath = f"captchaFolder/captcha_{ID}"
    try:
        os.mkdir(folderPath)
    except:
        if os.path.isdir('captchaFolder') is False:
            os.mkdir("captchaFolder")
        if os.path.isdir(folderPath) is True:
            shutil.rmtree(folderPath)
        os.mkdir(folderPath)
    image.save(f"{folderPath}/captcha{ID}.png")

    # Deform
    p = Augmentor.Pipeline(folderPath)
    p.random_distortion(probability=1, grid_width=4, grid_height=4, magnitude=10)
    p.process()

    # Search file in folder
    path = f"{folderPath}/output"
    files = os.listdir(path)
    captchaName = [i for i in files if i.endswith('.png')]
    captchaName = captchaName[0]

    image = Image.open(f"{folderPath}/output/{captchaName}")

    # Add line
    width = random.randrange(6, 8)
    co1 = random.randrange(0, 75)
    co3 = random.randrange(275, 350)
    co2 = random.randrange(35, 50)
    co4 = random.randrange(50, 85)
    draw = ImageDraw.Draw(image)
    draw.line([(co1, co2), (co3, co4)], width=width, fill=discord.Color.teal().to_rgb())

    # Add noise
    noisePercentage = 0.15  # 25%

    pixels = image.load()  # create the pixel map
    for i in range(image.size[0]):  # for every pixel:
        for j in range(image.size[1]):
            rdn = random.random()  # Give a random %
            if rdn < noisePercentage:
                pixels[i, j] = (90, 90, 90)

    # Save to bytesIO
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)

    # Send captcha
    return discord.File(buf, filename="Captcha.png"), text, folderPath

import asyncio
import datetime
import difflib
import functools
import io
import os
import re
import shutil
import string
import random
from autocorrect import Speller

import Augmentor
import aiohttp
import discord
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from unidecode import unidecode

import checks
import sql
import utils
from cogs.logging import send_log
from main import get_prefix


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(usage="testcaptcha", description="Generate a Test Captcha")
    @commands.is_owner()
    async def testcaptcha(self, ctx):
        file, text, folder_path = await self.client.loop.run_in_executor(None, functools.partial(create_captcha, ctx.author))

        captcha_msg = await ctx.send(
            f"{ctx.author.mention} - Please solve the captcha below to gain access to the server! (6 uppercase letters).",
            file=file)
        # Remove captcha folder
        try:
            shutil.rmtree(folder_path)
        except Exception as error:
            pass

        # Check if it is the right user
        def check(message):
            if message.author == ctx.author and message.content != "":
                return message.content

        msg = await self.client.wait_for('message', timeout=120.0, check=check)
        # Check the captcha
        password = text.split(" ")
        password = "".join(password)
        if msg.content.upper() == password:
            await ctx.send("Correct Solution!")
        else:
            await ctx.send(f"Incorrect Solution! Answer: {password}")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.guild and not msg.author.bot:
            # Add to sent message queue to be inserted later...
            self.client.sent_messages[(msg.guild.id, msg.author.id)] = self.client.sent_messages.get((msg.guild.id, msg.author.id), 0) + 1

            if msg.attachments and (msg.channel.id == 396316232124727296 or msg.channel.id == 797960110310686760 or msg.channel.id == 804133361378656287):
                print("MSG HAS ATTACHMENT")
                img = msg.attachments[0]
                if img.height:
                    image_ref = msg
                    print("MSG IS IMAGE")
                    data, img, response = await self.check_spam_img(img, msg, True)
                    await self.send_spam_report(msg, data, img, response)

            elif any(command in msg.content.split(" ")[0] for command in ['!level', '!rank']):
                if msg.guild.id == 390628544369393664 and msg.channel.id != 780208685229801502:
                    try:
                        m = await msg.channel.send(content=f'{msg.author.mention} Use <#780208685229801502> to check your level 🤡', delete_after=15)
                        await m.add_reaction('🤡')

                        await msg.delete()

                        def check(m):
                            return m.channel == msg.channel and m.author.id == 159985870458322944

                        try:
                            mee6_msg = await self.client.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            return

                        await mee6_msg.delete()

                    except discord.DiscordException:
                        return

            elif (msg.author.id, msg.guild.id) in self.client.soft_muted:
                try:
                    await msg.delete()
                    str = msg.content.replace('||', '')
                    if len(str) > 0:
                        await msg.channel.send(f"(Soft-Muted) __{msg.author.display_name}__: ||{str}||")
                except discord.NotFound or discord.Forbidden:
                    pass

    async def check_spam_img(self, img, msg, send_to_channel=False):
        if send_to_channel:
            response = await msg.channel.send("Checking Image... Please wait.")
        else:
            response = None
        log_channel = self.client.variables[msg.guild.id]['log_channel']
        if log_channel:
            try:
                image_ref = await log_channel.send(content="Image(s) uploaded in support channels:",
                                                   files=[await a.to_file(use_cached=True) for a in msg.attachments])
                img = image_ref.attachments[0]
            except discord.DiscordException:
                pass
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(200)) as cs:
                for i in range(3):
                    async with cs.get(f'https://api.ocr.space/parse/imageurl?OCREngine=2&apikey={self.client.OCR_TOKEN}&url={img.url}') as r:
                        if r.status != 200:
                            if response:
                                await response.edit(content=f"I'm having trouble parsing this image! (Status: {r.status})... Retrying ({i}/3)")
                            await asyncio.sleep(60)
                            continue
                        data = await r.json()
                        if data['IsErroredOnProcessing'] is True:
                            if response:
                                await response.edit(content=f"I'm having trouble parsing this image!... Retrying ({i + 1}/3)")
                            await asyncio.sleep(60)
                            continue
                        break
                else:
                    try:
                        if response:
                            await response.edit(content="OCR Detection failed! Sending image for moderators to review!")
                        data = None
                    except discord.Forbidden or discord.HTTPException:
                        pass
        except (asyncio.TimeoutError, aiohttp.ClientError):
            try:
                if response:
                    await response.edit(content="OCR Detection failed! Sending image for moderators to review!")
                data = None
            except discord.Forbidden or discord.HTTPException:
                pass
        return data, img, response

    async def send_spam_report(self, msg, data, img, response):
        member = None

        if data is not None:
            parsed_text = data['ParsedResults'][0]['ParsedText'].lower()
            detections = ['win', 'giveaway', 'congratulations', 'prize', 'https', '.com', 'promo', 'pump', 'vote', 'advertisement', 'attn', 'selling', 'finance']
            prefix = await self.client.get_prefix(msg)

            if any(x in parsed_text.lower() for x in detections):
                if response:
                    await response.edit(content="__**SPAM DETECTED! -- DO NOT CLICK ANY LINKS IN THE RECIEVED MESSAGE!**__\nModerators have been alerted and "
                                            "will review your submission soon!\nIf the user is deemed to be a scammer they will be banned! Thank you for reporting this "
                                            "user!")
                # User lookup strategy:
                # 1. check for 'This is the beginning of your' -> words before likely username
                # 2. check for 'Today at ..."
                # 3. check for 'h/h:mm AM/PM <u_name>' (compact mode)
                # 4. check for '\w \w h/h:mm'
                tests = []
                print(f"Parsed text: {parsed_text}")

                # look for line: direct message history with @ .split -> 1?
                for i in range(2):
                    if 'this is the beginning of' in parsed_text:
                        lines = parsed_text.split('this is the beginning of')[0].splitlines()
                        tests.append(lines[0])
                        print(f'found beginning of: {lines} === {tests}')
                    elif 'today at' in parsed_text:
                        lines = parsed_text.split('today at')[0].splitlines()
                        lines = list(filter(None, lines))
                        tests.append(lines[-1])
                        if len(lines) > 1:
                            tests.append(lines[-2] + " " + lines[-1])
                        print(f'found today at: {lines} === {tests}')
                    elif 'today' in parsed_text:
                        lines = parsed_text.split('today')[0].splitlines()
                        lines = list(filter(None, lines))
                        tests.append(lines[-1])
                        if len(lines) > 1:
                            tests.append(lines[-2] + " " + lines[-1])
                        print(f'found today: {lines} === {tests}')
                    elif re.search(r'\d{1,2}:\d{2}\s(?:am|pm)', parsed_text):
                        lines = re.split(r'\d{1,2}:\d{2}\s(?:am|pm)', parsed_text)[1].splitlines()
                        lines = list(filter(None, lines))
                        tests.append(lines[0])
                        if len(lines) > 1:
                            if ' ' in lines[0]:
                                words = list(filter(None, lines[0].split()))
                                name = ""
                                for w in words:
                                    name += w
                                    tests.append(name)
                                    name += " "
                            tests.append(lines[0] + " " + lines[1])
                        print(f'found TIME: {lines} === {tests}')
                    elif re.search(r'(?:\S+\s\S+)\s\d{1,2}:\d{2}', parsed_text):
                        lines = re.split(r'(?:\S+\s\S+)\s\d{1,2}:\d{2}', parsed_text)[0].splitlines()
                        lines = list(filter(None, lines))
                        tests.append(lines[0])
                        if len(lines) > 1:
                            if ' ' in lines[0]:
                                words = list(filter(None, lines[0].split()))
                                name = ""
                                for w in words:
                                    name += w
                                    tests.append(name)
                                    name += " "
                            tests.append(lines[0] + " " + lines[1])
                        print(f'found POST TIME: {lines} === {tests}')
                    if tests:
                        break
                    parsed_text = Speller(only_replacements=True).autocorrect_sentence(parsed_text)

                if tests:
                    tests.sort(key=len)
                    converter = utils.MemberLookupConverter()
                    ctx = commands.Context(bot=self.client, prefix=prefix, guild=msg.guild, message=msg)
                    for l in tests:
                        try:
                            member = await converter.convert(ctx, l)
                            if member:
                                break
                        except discord.ext.commands.BadArgument:
                            pass
            elif response:
                try:
                    return await response.delete()
                except discord.Forbidden or discord.HTTPException:
                    pass

            spam_report_channel = self.client.variables[msg.guild.id]['spam_reports']

            detected_member_str = f"\n__User Detected:__\n{member.mention} ({member.display_name}#{member.discriminator}) - Joined (" \
                                  f"{member.joined_at.strftime('%m/%d/%Y, %H:%M:%S %Z')})" if member else "\n\nUser not found! Please press 📝 and enter the user to " \
                                                                                                          "ban if possible!"
            embed = discord.Embed(title="Possible Spam Report!",
                                  description=f"Spam report detected in {msg.channel.mention} - sent by {msg.author.mention}.{detected_member_str}\n\nImage provided "
                                              f"below:",
                                  color=discord.Color.teal(), url=msg.jump_url)
            if member:
                embed.set_author(name=member.display_name + " <-- NAME (VERIFY MATCH!) PHOTO -->", icon_url=member.avatar_url)
                embed.set_thumbnail(url=member.avatar_url)
            embed.set_image(url=img.url)
            footer = 'Click ✅ to ban user, ❌ to ignore.' if member else 'Click 📝 or ❌ to resolve this message.'
            embed.set_footer(text=footer + " | Detected")
            embed.timestamp = datetime.datetime.utcnow()

            id = member.id if member else "N/A"

            if member:
                report = await spam_report_channel.send(content=f'({member.mention}) SPAM Report for UID: {id}', embed=embed)
                await report.add_reaction('✅')
            else:
                report = await spam_report_channel.send(content=f'SPAM Report for UID: {id}', embed=embed)
            await report.add_reaction('📝')
            await report.add_reaction('❌')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id:
            if str(payload.emoji) in ['✅', '❌', '📝']:
                print("DETECTED CHECK/X REACTION")
                spam_reports_channel: discord.TextChannel = self.client.variables[payload.guild_id]['spam_reports']
                duplicate_reports_channel: discord.TextChannel = self.client.variables[payload.guild_id]['duplicate_reports']
                if (payload.channel_id == spam_reports_channel.id or payload.channel_id == duplicate_reports_channel.id) and payload.user_id != self.client.user.id:
                    is_spam = True
                    if payload.channel_id == spam_reports_channel.id:
                        msg: discord.Message = await spam_reports_channel.fetch_message(payload.message_id)
                    else:
                        msg: discord.Message = await duplicate_reports_channel.fetch_message(payload.message_id)
                        is_spam = False
                    if ('SPAM Report' in msg.content or 'DUPLICATE Report' in msg.content) and msg.author.id == self.client.user.id:
                        print("Reaction added to report channel")
                        embed: discord.Embed = msg.embeds[0]

                        if is_spam:
                            url = embed.image.url

                        edit = True

                        def resolve_report(title):
                            embed.title = title
                            embed.description = f"Click title for original message.\t\t[[Image link]({url})]\n" if is_spam else ""
                            if not is_spam:
                                embed.clear_fields()
                            embed.description += f"Resolved by: {payload.member.name}#{payload.member.discriminator}"
                            embed.color = discord.Color.red()

                        if str(payload.emoji) == '❌':
                            resolve_report(f"Resolved: Not {'Spam' if is_spam else 'Duplicate'}")
                        elif str(payload.emoji) == '📝':
                            try:
                                await msg.delete()
                            except discord.DiscordException:
                                resolve_report(f"Resolved: Moved below for member specification.")

                            msg = await msg.channel.send(msg.content, embed=embed)

                            find_embed = discord.Embed(title="Member Selection", description="Please enter the username of the member in this spam report.\n\nType `CANCEL` to "
                                                                                             "cancel this process.",
                                                       color=discord.Color.blue())
                            find_msg = await msg.channel.send(embed=find_embed)
                            member = None

                            def check(m):
                                return m.author.id == payload.user_id and m.channel == msg.channel

                            while True:
                                try:
                                    name_msg = await self.client.wait_for('message', timeout=400, check=check)
                                except asyncio.TimeoutError:
                                    resolve_report("Timed out! Member not specified in time!")
                                    try:
                                        await find_msg.delete()
                                        break
                                    except discord.DiscordException:
                                        break
                                try:
                                    try:
                                        await name_msg.delete()
                                    except discord.DiscordException:
                                        pass

                                    if name_msg.content[0] == get_prefix(self.client, msg):
                                        continue
                                    if name_msg.content.strip() == 'CANCEL':
                                        break
                                    elif name_msg.content.strip() == 'RESOLVE':
                                        member = -1
                                        break

                                    nicks = [m.display_name for m in name_msg.guild.members]
                                    matches = difflib.get_close_matches(name_msg.content, nicks, cutoff=0.8)
                                    print('')
                                    print(matches)
                                    mems = [m for m in name_msg.guild.members if m.display_name in matches]
                                    print(mems)

                                    if not mems:
                                        nicks = []
                                        map = {}
                                        for m in name_msg.guild.members:
                                            n = unidecode(m.name)
                                            nicks.append(n)
                                            map[n] = m
                                        matches = difflib.get_close_matches(name_msg.content, nicks, cutoff=0.65)
                                        print(f"Uni Matches: {matches}")
                                        mems = [map.get(n) for n in matches]
                                        if not mems:
                                            await msg.channel.send(f"No members found with the input: `{name_msg.content}`! Type another name, __CANCEL__ to cancel, or __RESOLVE__ to "
                                                                   f"resolve this report.", delete_after=10)
                                            continue

                                    embeds = []
                                    mems.reverse()
                                    for i, m in enumerate(mems, start=1):
                                        embd = discord.Embed(description=f"{m.mention} ({m.name}#{m.discriminator})\n\n"
                                                                         f"If this is the correct member, press the ✅ reaction below.\nIf not, use the arrows to browse "
                                                                         f"other members with similar names.\n\nIf no members are correct, use the ❌.", color=discord.Color.blue())
                                        embd.set_author(name=m.display_name, icon_url=m.avatar_url)
                                        embd.set_thumbnail(url=m.avatar_url)
                                        embd.set_footer(text=f"Match {i}/{len(mems)}")
                                        embeds.append(embd)

                                    await msg.channel.send(''.join([m.mention for m in mems]), delete_after=0.01)
                                    paginator = utils.EmbedPaginator(self.client, msg.channel, payload.member, embeds)
                                    index = await paginator.paginate(search=True)  # index of result, or -1 if cancelled
                                    if index != -1:
                                        member = mems[index]
                                    break
                                except BaseException:
                                    pass

                            try:
                                await find_msg.delete()
                            except discord.DiscordException:
                                pass

                            if member == -1:
                                embed.title = "Resolved: Scam detected - Account not found!"
                                embed.description = f"The detected user was attempted to be banned, but the associated account could not be found.\n" \
                                                    f"Resolved by: {payload.member.name}#{payload.member.discriminator}"
                                if is_spam:
                                    embed.description += f"Click title for original message.\t\t[[Image link]({url})]\n"
                                embed.color = discord.Color.purple()
                            elif member is not None:
                                try:
                                    print("Trying to ban member...")
                                    await spam_reports_channel.guild.ban(user=member, reason=f'Banned for {"spamming" if is_spam else "duplicate name"} '
                                                                                             f'by {payload.member.name}#{payload.member.discriminator}',
                                                                         delete_message_days=7)
                                    print(f"Successfully banned: {payload.member.name}#{payload.member.discriminator}")
                                    # await duplicate_reports_channel.send("TESTING: MEMBER BANNED HERE!")
                                except discord.Forbidden:
                                    return await spam_reports_channel.send("Missing Permissions to ban member!")
                                if is_spam:
                                    ban_embed = discord.Embed(description=f"{member.mention} ({member.name}#{member.discriminator}) was banned for "
                                                                          f"{'spamming' if is_spam else 'duplicate name'}.",
                                                              color=discord.Color.gold())
                                    ban_embed.set_author(name='Member Banned', icon_url=member.avatar_url)
                                    ban_embed.set_footer(text=f'ID: {member.id}')
                                    submission_channel = self.client.get_channel(int(embed.url.split('channels/')[1].split("/")[1]))
                                    author_mention = '<@' + embed.description.split('<@')[1].split('>')[0] + '>'
                                    await submission_channel.send(f'{author_mention} - Thank you for your report!', embed=ban_embed)
                                else:
                                    embed.clear_fields()

                                embed.title = "Resolved: Member Banned"
                                embed.description = f"{member.mention} ({member.name}#{member.discriminator}) was banned for {'spamming' if is_spam else 'duplicate name'}.\n\n"
                                if is_spam:
                                    embed.description += f"Click title for original message.\t\t[[Image link]({url})]\n"
                                embed.description += f"Resolved by: {payload.member.name}#{payload.member.discriminator}"
                                embed.color = discord.Color.green()
                            else:
                                await msg.add_reaction('📝')
                                await msg.add_reaction('❌')
                                edit = False


                        elif str(payload.emoji) == '✅':
                            print("Check reaction, ban member!")
                            uid = msg.content.split('UID: ')[1]
                            if uid.isdigit():
                                member = spam_reports_channel.guild.get_member(int(uid))
                                if not member:
                                    print("trying to get USER account")
                                    _user = await self.client.fetch_user(int(uid))
                                    if _user is not None:
                                        member = _user
                                if member is not None:
                                    try:
                                        print("Trying to ban member...")
                                        await spam_reports_channel.guild.ban(user=member, reason=f'Banned for {"spamming" if is_spam else "duplicate name"} '
                                                                                                 f'by {payload.member.name}#{payload.member.discriminator}',
                                                                             delete_message_days=7)
                                        print(f"Successfully banned: {payload.member.name}#{payload.member.discriminator}")
                                        # await duplicate_reports_channel.send("TESTING: MEMBER BANNED HERE!")
                                    except discord.Forbidden:
                                        return await spam_reports_channel.send("Missing Permissions to ban member!")
                                    if is_spam:
                                        ban_embed = discord.Embed(description=f"{member.mention} ({member.name}#{member.discriminator}) was banned for "
                                                                              f"{'spamming' if is_spam else 'duplicate name'}.",
                                                                  color=discord.Color.gold())
                                        ban_embed.set_author(name='Member Banned', icon_url=member.avatar_url)
                                        ban_embed.set_footer(text=f'ID: {member.id}')
                                        submission_channel = self.client.get_channel(int(embed.url.split('channels/')[1].split("/")[1]))
                                        author_mention = '<@' + embed.description.split('<@')[1].split('>')[0] + '>'
                                        await submission_channel.send(f'{author_mention} - Thank you for your report!', embed=ban_embed)
                                    else:
                                        embed.clear_fields()

                                    embed.title = "Resolved: Member Banned"
                                    embed.description = f"{member.mention} ({member.name}#{member.discriminator}) was banned for {'spamming' if is_spam else 'duplicate name'}.\n\n"
                                    if is_spam:
                                        embed.description += f"Click title for original message.\t\t[[Image link]({url})]\n"
                                    embed.description += f"Resolved by: {payload.member.name}#{payload.member.discriminator}"
                                    embed.color = discord.Color.green()
                                else:
                                    embed.title = "Resolved: Scam detected - USER account deleted!"
                                    embed.description = f"The detected user was attempted to be banned, but the associated account has since been deleted.\n" \
                                                        f"Resolved by: {payload.member.name}#{payload.member.discriminator}" + "\n\n__User Detected:__" \
                                                        + embed.description.split("__User Detected:__")[1]
                                    if is_spam:
                                        embed.description += f"Click title for original message.\t\t[[Image link]({url})]\n"
                                    embed.color = discord.Color.orange()
                            else:
                                return

                        if edit:
                            embed.remove_author()
                            embed.set_image(url=discord.Embed.Empty)
                            embed.set_footer(text="Resolved at ")
                            embed.timestamp = datetime.datetime.utcnow()
                            try:
                                await msg.edit(content="", embed=embed)
                                await msg.clear_reactions()
                            except discord.Forbidden or discord.HTTPException:
                                pass
            elif payload.channel_id in [396316232124727296, 797960110310686760, 804133361378656287] and str(payload.emoji) == '♻️' and\
                (payload.member.top_role >= self.client.variables[payload.guild_id]['min_staff_role'] or payload.user_id == 196282885601361920):
                    channel = self.client.get_channel(payload.channel_id)
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.remove_reaction(payload.emoji, payload.member)
                    img = msg.attachments[0]
                    if img.height:
                        data, img, response = await self.check_spam_img(img, msg, False)
                        await self.send_spam_report(msg, data, img, response)

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

            if photo_hash in self.client.banned_photos.get(member.guild.id, set()):
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
                (days, hours, minutes, seconds) = secondsformatter(seconds_old)

                embed = discord.Embed(title=f"YOU HAVE BEEN KICKED FROM {member.guild.name}!",
                                      description=f"Your account creation date is less than this server's minimum!", color=discord.Color.red())
                log_embed = discord.Embed(title=f"{member.name}#{member.discriminator} has been kicked!**",
                                          description=f"Account under minimum creation date! ({seconds_old}s < {min_account_age_seconds}s minimum)!\n"
                                                      f"\n**Mention:** {member.mention}"
                                                      f"\n**Id :** {member.id}",
                                          color=discord.Color.orange())

                embed.add_field(name="Current Account Age:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)
                log_embed.add_field(name="Current Account Age:", value=f"**{days}**d, **{hours}**h, **{minutes}**m, **{seconds}**s", inline=True)

                (days, hours, minutes, seconds) = secondsformatter(min_account_age_seconds)
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
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.avatar != after.avatar:
            if not after.avatar:
                photo_hash = str(after.default_avatar)
            else:
                photo_hash = await utils.get_photo_hash(self.client, after)
            print(f"USER UPDATED AVATAR! (ID: {after.id}) | Hash: {photo_hash}")
            if photo_hash:
                await sql.update_photo_hash(self.client.pool, after.id, photo_hash, new=False)


def setup(client):
    client.add_cog(Events(client))


def secondsformatter(total_seconds):
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return days, hours, minutes, seconds


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

import asyncio
import datetime
import functools
import io
import json
import os
import shutil
import string
from random import random

import Augmentor as Augmentor
import discord
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from cogs.logging import sendLog


class Events(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        log_channel: discord.TextChannel = self.client.variables[member.guild.id]['log_channel']
        captcha_channel: discord.TextChannel = self.client.variables[member.guild.id]['captcha_channel']
        min_account_age_seconds = self.client.variables[member.guild.id]['min_account_age_seconds']

        memberTime = f"{member.joined_at.year}-{member.joined_at.month}-{member.joined_at.day} {member.joined_at.hour}:{member.joined_at.minute}:{member.joined_at.second}"

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

                await sendLog(self.client, member.guild, log_channel, embed=embed, event="onJoin Account Age", action="Member Kicked")

                await member.send(embed=embed)
                await member.kick(reason=f"Account under minimum creation date! ({seconds_old}s < {min_account_age_seconds}s minimum)")  # Kick the user


        if self.client.variables[member.guild.id]['captcha_status']:
            # Give temporary role
            await member.add_roles(self.client.variables[member.guild.id]['temporary_role'])

            file, text, folderPath = await self.client.loop.run_in_executor(functools.partial(create_captcha, member))
            
            captcha_msg = await captcha_channel.send(
                f"{member.mention} - Please solve the captcha below to gain access to the server! (6 uppercase letters).",
                file=file)
            # Remove captcha folder
            try:
                shutil.rmtree(folderPath)
            except Exception as error:
                await sendLog(self.client, member.guild, log_channel, embed=self.client.warning_embed, event=f"Delete captcha file failed {error}")

            # Check if it is the right user
            def check(message):
                if message.author == member and message.content != "":
                    return message.content

            try:
                msg = await self.client.wait_for('message', timeout=120.0, check=check)
                # Check the captcha
                password = text.split(" ")
                password = "".join(password)
                if msg.content == password:

                    embed = discord.Embed(description=f"{member.mention} passed the captcha.", color=0x2fa737)  # Green
                    await captcha_channel.send(embed=embed, delete_after=5)
                    # Give and remove roles
                    try:
                        veri_role = self.client.variables[member.guild.id]['verified_role']
                        if veri_role:
                            await member.add_roles(veri_role)
                    except Exception as error:
                        await sendLog(self.client, member.guild, log_channel, self.client.error_embed, event=f"Failed to give member {member.mention} the verified role!")
                    try:
                        temp_role = self.client.variables[member.guild.id]['temporary_role']
                        if temp_role:
                            await member.remove_roles(temp_role)
                    except Exception as error:
                        await sendLog(self.client, member.guild, log_channel, self.client.error_embed, event=f"Failed to remove the temporary role from member: {member.mention}")

                    await asyncio.sleep(3)

                    try:
                        await captcha_msg.delete()
                        await msg.delete()
                    except discord.Forbidden or discord.HTTPException:
                        await sendLog(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg/ user captcha solution msg!")

                    # Logs
                    embed = discord.Embed(title=f"**{member} passed the captcha.**", description=f"**__User informations :__**\n\n**Name :** {member}\n**Id :** {member.id}",
                                          color=discord.Color.green())
                    embed.set_footer(text=f"at {memberTime}")
                    await sendLog(self.client, member.guild, log_channel, embed=embed, event="Successful Captcha", action=f"Verified Role Given to {member.mention}")

                else:
                    link = await captcha_channel.create_invite(reason='Failed captcha')  # Create an invite
                    embed = discord.Embed(description=f"{member.mention} failed the captcha.", color=discord.Color.red())  # Red
                    await captcha_channel.send(embed=embed, delete_after=5)
                    embed = discord.Embed(title=f"Error! Incorrect Captcha!", description=f"You have been kicked from {member.guild.name}\nReason : You failed the "
                                                                                          f"captcha!\nCorrect answer: __{text}__"
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
                        await sendLog(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg/ user captcha solution msg!")

                    # Logs
                    embed = discord.Embed(title=f"**{member} failed the captcha!**", description=f"**__User information :__**\n\n**Name :** {member}\n**Id :** {member.id}",
                                          color=discord.Color.red())
                    embed.set_footer(text=f"at {memberTime}")
                    await sendLog(self.client, member.guild, log_channel, embed=embed, event="Failed Captcha", action=f"{member.mention} kicked from server")

            except asyncio.TimeoutError:
                link = await captcha_channel.create_invite()  # Create an invite
                embed = discord.Embed(title=f"Timeout!", description=f"{member.mention} has exceeded the response time (120s)!", color=discord.Color.orange())
                await captcha_channel.send(embed=embed, delete_after=5)
                try:
                    embed = discord.Embed(title=f"Error! Captcha response timeout!", description=f"You have been kicked from {member.guild.name}\nReason : You took too long to "
                                                                                                 f"answer the captcha! (120s) \n Correct answer: __{text}__\n"
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
                    await sendLog(self.client, member.guild, log_channel, self.client.error_embed, event="Failed to delete captcha msg!")

                # Logs
                embed = discord.Embed(title=f"**{member} timed out while answering captcha!**", description=f"**__User information :__**\n\n**Name :** {member}\n**Id :**"
                                                                                                            f" {member.id}",
                                      color=discord.Color.red())
                embed.set_footer(text=f"at {memberTime}")
                await sendLog(self.client, member.guild, log_channel, embed=embed, event="Captcha Timeout", action=f"{member.mention} kicked from server")


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
    p.random_distortion(probability=1, grid_width=4, grid_height=4, magnitude=14)
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
    co2 = random.randrange(40, 65)
    co4 = random.randrange(40, 65)
    draw = ImageDraw.Draw(image)
    draw.line([(co1, co2), (co3, co4)], width=width, fill=(90, 90, 90))

    # Add noise
    noisePercentage = 0.25  # 25%

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
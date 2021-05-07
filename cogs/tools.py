import asyncio
import datetime
import json

import aiohttp
import discord
from discord.ext import commands

import utils


class Tools(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(usage='convert <amount> <currency_code> to <currency_code>', description="Convert a currency into another\nEx: `convert 10 USD to EUR`")
    @commands.cooldown(1, 5, discord.ext.commands.BucketType.member)
    async def convert(self, ctx, amount, *, currency):
        currency = currency.upper()

        error = discord.Embed(title='Error!', color=discord.Color.red())

        try:
            amount = float(amount)
        except ValueError:
            error.description = f"Please provide an amount in a number format!\n\nEx: `{ctx.prefix}convert 100 USD to EUR`"
            return await ctx.send(embed=error)

        if 'TO' not in currency:
            error.description = f"Please provide an amount and two currency codes!\n\nEx: `{ctx.prefix}convert 100 USD to BTC`"
            return await ctx.send(embed=error)

        with open('data/currencies.json') as f:
            currency_data = json.load(f)

        currency = currency.split(' TO ')
        if currency[0] not in currency_data['all'] or currency[1] not in currency_data['all']:
            badarg = currency[0] if currency[0] not in currency_data['all'] else currency[1]
            error.description = f"Currency code: **{badarg}** was not found in fiat or crypto symbols! Please use a valid currency symbol!"
            return await ctx.send(embed=error)

        msg = await ctx.send("Fetching Exchange Rate data...")
        data = None

        if currency[0] == currency[1]:
            price = amount
        else:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(10)) as cs:
                    for i in range(2):
                        async with cs.get(f'https://pro-api.coinmarketcap.com/v1/tools/price-conversion?symbol={currency[0]}&convert={currency[1]}&amount={amount}',
                                          headers={'X-CMC_PRO_API_KEY': self.client.CMC_TOKEN}) as r:
                            if r.status != 200:
                                await msg.edit(f"I'm having trouble fetching current exchange rates! (Status: {r.status})... Retrying ({i}/3)")
                                continue
                            data = await r.json()
                            if data['status']['error_code'] != 0:
                                await msg.edit(f"I'm having trouble fetching current exchange rates!... Retrying ({i+1}/3)")
                                continue
                            break
            except (asyncio.TimeoutError, aiohttp.ClientError):
                error.description = "Retrieval of exchange rates took too long! Please try running the command later."
                return await msg.edit(content="", embed=error)

            price = data['data']['quote'][currency[1]]['price']

        embed = discord.Embed(title=f"{price:,.6g} {currency[1]}", description=f"{amount} {currency[0]} is **__{price:,.8g}__** {currency[1]}", color=discord.Color.green(),
                              url=f'https://coinmarketcap.com/converter/{currency[0]}/{currency[1]}/?amt={amount}')
        embed.add_field(name="Conversion Rate", value=f"1 {currency[0]} = {price/amount:,.6g} {currency[1]}")
        embed.set_footer(text="Conversion Generated ")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(content="", embed=embed)

    @commands.command(usage='remindme <time>', description="Set a reminder to be given a specified time later.")
    async def remindme(self, ctx, duration: utils.Duration):
        if not ctx.message.reference:
            return await ctx.send("Please use this command by replying to the message you'd like to be reminded about!")

        total_seconds = (duration - datetime.datetime.utcnow()).total_seconds()
        resolved = ctx.message.reference.resolved
        content = resolved.content if resolved and resolved.content else ""

        with open('data/reminders.json',) as file:
            reminders = json.load(file, )

        name = reminders[str(ctx.guild.id)]['name']
        photo = reminders[str(ctx.guild.id)]['photo']
        data = (duration.timestamp(), ctx.message.reference.jump_url, resolved.author.name, str(resolved.author.avatar_url), content)

        if str(ctx.author.id) in reminders[str(ctx.guild.id)] and reminders[str(ctx.guild.id)][str(ctx.author.id)] is not None:
            if len(reminders[str(ctx.guild.id)][str(ctx.author.id)]) > 9:
                return await ctx.send("You cannot have more than 10 pending reminders! Wait until one expires before creating another.")
            reminders[str(ctx.guild.id)][str(ctx.author.id)].append(data)
        else:
            reminders[str(ctx.guild.id)][str(ctx.author.id)] = [data]

        try:
            embed = discord.Embed(title="Reminder Set!", url=ctx.message.reference.jump_url, description=f"I will be reminding you about the linked message in:\n"
                                  f"__{utils.duration_formatter(total_seconds, 'reminder').split('issued for ')[1]}__",
                                  color=discord.Color.green())
            embed.set_footer(text="You will be reminded")
            embed.set_thumbnail(url='https://i.imgur.com/1b2ietu.gif')
            embed.timestamp = duration
            if content:
                embed.add_field(name="Message Content:", value=content)
            await ctx.author.send(embed=embed)

            with open('data/reminders.json', 'w') as file:
                json.dump(reminders, file, indent=4)
        except discord.Forbidden:
            await ctx.message.add_reaction("❌")
            return await ctx.send("Please enable DM's to use this command!")
        except discord.DiscordException:
            return

        await ctx.message.add_reaction("✅")
        await reminder(ctx.author, ctx.guild.id, name, photo, total_seconds, ctx.message.reference.jump_url, resolved.author.name, resolved.author.avatar_url, content)

    @commands.command(usage='greed', description="Retrieve the current Crypto Fear & Greed Index", aliases=['fear', 'fng'])
    @commands.cooldown(1, 5, discord.ext.commands.BucketType.member)
    async def greed(self, ctx):
        error = discord.Embed(title='Error!', color=discord.Color.red())
        msg = await ctx.send("Fetching Index data...")
        data = None

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(10)) as cs:
                for i in range(2):
                    async with cs.get(f'https://api.alternative.me/fng/') as r:
                        if r.status != 200:
                            await msg.edit(f"I'm having trouble fetching current index data! (Status: {r.status})... Retrying ({i}/3)")
                            continue
                        data = await r.json()
                        if not data:
                            await msg.edit(f"I'm having trouble fetching current index data!... Retrying ({i + 1}/3)")
                            continue
                        break
        except (asyncio.TimeoutError, aiohttp.ClientError):
            error.description = "Retrieval of index data took too long! Please try running the command later."
            return await msg.edit(content="", embed=error)

        num = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']

        if num >= 90:
            colorCode = 0x65c64c
        if num < 90:
            colorCode = 0x79d23c
        if num <= 75:
            colorCode = 0x9bbe44
        if num <= 63:
            colorCode = 0xc6bf22
        if num <= 54:
            colorCode = 0xdfce60
        if num <= 46:
            colorCode = 0xd8bc59
        if num <= 35:
            colorCode = 0xe39d64
        if num <= 25:
            colorCode = 0xd17339
        else:
            colorCode = 0xb74d34

        embed = discord.Embed(title=f"Crypto Fear and Greed Index", url="https://alternative.me/crypto/fear-and-greed-index/", color=colorCode)
        embed.add_field(name=num, value=f"{classification}")
        embed.set_footer(text="Retrieved ")
        embed.set_image(url='https://alternative.me/crypto/fear-and-greed-index.png')
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(content="", embed=embed)

    @commands.command(usage='stats', description='Show my member stats!')
    async def stats(self, ctx):
        embed = discord.Embed(title=f"Stats for {ctx.guild.name}", color=discord.Color.dark_gold())
        entries = await ctx.guild.audit_logs(limit=None, user=ctx.guild.me, action=discord.AuditLogAction.ban).flatten()
        # kicked = len(list(filter(lambda entry: entry.action == discord.AuditLogAction.kick, entries)))
        embed.description = f"__Moderation Action Stats:__\n**{len(entries)}** members banned for scamming!"
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.add_field(name="Bot latency:", value=f"**`{round(self.client.latency * 1000, 2)}`** Milliseconds.")
        mcount = 0
        for g in self.client.guilds:
            mcount += g.member_count
        embed.add_field(name="Connected Servers:",
                        value=f"**`{len(self.client.guilds)}`** servers with **`{mcount}`** total members.")
        embed.add_field(name="\u200b", value="\u200b")
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(Tools(client))


async def reminder(user, guild_id, guild_name, guild_icon, t_seconds, jump_url, author_name, author_pfp, content):
    await asyncio.sleep(t_seconds)

    embed = discord.Embed(title="Link to Message (Click Me!)", url=jump_url, description=f"Message sent in {guild_name} by {author_name}", color=discord.Color.gold())
    embed.set_author(name=author_name, icon_url=author_pfp)
    embed.set_thumbnail(url=guild_icon)
    if content:
        embed.add_field(name="Message Content:", value=content)

    try:
        await user.send("⚠️ Reminder ⚠️", embed=embed)
    except discord.DiscordException:
        pass

    with open('data/reminders.json') as file:
        reminders = json.load(file)

    if reminders[str(guild_id)][str(user.id)]:
        for r in reminders[str(guild_id)][str(user.id)]:
            if r[1] == jump_url:
                if reminders[str(guild_id)][str(user.id)] is None or len(reminders[str(guild_id)][str(user.id)]) == 1:
                    data = reminders[str(guild_id)].copy()
                    del data[str(user.id)]
                    reminders[str(guild_id)] = data
                else:
                    reminders[str(guild_id)][str(user.id)] = reminders[str(guild_id)][str(user.id)].remove(r)

    with open('data/reminders.json', 'w') as file:
        json.dump(reminders, file, indent=4, )

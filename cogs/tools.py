import asyncio
import datetime
import json

import aiohttp
import discord
from discord.ext import commands


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
            res = amount
            rate = 1
        else:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(10)) as cs:
                    for i in range(2):
                        async with cs.get(f'https://api.exchangerate.host/convert?from={currency[0]}&to={currency[1]}&amount={amount}&source=crypto') as r:
                            if r.status != 200:
                                await msg.edit(f"I'm having trouble fetching current exchange rates! (Status: {r.status})... Retrying ({i}/3)")
                                continue
                            data = await r.json()
                            if data['success'] is not True:
                                await msg.edit(f"I'm having trouble fetching current exchange rates!... Retrying ({i+1}/3)")
                                continue
                            break
            except (asyncio.TimeoutError, aiohttp.ClientError):
                error.description = "Retrieval of exchange rates took too long! Please try running the command later."
                return await msg.edit(content="", embed=error)

            res = data['result']
            rate = data['info']['rate']

        embed = discord.Embed(title=f"{res:,.2f} {currency[1]}", description=f"{amount} {currency[0]} is **__{res:,.2f}__** {currency[1]}", color=discord.Color.green())
        embed.add_field(name="Conversion Rate", value=f"1 {currency[0]} = {rate:,.5f} {currency[1]}")
        embed.set_footer(text="Conversion Generated ")
        embed.timestamp = datetime.datetime.utcnow()
        await msg.edit(content="", embed=embed)

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

def setup(client):
    client.add_cog(Tools(client))
import json

import discord
from discord.ext import commands


class Logging(commands.Cog):

    def __init__(self, client):
        self.client = client


def setup(client):
    client.add_cog(Logging(client))


async def send_log(client, guild, channel, embed, event: str = None, action="Not Specified"):
    """Placeholder logging"""

    if not channel:
        with open('data/variables.json') as f:
            data = json.load(f)

        log_channel = data[str(guild.id)]['channels']['log_channel']
        if log_channel:
            channel = client.get_channel(log_channel)
            if not channel:
                return
            else:
                client.variables[guild.id]['log_channel'] = channel
        else:
            return

    print(f"sending log in channel: {channel.name} id: {channel.id} for guild {guild.name}")
    # Send the message
    if embed == client.warning_embed or embed == client.error_embed:
        embed: discord.Embed = embed
        embed.description = "__EVENT:__ " + event + "\n__ACTION:__ " + action
        await channel.send(embed=embed)
    else:
        await channel.send(content=f"Log for event: {event}, action taken: {action}", embed=embed)

    # TODO: Log to console/action file

import datetime
import enum
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

        channel = client.variables[guild.id]['log_channel']
        if not channel:
            with open('data/variables.json') as f:
                data = json.load(f)

                log_channel = data[str(guild.id)]['channels']['log_channel']
                if log_channel:
                    channel = client.get_channel(log_channel)
                    if not channel:
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


async def action_log(client: discord.Client, member: discord.Member, is_ban: bool, reason: str):
    embed = discord.Embed(description=f"{member.mention} {member.name}#{member.discriminator}", color=discord.Color.from_rgb(0, 0, 0) if is_ban else discord.Color.red())
    embed.set_author(name="Banned " if is_ban else "Kicked [" + reason + "]", icon_url=member.avatar)
    embed.set_thumbnail(url=member.avatar)
    embed.set_footer(text=f"ID: {member.id}")
    if not all(ord(char) < 128 for char in member.name):
        embed.add_field(name="Unicode Name:", value=f"`{member.name}` - decoded: `{member.name.encode('unicode-escape')}`")
    embed.timestamp = datetime.datetime.utcnow()

    log_channel = client.variables[member.guild.id]['log_channel']
    await log_channel.send(embed=embed)


class VerifyAction(enum.Enum):
    START_VERIFICATION = ("📥", "Has started the verification process.")
    TIMEOUT = ("⏰", "Timed out while attempting a captcha.")
    RETRY = ("🔄", "Entered a wrong solution and is Retrying")
    COMPLETED = ("✅", "Completed the Verification")
    FAILED = ("📤", "Failed the captcha 3 times and will be kicked.")
    EXPIRED = ("❌", "Exceeded the time limit to attempt the captcha and will be kicked.")


async def verify_log(client, guild, member, action: VerifyAction):
    await client.variables[guild.id]['verify_log_channel'].send(f"{action.value[0]}{member.mention}{action.value[1]}")



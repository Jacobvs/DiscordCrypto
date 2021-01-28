import discord
from discord.ext import commands


def is_staff_check():
    """Check if user is staff in the server"""
    def predicate(ctx):
        db = ctx.bot.guild_db.get(ctx.guild.id)
        role = db['min_staff_role']
        return ctx.author.top_role >= role
    return commands.check(predicate)


def is_role_or_higher(member, role):
    """Base check for if user has a role or higher"""
    if member:
        if member.top_role:
            return member.top_role >= role
        return False
    return False


def has_manage_roles():
    def predicate(ctx):
        return ctx.author.guild_permissions.manage_roles
    return commands.check(predicate)

def in_voice_channel():
    """Check if user is in a voice channel"""
    def predicate(ctx):
        if ctx.author.voice is None:
            return False
        return True
    return commands.check(predicate)

def is_dj():
    """Check if user has a role named 'DJ'"""
    def predicate(ctx):
        if ctx.message.author.guild_permissions.administrator:
            return True
        role = discord.utils.get(ctx.guild.roles, name="DJ")
        if role in ctx.author.roles:
            return True
        #await ctx.say("The 'DJ' Role is required to use this command.", delete_after=4)
        return False
    return commands.check(predicate)


# async def audio_playing(ctx):
#     """Checks that audio is currently playing before continuing."""
#     client = ctx.guild.voice_client
#     if client and client.channel and client.source:
#         return True
#     else:
#         raise commands.CommandError("Not currently playing any audio.")
#
# async def in_same_voice_channel(ctx):
#     """Checks that the command sender is in the same voice channel as the bot."""
#     voice = ctx.author.voice
#     bot_voice = ctx.guild.voice_client
#     if voice and bot_voice and voice.channel and bot_voice.channel and voice.channel == bot_voice.channel:
#         return True
#     else:
#         raise commands.CommandError("You need to be in the same voice channel as the bot to use this command.")
#
# async def is_audio_requester(ctx):
#     """Checks that the command sender is the song requester."""
#     music = ctx.bot.get_cog("Music")
#     state = music.get_state(ctx.guild)
#     permissions = ctx.channel.permissions_for(ctx.author)
#     if permissions.administrator or state.is_requester(ctx.author):
#         return True
#     else:
#         raise commands.CommandError("You need to be the song requester or an admin to use this command.")

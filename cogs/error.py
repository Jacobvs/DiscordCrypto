import logging
import traceback

import discord
from discord.ext import commands


class ErrorHandler(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_command_error(self, ctx: discord.ext.commands.Context, error):
        """Handles command errors"""
        if hasattr(ctx.command, "on_error"):
            return  # Don't interfere with custom error handlers

        error = getattr(error, "original", error)  # get original error
        logging.error("Ignoring exception in command {}:".format(ctx.command))
        logging.error("\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__)))

        if isinstance(error, commands.CommandNotFound):
            await ctx.message.delete()
            return await ctx.send(f"That command does not exist. Please use `{ctx.prefix}commands` for "
                                  f"a list of commands, or `{ctx.prefix}help` for more information.", delete_after=15)

        if isinstance(error, commands.MissingPermissions):
            await ctx.message.delete()
            # return await ctx.send(f'{ctx.author.mention} Does not have the perms to use this: `{ctx.command.name}` command.', delete_after=15)

        if isinstance(error, commands.MissingRole):
            await ctx.message.delete()
            return await ctx.send(f'{ctx.author.mention}: ' + str(error))

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("This command cannot be used in a DM.")

        if isinstance(error, commands.CheckFailure) or isinstance(error, commands.CheckAnyFailure):
            # if not self.client.maintenance_mode and error:
                # await ctx.send(f"You do not have permission to use this command (`{ctx.prefix}{ctx.command.name}`).", delete_after=15)  # \nCheck(s) failed: {failed}")
            return await ctx.message.delete()

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"To prevent overload, this command is on cooldown for: ***{round(error.retry_after)}*** more seconds. Retry the command then.",
                delete_after=5)
            return await ctx.message.delete()

        if isinstance(error, commands.MaxConcurrencyReached):
            return await ctx.send(f"The maximum number of concurrent usages of this command has been reached ({error.number}/{error.number})! Please wait until the previous "
                                  f"execution "
                                  f"of the command `{ctx.prefix}{ctx.command.name}` is completed!")

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(title="Error!", description="You appear to be missing a required argument!", color=discord.Color.red())
            embed.add_field(name="Missing argument", value=f'`{error.args[0]}`', inline=False)
            embed.add_field(name="Command Usage", value=f'`{ctx.command.usage}`', inline=False)
            if ctx.command.aliases:
                aliases = "`" + "".join("!" + c + ", " for c in ctx.command.aliases) + "`"
                embed.add_field(name="Command Aliases", value=f"{aliases}", inline=False)
            return await ctx.send(embed=embed, delete_after=20)

        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(title="Error!", description="An argument you entered is invalid!", color=discord.Color.red())
            embed.add_field(name="Bad Argument", value=f'`{error.args[0]}`', inline=False)
            embed.add_field(name="Command Usage", value=f'`{ctx.command.usage}`', inline=False)
            if ctx.command.aliases:
                aliases = "`" + "".join("!" + c for c in ctx.command.aliases) + "`"
                embed.add_field(name="Command Aliases", value=f"{aliases}", inline=False)
            return await ctx.send(embed=embed, delete_after=20)

        if isinstance(error, discord.ext.commands.errors.ExtensionNotLoaded):
            embed = discord.Embed(title="Error!", description="Cog not found!", color=discord.Color.red())
            embed.add_field(name="Bad Argument", value=f'`{error.args[0]}`', inline=False)
            embed.add_field(name="Command Usage", value=f'`{ctx.command.usage}`', inline=False)
            embed.add_field(name='Loaded Cogs:', value="".join("`" + c + "`\n" for c in sorted(self.client.cogs)), inline=False)
            return await ctx.send(embed=embed, delete_after=20)

        if isinstance(error, commands.CommandError):
            return await ctx.send(f"Unhandled error while executing command `{ctx.command.name}`: {str(error)}", delete_after=20)

        await ctx.send("An unexpected error occurred while running that command. Please report this by sending a DM to Darkmatter#7321.", delete_after=20)


def setup(client):
    client.add_cog(ErrorHandler(client))

import asyncio
import json
import random
import string
from typing import Optional, Dict, Any, List, Tuple
import discord
import numpy as np
from discord.webhook.async_ import async_context
import sql
from cogs.logging import verify_log, VerifyAction
from main import CryptoBot

completed_embed = discord.Embed(title="Successfully Verified!", description="\n\nYou can dismiss this message below. The verified role will be added within 30s.",
                                             color=discord.Color.green(), timestamp=discord.utils.utcnow())
completed_embed.set_footer(text="©Cryptographer")

timed_out_embed = discord.Embed(title="Error! Timed out.", description="You didn't complete the captcha in time (90s limit)! Please press the verify button above to try "
                                                                       "again.\n\nYou can dismiss this message below.", color=discord.Color.red())
timed_out_embed.set_footer(text="©Cryptographer")


class CaptchaButton(discord.ui.Button['Captcha']):
    def __init__(self, x: int, y: int, label: str):
        # A label is required, but we don't need one so a zero-width space is used
        # The row parameter tells the View which row to place the button under.
        # A View can only contain up to 5 rows -- each row can only have 5 buttons.
        # Since a Tic Tac Toe grid is 3x3 that means we have 3 rows and 3 columns.
        super().__init__(style=discord.ButtonStyle.primary if x == 0 else discord.ButtonStyle.secondary, label=label, row=y, disabled=x != 0)
        self.x = x
        self.y = y

    # This function is called whenever this particular button is pressed
    # This is part of the "meat" of the game logic
    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: CaptchaView = self.view
        state = view.board[self.y][self.x]

        if state != '-1':
            if self.x == 4:
                for btn in view.children:
                    if isinstance(btn, CaptchaButton):
                        btn.disabled = True
                        if view.board[btn.y][btn.x] != "-1":
                            btn.style = discord.ButtonStyle.success
                        else:
                            btn.style = discord.ButtonStyle.secondary
                    if isinstance(btn, RefreshCaptchaButton):
                        btn.disabled = True
                view.stop()
                await complete_verification(interaction.user, view.verify_role)
            else:
                self.style = discord.ButtonStyle.success
                self.disabled = True
                for btn in view.children:
                    if isinstance(btn, CaptchaButton):
                        if btn.x == self.x and btn.y != self.y:
                            btn.disabled = True
                            btn.style = discord.ButtonStyle.secondary
                        elif btn.x == self.x+1:
                            btn.disabled = False
                            btn.style = discord.ButtonStyle.primary
                    elif self.x == 0 and isinstance(btn, RefreshCaptchaButton):
                            btn.disabled = True

        else:
            self.style = discord.ButtonStyle.danger
            for btn in view.children:
                if isinstance(btn, CaptchaButton):
                    btn.disabled = True
                    if btn.x != self.x or btn.y != self.y:
                        if view.board[btn.y][btn.x] != '-1':
                            btn.style = discord.ButtonStyle.success
                        else:
                            btn.style = discord.ButtonStyle.secondary
                if isinstance(btn, RefreshCaptchaButton):
                    btn.disabled = False

            view.stop()
            await asyncio.sleep(2)
            for btn in view.children:
                if isinstance(btn, RefreshCaptchaButton):
                    return await btn.callback(interaction, failed=True)

        await interaction.response.edit_message(embed=view.embed, view=view)


class RefreshCaptchaButton(discord.ui.Button['NewCaptcha']):
    """Button to Get a new Captcha"""

    def __init__(self):
        super().__init__(label="New Captcha", emoji='🔄', style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction, failed: bool = False):
        assert self.view is not None
        view: CaptchaView = self.view
        if not view.is_finished():
            view.stop()

        if failed:
            view.attempt += 1

        if view.attempt > 3:
            await verify_log(view.client, interaction.guild, interaction.user, VerifyAction.FAILED)
            embed = discord.Embed(title="Error!", description="You have exceeded the allowable attempt limit for this server.\n"
                                                              "To prevent spam-bots you will be kicked from the server in 15s."
                                                              "\n\nYou can rejoin the server with a new link to attempt the captcha again.",
                                                 color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_footer(text="©Cryptographer")
            await interaction.response.edit_message(embed=embed, view=None)
            await asyncio.sleep(15)
            await interaction.channel.send("[DEBUG LOG: RFCButton] Failed 3/3 - MEMBER KICKED HERE")
        else:
            await verify_log(view.client, interaction.guild, interaction.user, VerifyAction.RETRY)


        with open('data/captchas.json') as file:
            data = json.load(file)

        code, img = random.choice(list(data.items()))

        embed = discord.Embed(title="Complete the Captcha!",
                              description=f"Press each letter one-by-one using the buttons below.\n\nAttempt __{view.attempt}/3__",
                              color=discord.Color.gold())
        embed.set_image(url=img)
        new_view = CaptchaView(code, view.attempt, embed, view.verify_role, view.client)
        await interaction.response.edit_message(embed=embed, view=new_view)
        if await new_view.wait():
            await verify_log(view.client, interaction.guild, interaction.user, VerifyAction.TIMEOUT)
            await new_view.timeout(interaction)


class CaptchaView(discord.ui.View):
    """This view houses buttons and functionality for solving a generated captcha image."""

    def __init__(self, code: str, attempt: int, embed: discord.Embed, verify_role: discord.Role, client: CryptoBot):
        super().__init__(timeout=90)
        self.code: str = code
        self.attempt: int = attempt
        self.locations: List[int] = []
        self.embed: discord.Embed = embed
        self.verify_role = verify_role
        self.client = client
        self.board = [["-1", "-1", "-1", "-1", "-1"],["-1", "-1", "-1", "-1", "-1"],["-1", "-1", "-1", "-1", "-1"],["-1", "-1", "-1", "-1", "-1"]]
        self.rand_letters = [x for x in (string.ascii_uppercase + string.digits) if x not in self.code]

        for i, l in enumerate(self.code):
            x_pos = np.random.randint(0, 4)
            self.board[x_pos][i] = l
            self.locations.append(x_pos)

        # Our board is made up of 4 rows of 5 CaptchaButtons
        # The CaptchaButton maintains the callbacks and helps check the captcha
        for x in range(5):
            for y in range(4):
                state = self.board[y][x]
                label = state if state != '-1' else random.choice(self.rand_letters)
                self.add_item(CaptchaButton(x, y, label))

        self.add_item(RefreshCaptchaButton())

    async def timeout(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=timed_out_embed, view=None)
        self.client.pending_verification.remove(interaction.user.id)


class VerifyButton(discord.ui.Button['Verify']):

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Verify Me!", custom_id="Verify-Button")


    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: VerifyView = self.view

        view.client.pending_verification.add(interaction.user.id)
        await verify_log(view.client, interaction.guild, interaction.user, VerifyAction.START_VERIFICATION)

        await defer_with_thinking(interaction.response, ephemeral=True)
        await asyncio.sleep(2)

        score, default_pfp, wordlist_match, creation_score, flags, messages = await get_bot_chance_score(view.client, interaction.user)

        if score < 25:
            embed = completed_embed.copy()
            embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar)
            embed.set_thumbnail(url=view.client.user.avatar)
            embed.description = "Cryptographer's AI Bot detection has automatically determined you are a valid user!\n__No further action is required at this " \
                                               "time.__\n\nYou will be given the verified role within 30s."
            embed.add_field(name="Bot Detection Likelihood", value=f"Chance that {interaction.user.mention} is a bot: *{score}%*")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return await complete_verification(view.client, interaction.user, view.get_verify_role(interaction.guild_id))

            # await interaction.channel.send("[DEBUG LOG: VerifyButton]\nMember Auto-Verified Here! (Continuing for Testing)")

        with open('data/captchas.json') as file:
            data = json.load(file)

        code, img = random.choice(list(data.items()))

        embed = discord.Embed(title="Complete the Captcha!",
                              description="Press each letter one-by-one using the buttons below.\n\nAttempt __1/3__",
                              color=discord.Color.gold())
        embed.set_image(url=img)

        captcha_view = CaptchaView(code, attempt=1, embed=embed, verify_role=view.get_verify_role(interaction.guild_id), client=view.client)
        await interaction.followup.send(embed=embed, view=captcha_view, wait=True, ephemeral=True)
        if await captcha_view.wait():
            await verify_log(view.client, interaction.guild, interaction.user, VerifyAction.TIMEOUT)
            return await captcha_view.timeout(interaction)

        # await interaction.channel.send("[DEBUG LOG: VerifyButton]\nCaptcha View Has Completed (No Timeout)!")


class VerifyView(discord.ui.View):

    def __init__(self, client: CryptoBot):
        super().__init__(timeout=None)
        self.client = client
        self.add_item(VerifyButton())

    def get_verify_role(self, guild_id: int):
        return self.client.variables[guild_id]['verified_role']


async def get_bot_chance_score(client: discord.Client, member: discord.Member) -> Tuple[float, bool, bool, float, float, float]:
    """
    Generate score for new member of bot likeliness from 0-100
    0: Likely a regular user
    Items which increase score:
    +20.27 | Default profile picture
    +63.81 | Name matching wordlist
    +2.63 | Every day under 4 weeks of account creation date
    +11.11 | If member has no public flags
    +34.29 | If member has sent < 3 messages in the server

    :param client: discord.Bot instance
    :param member: discord.User of user to check
    :return (float, bool, bool, float, float, float): score, default_pfp, wordlist_match, creation score, flags, messages
    """
    default_pfp = member.avatar == member.default_avatar
    wordlist_match = check_wordlist(client, member)
    creation_score = max(0, 28 - (discord.utils.utcnow() - member.created_at).days) * 2.63
    all_flags: list[str] = [k for k, v in iter(member.public_flags) if v]
    flags = 11.11 if member.public_flags.value == 0 else 0
    messages = 34.92 if await sql.get_total_msg_count(client.pool, member.id) < 20 else 0

    if messages == 0 or member.premium_since or (flags == 0 and any([flag for flag in all_flags if not "hype" in flag])):
        print(all_flags)
        score = 0.0
    else:
        score = 20.27 if default_pfp else 0
        score += 63.81 if wordlist_match else 0
        score += creation_score
        score += flags
        score += messages
        score = 0.0 if score < 0 else 100.0 if score >= 100 else score

    return score, default_pfp, wordlist_match, creation_score, flags, messages


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


async def complete_verification(client: CryptoBot, member: discord.Member, verify_role: discord.Role):
    await verify_log(client, member.guild, member, VerifyAction.COMPLETED)
    await asyncio.sleep(30)
    await member.add_roles(verify_role)
    client.pending_verification.remove(member.id)


async def defer_with_thinking(response: discord.InteractionResponse, ephemeral: bool = False):
    data: Optional[Dict[str, Any]] = None
    _parent: discord.Interaction = getattr(response, "_parent")

    if ephemeral:
        data = {'flags': 64}
    adapter = async_context.get()

    await adapter.create_interaction_response(
        _parent.id, _parent.token, session=getattr(_parent, "_session"), type=discord.InteractionResponseType.deferred_channel_message.value, data=data
    )

    setattr(response, "_responded", True)
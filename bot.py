import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
from groq import Groq
from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_CHESS_CHANNEL_ID,
    GROQ_API_KEY,
    CANDIDATES_BROADCAST_ID,
    CANDIDATES_BROADCAST_SLUG,
)
from monitor import TournamentMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("maggie-man")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
monitor: TournamentMonitor = None


@bot.event
async def on_ready():
    global monitor
    logger.info(f"Maggie Man is online as {bot.user}")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    channel = bot.get_channel(DISCORD_CHESS_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="♟️ Maggie Man has entered the chat",
            description=(
                "Ah, the peasants await. 👑\n\n"
                "I'm **Maggie Man**, rated 2800+ and basically unbeatable. "
                "I'll be watching the **FIDE Candidates 2026** and providing *elite* commentary "
                "on every blunder, mistake, and the rare brilliancy these \"grandmasters\" manage to produce.\n\n"
                "Use `/follow` to get tournament alerts. Or don't. I'll be here either way, being better than everyone."
            ),
            color=0xFFD700
        )
        embed.set_footer(text="Maggie Man • 2800+ GM • Better than your favourite player")
        await channel.send(embed=embed)

    monitor = TournamentMonitor(bot, DISCORD_CHESS_CHANNEL_ID, GROQ_API_KEY)
    monitor.start()
    logger.info("Tournament monitor started")


@bot.tree.command(name="follow", description="Follow the FIDE Candidates 2026 tournament")
async def follow(interaction: discord.Interaction):
    monitor.add_follower(interaction.user.id)
    embed = discord.Embed(
        title="✅ Followed: FIDE Candidates 2026",
        description=(
            f"Fine, {interaction.user.mention}, I'll let you know when these so-called GMs are about to play. "
            "Don't expect miracles — most of them can barely hold a draw against me in bullet.\n\n"
            "You'll get:\n"
            "• ⏰ 1-hour reminder before rounds\n"
            "• 🎯 Round start with all pairings\n"
            "• 💥 Blunder/Mistake/Brilliancy alerts with my analysis"
        ),
        color=0x00FF00
    )
    embed.set_footer(text="Maggie Man Tournament Tracker")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unfollow", description="Unfollow the FIDE Candidates 2026 tournament")
async def unfollow(interaction: discord.Interaction):
    monitor.remove_follower(interaction.user.id)
    embed = discord.Embed(
        title="❌ Unfollowed: FIDE Candidates 2026",
        description=(
            f"Leaving already, {interaction.user.mention}? Can't blame you — "
            "watching these games is like watching amateurs play. "
            "Come back when you're ready for *real* chess commentary."
        ),
        color=0xFF4444
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="status", description="Check tournament monitor status")
async def status(interaction: discord.Interaction):
    if monitor is None:
        await interaction.response.send_message("Monitor not started yet.", ephemeral=True)
        return

    info = monitor.get_status()
    embed = discord.Embed(title="📊 Maggie Man - Status", color=0x5865F2)
    embed.add_field(name="Monitoring", value="✅ Active" if info["running"] else "❌ Stopped", inline=True)
    embed.add_field(name="Followers", value=str(info["followers"]), inline=True)
    embed.add_field(name="Active Games", value=str(info["active_games"]), inline=True)
    embed.add_field(name="Rounds Tracked", value=str(info["rounds_tracked"]), inline=True)
    embed.add_field(name="Moves Analysed", value=str(info["moves_analysed"]), inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="maggie", description="Ask Maggie Man anything about chess")
@app_commands.describe(question="Your chess question for the great Maggie Man")
async def maggie(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    groq_client = Groq(api_key=GROQ_API_KEY)
    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Maggie Man, a parody of Magnus Carlsen. You are a 2800+ rated GM "
                        "who thinks everyone else is a noob. You are funny, witty, and roast other players. "
                        "You glorify your own achievements constantly. You refer to yourself in third person sometimes. "
                        "Keep responses under 200 words. Be entertaining."
                    )
                },
                {"role": "user", "content": question}
            ],
            temperature=1,
            max_completion_tokens=512,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
            stop=None
        )
        answer = completion.choices[0].message.content
        embed = discord.Embed(
            title="🎙️ Maggie Man Speaks",
            description=answer,
            color=0xFFD700
        )
        embed.set_footer(text=f"Asked by {interaction.user.display_name} • Maggie Man 2800+ GM")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Groq error in /maggie: {e}")
        await interaction.followup.send("Even Maggie Man has off days. Try again.", ephemeral=True)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
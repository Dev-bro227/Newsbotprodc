import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import pytz
import json
import requests
from keep_alive import keep_alive

TOKEN = os.getenv("TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online as {bot.user}")
    daily_news.start()

# /setup command with optional role and time
@tree.command(name="setup", description="Set the channel, time and optional ping role for daily news")
@app_commands.describe(time="Time in HH:MM (24hr) format", ping_role="Role to ping (optional)")
async def setup(interaction: discord.Interaction, time: str, ping_role: discord.Role = None):
    try:
        # Validate time
        hour, minute = map(int, time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await interaction.response.send_message("❌ Invalid time format. Use HH:MM (24hr).", ephemeral=True)
            return

        # Save config
        config = {
            "channel_id": interaction.channel.id,
            "time": time
        }
        if ping_role:
            config["ping_role_id"] = ping_role.id

        with open("channel.json", "w") as f:
            json.dump(config, f)

        await interaction.response.send_message("✅ Setup complete! Daily news will be posted here.")
        await fetch_and_send_news(interaction.channel, count=7)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error during setup: {e}")

@tree.command(name="news", description="Post 4 latest news")
async def news(interaction: discord.Interaction):
    await interaction.response.defer()
    await fetch_and_send_news(interaction.channel, count=4)
    await interaction.followup.send("✅ News posted!")

async def fetch_and_send_news(channel, count=3):
    try:
        url = f"https://gnews.io/api/v4/top-headlines?lang=en&country=in&max=10&apikey={NEWS_API_KEY}"
        response = requests.get(url)
        data = response.json()

        if "articles" not in data:
            await channel.send("❌ Could not fetch news.")
            return

        if not os.path.exists("news.json"):
            with open("news.json", "w") as f:
                json.dump([], f)

        with open("news.json", "r") as f:
            old_titles = json.load(f)

        new_titles = []
        sent = 0

        for article in data["articles"]:
            title = article["title"]
            url = article["url"]

            if title not in old_titles:
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=f"📰 Source: {article['source']['name']}",
                    color=discord.Color.blue()
                )
                if article.get("image"):
                    embed.set_image(url=article["image"])
                embed.set_footer(text="Powered by GNews.io")

                await channel.send(embed=embed)
                new_titles.append(title)
                sent += 1

            if sent >= count:
                break

        if sent == 0:
            await channel.send("ℹ️ No new articles today.")

        with open("news.json", "w") as f:
            json.dump(new_titles, f)

    except Exception as e:
        await channel.send(f"❌ Error fetching news: {e}")

@tasks.loop(minutes=1)
async def daily_news():
    try:
        if not os.path.exists("channel.json"):
            return

        now = datetime.now(pytz.timezone("Asia/Kolkata"))
        with open("channel.json", "r") as f:
            config = json.load(f)

        hour, minute = map(int, config["time"].split(":"))
        if now.hour == hour and now.minute == minute:
            channel = bot.get_channel(config["channel_id"])
            if channel:
                if "ping_role_id" in config:
                    await channel.send(f"<@&{config['ping_role_id']}> 🔔 Here's your daily news:")
                await fetch_and_send_news(channel, count=7)
    except Exception as e:
        print(f"❌ Error in daily_news loop: {e}")

keep_alive()
bot.run(TOKEN)

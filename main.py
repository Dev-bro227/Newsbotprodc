import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import requests
import json
from datetime import datetime
import pytz
import feedparser
from keep_alive import keep_alive

# Config
CONFIG_FILE = "config.json"
default_config = {
    "channel_id": None,
    "prefix": "!",
    "post_hour": 9,
    "post_minute": 0,
    "timezone": "Asia/Kolkata"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return default_config.copy()

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

config = load_config()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=lambda b, m: config["prefix"], intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    daily_news.start()
    try:
        await tree.sync()
        print("✅ Slash commands synced.")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")

@tree.command(name="prefix", description="Change the bot's command prefix")
@app_commands.describe(new_prefix="New prefix like ! or ?")
async def prefix(interaction: discord.Interaction, new_prefix: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    config["prefix"] = new_prefix
    save_config(config)
    await interaction.response.send_message(f"✅ Prefix changed to `{new_prefix}`")

@tree.command(name="setup", description="Set news post time and this channel for updates")
@app_commands.describe(time="24h format like 09:00")
async def setup(interaction: discord.Interaction, time: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        return
    try:
        hour, minute = map(int, time.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError()
    except:
        await interaction.response.send_message("❌ Use format HH:MM (like 09:30)", ephemeral=True)
        return

    config["channel_id"] = interaction.channel.id
    config["post_hour"] = hour
    config["post_minute"] = minute
    save_config(config)

    await interaction.response.send_message(f"✅ Setup complete. News will post daily at {time}")
    await fetch_and_send_news(interaction.channel, count=7)

@tree.command(name="news", description="Get 4 fresh news articles now")
async def slash_news(interaction: discord.Interaction):
    await interaction.response.defer()
    await fetch_and_send_news(interaction.channel, count=4)

@bot.command()
async def news(ctx):
    await fetch_and_send_news(ctx.channel, count=4)

@tasks.loop(minutes=1)
async def daily_news():
    now = datetime.now(pytz.timezone(config["timezone"]))
    if now.hour == config["post_hour"] and now.minute == config["post_minute"]:
        channel_id = config.get("channel_id")
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                await fetch_and_send_news(channel, count=7)

async def fetch_and_send_news(channel, count=3):
    if not os.path.exists("news.json"):
        with open("news.json", "w") as f:
            json.dump([], f)

    with open("news.json", "r") as f:
        old_titles = json.load(f)

    new_titles = old_titles.copy()
    sent = 0

    sources = [fetch_from_gnews, fetch_from_newsdata, fetch_from_dainik_bhaskar]

    for source in sources:
        articles = source()
        for article in articles:
            if article["title"] not in old_titles:
                embed = discord.Embed(
                    title=article["title"],
                    url=article["url"],
                    description=article.get("desc", ""),
                    color=discord.Color.blue()
                )
                if article.get("image"):
                    embed.set_image(url=article["image"])
                embed.set_footer(text=article.get("source", "News Bot"))
                await channel.send(embed=embed)
                new_titles.append(article["title"])
                sent += 1
            if sent >= count:
                break
        if sent >= count:
            break

    if sent == 0:
        await channel.send("ℹ️ No new articles today.")

    with open("news.json", "w") as f:
        json.dump(new_titles[-50:], f)

def fetch_from_gnews():
    key = os.getenv("NEWS_API_KEY")
    if not key:
        return []
    try:
        url = f"https://gnews.io/api/v4/top-headlines?lang=en&country=in&max=10&apikey={key}"
        data = requests.get(url).json()
        return [{
            "title": a["title"],
            "url": a["url"],
            "desc": f"📰 Source: {a['source']['name']}",
            "image": a.get("image"),
            "source": "GNews.io"
        } for a in data.get("articles", [])]
    except:
        return []

def fetch_from_newsdata():
    key = os.getenv("NEWSDATA_API_KEY")
    if not key:
        return []
    try:
        url = f"https://newsdata.io/api/1/news?apikey={key}&country=in&language=hi,en&category=top"
        data = requests.get(url).json()
        return [{
            "title": a["title"],
            "url": a["link"],
            "desc": f"📰 Source: {a.get('source_id', 'NewsData.io')}",
            "image": a.get("image_url"),
            "source": "NewsData.io"
        } for a in data.get("results", [])]
    except:
        return []

def fetch_from_dainik_bhaskar():
    try:
        feed = feedparser.parse("https://www.bhaskar.com/rss-national.xml")
        return [{
            "title": entry.title,
            "url": entry.link,
            "desc": "📰 Source: Dainik Bhaskar",
            "source": "Dainik Bhaskar"
        } for entry in feed.entries]
    except:
        return []

if __name__ == "__main__":
    keep_alive()
    bot.run(os.getenv("TOKEN"))

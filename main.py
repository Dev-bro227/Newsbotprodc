import os
import discord
import json
import requests
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import pytz
from flask import Flask
from threading import Thread

# ========== Keep Alive Flask Server ==========
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ========== Bot Setup ==========
TOKEN = os.getenv("TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

config_file = "channel.json"
news_log = "news.json"

def load_config():
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            return json.load(f)
    return {"channel_id": None, "post_hour": 9}

def save_config(data):
    with open(config_file, "w") as f:
        json.dump(data, f)

config = load_config()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")
    daily_news.start()

@bot.command()
async def prefix(ctx, *, symbol=None):
    if symbol:
        bot.command_prefix = symbol
        await ctx.send(f"✅ Prefix changed to `{symbol}`")
    else:
        await ctx.send(f"ℹ️ Current prefix is `{bot.command_prefix}`")

@bot.command()
async def news(ctx):
    await fetch_gnews(ctx.channel, lang="en", count=4)

@bot.tree.command(name="setup", description="Setup daily news posting")
@app_commands.describe(time="Hour of day (0–23)")
async def setup(interaction: discord.Interaction, time: int):
    if not (0 <= time <= 23):
        await interaction.response.send_message("❌ Time must be between 0–23.", ephemeral=True)
        return
    config["channel_id"] = interaction.channel.id
    config["post_hour"] = time
    save_config(config)
    await interaction.response.send_message(f"✅ Daily news will post here at {time:02d}:00")
    await fetch_gnews(interaction.channel, "en", count=7)

@bot.tree.command(name="weather", description="Check current weather")
@app_commands.describe(city="City name")
async def weather(interaction: discord.Interaction, city: str):
    await interaction.response.defer(thinking=True)
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url).json()

        if res.get("cod") != 200:
            await interaction.followup.send(f"❌ City not found: {city}")
            return

        embed = discord.Embed(
            title=f"🌤 Weather in {res['name']}, {res['sys']['country']}",
            description=f"⛅ {res['weather'][0]['description'].title()}",
            color=discord.Color.teal()
        )
        embed.add_field(name="🌡 Temperature", value=f"{res['main']['temp']}°C", inline=True)
        embed.add_field(name="💧 Humidity", value=f"{res['main']['humidity']}%", inline=True)
        embed.add_field(name="🌬 Wind", value=f"{res['wind']['speed']} km/h", inline=True)
        embed.set_footer(text="Powered by OpenWeatherMap")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

@weather.autocomplete("city")
async def weather_autocomplete(interaction: discord.Interaction, current: str):
    cities = [
        "Delhi", "Mumbai", "Chennai", "Kolkata", "Bangalore", "Hyderabad",
        "Pune", "Lucknow", "Indore", "Jaipur", "Patna", "Varanasi"
    ]
    current = current or ""
    matches = [c for c in cities if current.lower() in c.lower()]
    await interaction.response.send_autocomplete([
        app_commands.Choice(name=city, value=city) for city in matches[:10]
    ])

@bot.tree.command(name="news", description="Get news from source")
@app_commands.describe(language="Language", source="Source")
@app_commands.choices(
    language=[
        app_commands.Choice(name="English", value="en"),
        app_commands.Choice(name="Hindi", value="hi")
    ],
    source=[
        app_commands.Choice(name="GNews", value="gnews"),
        app_commands.Choice(name="NewsData", value="newsdata"),
        app_commands.Choice(name="Dainik Bhaskar", value="bhaskar")
    ]
)
async def news_command(interaction: discord.Interaction, language: app_commands.Choice[str], source: app_commands.Choice[str]):
    await interaction.response.defer(thinking=True)
    lang = language.value
    src = source.value

    try:
        if src == "gnews":
            await fetch_gnews(interaction.channel, lang)
        elif src == "newsdata":
            await fetch_newsdata(interaction.channel, lang)
        elif src == "bhaskar":
            await fetch_dainik_bhaskar(interaction.channel)
        else:
            await interaction.followup.send("❌ Unknown source selected.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

# ========== News Functions ==========
async def fetch_gnews(channel, lang="en", count=5):
    url = f"https://gnews.io/api/v4/top-headlines?lang={lang}&country=in&max=10&apikey={NEWS_API_KEY}"
    res = requests.get(url).json()
    if "articles" not in res:
        await channel.send("❌ Could not fetch GNews articles.")
        return

    old_titles = []
    if os.path.exists(news_log):
        with open(news_log, "r") as f:
            old_titles = json.load(f)

    new_titles = []
    sent = 0

    for art in res["articles"]:
        if art["title"] in old_titles:
            continue
        embed = discord.Embed(
            title=art["title"],
            url=art["url"],
            description=f"📰 Source: {art['source']['name']}",
            color=discord.Color.blue()
        )
        if art.get("image"):
            embed.set_image(url=art["image"])
        await channel.send(embed=embed)
        new_titles.append(art["title"])
        sent += 1
        if sent >= count:
            break

    if sent == 0:
        await channel.send("ℹ️ No new articles.")
    with open(news_log, "w") as f:
        json.dump(new_titles, f)

async def fetch_newsdata(channel, lang="en", count=5):
    url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&country=in&language={lang}&category=top"
    res = requests.get(url).json()
    if "results" not in res:
        await channel.send("❌ Could not fetch NewsData articles.")
        return

    for art in res["results"][:count]:
        embed = discord.Embed(
            title=art["title"],
            url=art["link"],
            description=f"📰 {art.get('source_id', 'NewsData')}",
            color=discord.Color.orange()
        )
        await channel.send(embed=embed)

async def fetch_dainik_bhaskar(channel):
    url = "https://www.bhaskar.com/"
    try:
        html = requests.get(url).text
        headlines = []
        for line in html.splitlines():
            if '<h3 class="newstrend-title">' in line:
                start = line.find('>') + 1
                end = line.rfind('<')
                title = line[start:end].strip()
                if title:
                    headlines.append(title)
            if len(headlines) >= 5:
                break

        for headline in headlines:
            embed = discord.Embed(
                title=headline,
                url=url,
                description="📰 Dainik Bhaskar",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)

    except Exception as e:
        await channel.send(f"❌ Dainik Bhaskar fetch failed: {e}")

@tasks.loop(minutes=1)
async def daily_news():
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    if now.hour == config.get("post_hour", 9) and now.minute == 0:
        cid = config.get("channel_id")
        if cid:
            channel = bot.get_channel(cid)
            if channel:
                await fetch_gnews(channel, "en", count=7)

# ========== Start Bot ==========
keep_alive()
bot.run(TOKEN)

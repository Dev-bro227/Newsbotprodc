import os
import json
import pytz
import requests
import discord
from datetime import datetime
from discord.ext import commands, tasks
from discord import app_commands
from keep_alive import keep_alive

# ENV
TOKEN = os.getenv("TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online as {bot.user}")
    daily_news.start()

# /setup with optional role + time
@tree.command(name="setup", description="Set channel, time, and optional ping role for daily news.")
@app_commands.describe(time="Time in HH:MM format (24hr)", ping_role="Role to ping with news (optional)")
async def setup(interaction: discord.Interaction, time: str, ping_role: discord.Role = None):
    await interaction.response.defer()

    try:
        hour, minute = map(int, time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await interaction.followup.send("❌ Invalid time format. Use HH:MM (24hr).")
            return

        config = {
            "channel_id": interaction.channel.id,
            "time": time
        }
        if ping_role:
            config["ping_role_id"] = ping_role.id

        with open("channel.json", "w") as f:
            json.dump(config, f)

        await interaction.followup.send("✅ Setup complete! Daily news will be posted here.")
        
        # Immediately post 7 news after setup
        await fetch_and_send_news(interaction.channel, count=7)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

# /news command
@tree.command(name="news", description="Get latest 4 news")
async def news(interaction: discord.Interaction):
    await interaction.response.defer()
    await fetch_and_send_news(interaction.channel, count=4)
    await interaction.followup.send("✅ News posted!")

# /weather command
@tree.command(name="weather", description="Get current weather info for a city")
@app_commands.describe(city="City name")
async def weather(interaction: discord.Interaction, city: str):
    await interaction.response.defer()
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url).json()

        if res.get("cod") != 200:
            await interaction.followup.send("❌ City not found.")
            return

        name = res["name"]
        country = res["sys"]["country"]
        desc = res["weather"][0]["description"].title()
        temp = res["main"]["temp"]
        humidity = res["main"]["humidity"]
        wind = res["wind"]["speed"]

        embed = discord.Embed(
            title=f"🌤️ Weather in {name}, {country}",
            description=f"{desc}",
            color=discord.Color.teal()
        )
        embed.add_field(name="🌡️ Temperature", value=f"{temp}°C")
        embed.add_field(name="💧 Humidity", value=f"{humidity}%")
        embed.add_field(name="🌬️ Wind", value=f"{wind} m/s")
        embed.set_footer(text="Powered by OpenWeatherMap")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

# Send daily news at set time
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
        print(f"❌ Error in daily_news: {e}")

# News fetcher
async def fetch_and_send_news(channel, count=3):
    try:
        url = f"https://gnews.io/api/v4/top-headlines?lang=en&country=in&max=10&apikey={NEWS_API_KEY}"
        res = requests.get(url).json()

        if "articles" not in res:
            await channel.send("❌ Failed to fetch news.")
            return

        if not os.path.exists("news.json"):
            with open("news.json", "w") as f:
                json.dump([], f)

        with open("news.json", "r") as f:
            old_titles = json.load(f)

        new_titles = []
        sent = 0

        for article in res["articles"]:
            title = article["title"]
            url = article["url"]

            if title not in old_titles:
                embed = discord.Embed(
                    title=title,
                    url=url,
                    description=f"📰 {article['source']['name']}",
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
        await channel.send(f"❌ Error while fetching news: {e}")

# Start it
keep_alive()
bot.run(TOKEN)

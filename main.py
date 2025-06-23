import os import json import pytz import requests import discord from datetime import datetime from discord.ext import commands, tasks from discord import app_commands from keep_alive import keep_alive

ENV

TOKEN = os.getenv("TOKEN") GNEWS_API_KEY = os.getenv("NEWS_API_KEY") NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY") WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

intents = discord.Intents.default() intents.message_content = True bot = commands.Bot(command_prefix="!", intents=intents) tree = bot.tree

@bot.event async def on_ready(): await tree.sync() print(f"✅ Bot is online as {bot.user}") daily_news.start()

@tree.command(name="setup", description="Set daily news time, language, source, and ping role") @app_commands.describe( time="Time in HH:MM (24hr)", language="Language: en or hi", source="Source: gnews or newsdata", ping_role="Role to ping (optional)" ) async def setup(interaction: discord.Interaction, time: str, language: str = "en", source: str = "gnews", ping_role: discord.Role = None): await interaction.response.defer() try: hour, minute = map(int, time.split(":")) if not (0 <= hour <= 23 and 0 <= minute <= 59): await interaction.followup.send("❌ Invalid time format.") return

config = {
        "channel_id": interaction.channel.id,
        "time": time,
        "language": language,
        "source": source
    }
    if ping_role:
        config["ping_role_id"] = ping_role.id

    with open("channel.json", "w") as f:
        json.dump(config, f)

    await interaction.followup.send("✅ Setup complete! Sending initial news...")
    await fetch_and_send_news(interaction.channel, count=7, language=language, source=source)

except Exception as e:
    await interaction.followup.send(f"❌ Error: {e}")

@tree.command(name="news", description="Get 4 news articles with optional language and source") @app_commands.describe(language="Language: en or hi", source="Source: gnews or newsdata") async def news(interaction: discord.Interaction, language: str = "en", source: str = "gnews"): await interaction.response.defer() try: await fetch_and_send_news(interaction.channel, count=4, language=language, source=source) await interaction.followup.send("✅ News posted!") except Exception as e: await interaction.followup.send(f"❌ Error: {e}")

@tree.command(name="weather", description="Get weather of a city") @app_commands.describe(city="City name") async def weather(interaction: discord.Interaction, city: str): await interaction.response.defer() try: url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric" res = requests.get(url).json() if res.get("cod") != 200: await interaction.followup.send("❌ City not found.") return

embed = discord.Embed(title=f"🌤️ Weather in {res['name']}, {res['sys']['country']}", description=res['weather'][0]['description'].title(), color=discord.Color.teal())
    embed.add_field(name="🌡️ Temp", value=f"{res['main']['temp']}°C")
    embed.add_field(name="💧 Humidity", value=f"{res['main']['humidity']}%")
    embed.add_field(name="🌬️ Wind", value=f"{res['wind']['speed']} m/s")
    embed.set_footer(text="Powered by OpenWeatherMap")

    await interaction.followup.send(embed=embed)

except Exception as e:
    await interaction.followup.send(f"❌ Error: {e}")

@tasks.loop(minutes=1) async def daily_news(): try: if not os.path.exists("channel.json"): return with open("channel.json", "r") as f: config = json.load(f)

now = datetime.now(pytz.timezone("Asia/Kolkata"))
    hour, minute = map(int, config["time"].split(":"))

    if now.hour == hour and now.minute == minute:
        channel = bot.get_channel(config["channel_id"])
        if channel:
            if "ping_role_id" in config:
                try:
                    await channel.send(f"<@&{config['ping_role_id']}> 🔔 Here's your daily news:")
                except:
                    pass
            await fetch_and_send_news(channel, count=7, language=config["language"], source=config["source"])
except Exception as e:
    print(f"❌ Daily news error: {e}")

async def fetch_and_send_news(channel, count=3, language="en", source="gnews"): try: articles = []

if source == "gnews":
        url = f"https://gnews.io/api/v4/top-headlines?lang={language}&country=in&max=10&apikey={GNEWS_API_KEY}"
        res = requests.get(url).json()
        articles = res.get("articles", [])

    elif source == "newsdata":
        url = f"https://newsdata.io/api/1/news?apikey={NEWSDATA_API_KEY}&language={language}&country=in"
        res = requests.get(url).json()
        articles = res.get("results", [])

    if not articles:
        await channel.send("❌ No news found from the selected source.")
        return

    if not os.path.exists("news.json"):
        with open("news.json", "w") as f:
            json.dump([], f)

    with open("news.json", "r") as f:
        old_titles = json.load(f)

    new_titles = []
    sent = 0

    for article in articles:
        title = article.get("title")
        url = article.get("link") or article.get("url")
        source_name = article.get("source_id") or article.get("source", {}).get("name", "Unknown")
        image_url = article.get("image_url") or article.get("image")

        if title and title not in old_titles:
            embed = discord.Embed(title=title, url=url, description=f"📰 {source_name}", color=discord.Color.blue())
            if image_url:
                embed.set_image(url=image_url)
            embed.set_footer(text=f"Powered by {source.upper()}")
            await channel.send(embed=embed)
            new_titles.append(title)
            sent += 1

        if sent >= count:
            break

    if sent == 0:
        await channel.send("ℹ️ No new unique articles today.")

    with open("news.json", "w") as f:
        json.dump(new_titles, f)

except Exception as e:
    await channel.send(f"❌ Error fetching news: {e}")

keep_alive() bot.run(TOKEN)


import discord
import asyncio
import requests
import sqlite3
import time
import logging
import os
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Setup logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "bot.log"),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
print(TOKEN)
GUILD_ID = int(os.getenv("GUID"))  
print(GUILD_ID)
VERIFY_CHANNEL_ID = int(os.getenv("VCID")) 
ANNOUNCEMENT_CHANNEL_ID = int(os.getenv("ACID")) 

ROLE_MAP = {
    "newbie": "Newbie",
    "pupil": "Pupil",
    "specialist": "Specialist",
    "expert": "Expert",
    "candidate master": "Candidate Master",
    "master": "Master",
    "international master": "International Master",
    "grandmaster": "Grandmaster",
    "international grandmaster": "International Grandmaster",
    "legendary grandmaster": "Legendary Grandmaster"
}

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

db = sqlite3.connect("codeforces_users.db")
cursor = db.cursor()

# Create table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS verified_users (
    user_id INTEGER PRIMARY KEY,
    handle TEXT UNIQUE,
    rank TEXT,
    verified BOOLEAN DEFAULT 0
)''')
db.commit()

logger.info("Database initialized and table verified_users ensured.")

def get_handle_from_userid(user_id):
    cursor.execute("SELECT handle FROM verified_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_codeforces_stats(handle):
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    response = requests.get(url).json()
    if "result" in response:
        user_info = response["result"][0]
        return {
            "max_rating": user_info.get("maxRating", "Unknown"),
            "rank": user_info.get("rank", "Unknown"),
            "streak": get_solved_streak(handle),
            "questions_solved": get_solved_problems(handle),
            "questions_solved_week": get_solved_problems_week(handle)
        }
    return None

def get_solved_problems(handle):
    url = f"https://codeforces.com/api/user.status?handle={handle}"
    response = requests.get(url).json()
    if "result" in response:
        solved_problems = {sub["problem"]["name"] for sub in response["result"] if sub["verdict"] == "OK"}
        return len(solved_problems)
    return "Not Available"

def check_compilation_error(handle):
    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=5"
    response = requests.get(url).json()
    if "result" in response:
        for submission in response["result"]:
            if submission["verdict"] == "COMPILATION_ERROR":
                logger.info(f"Compilation error found for {handle}.")
                return True
    return False

def get_codeforces_rank(handle):
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    response = requests.get(url).json()
    if "result" in response:
        return response["result"][0].get("rank", "Newbie")
    return "Newbie"


def verify_user(user_id, handle):
    api_url = f"https://codeforces.com/api/user.info?handles={handle}"
    response = requests.get(api_url).json()
    
    if response["status"] == "OK":
        rank = response["result"][0].get("rank", "Newbie")
        cursor.execute("INSERT OR REPLACE INTO verified_users (user_id, handle, rank) VALUES (?, ?, ?)", (user_id, handle, rank))
        db.commit()
        logger.info(f"User {user_id} verified with handle {handle} and rank {rank}.")
        return True
    logger.warning(f"Verification failed for user {user_id} with handle {handle}.")
    return False

def get_solved_problems_week(handle):
    one_week_ago = int(time.time()) - 7 * 24 * 60 * 60
    url = f"https://codeforces.com/api/user.status?handle={handle}"
    response = requests.get(url).json()
    if "result" in response:
        solved_problems = {sub["problem"]["name"] for sub in response["result"] if sub["verdict"] == "OK" and sub["creationTimeSeconds"] >= one_week_ago}
        return len(solved_problems)
    return "Not Available"

def get_solved_streak(handle):
    url = f"https://codeforces.com/api/user.status?handle={handle}"
    response = requests.get(url).json()
    if "result" in response:
        solved_days = set()
        for sub in response["result"]:
            if sub["verdict"] == "OK":
                solved_days.add(time.strftime("%Y-%m-%d", time.gmtime(sub["creationTimeSeconds"])))
        
        sorted_days = sorted(solved_days)
        max_streak = 0
        current_streak = 0
        prev_day = None
        
        for day in sorted_days:
            if prev_day is None or (time.mktime(time.strptime(day, "%Y-%m-%d")) - time.mktime(time.strptime(prev_day, "%Y-%m-%d"))) == 86400:
                current_streak += 1
            else:
                current_streak = 1
            max_streak = max(max_streak, current_streak)
            prev_day = day
        
        return max_streak
    return "Not Available"



@bot.command()
async def verifycf(ctx, handle: str = None):
    """Verify your Codeforces account."""
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        return
    
    if not handle:
        await ctx.send(f"{ctx.author.mention}, please provide your Codeforces handle. Usage: `!verifycf your_handle`")
        logger.warning(f"User {ctx.author.id} attempted verification without a handle.")
        return
    
    user = ctx.author
    await user.send(f"Submit a compilation error on Codeforces and wait 5 minutes. Handle: {handle}")
    await asyncio.sleep(300)
    
    if check_compilation_error(handle):
        if verify_user(user.id, handle):
            rank = get_codeforces_rank(handle)
            role_name = ROLE_MAP.get(rank.lower(), "Newbie")
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role:
                await user.add_roles(role)
                await ctx.send(f"{user.mention} has been verified and assigned the {role_name} role!")
                logger.info(f"User {user.id} verified and assigned role {role_name}.")

@bot.command()
async def cfinfo(ctx, member: discord.Member = None):
    """Displays the info of the mentioned user or the user who invoked the command."""
    user_id = member.id if member else ctx.author.id
    handle = get_handle_from_userid(user_id)
    if handle:
        stats = get_codeforces_stats(handle)
        if stats:
            await ctx.send(
                f"**Codeforces Info for {handle}:**\n"
                f"- Max Rating: {stats['max_rating']}\n"
                f"- Rank: {stats['rank']}\n"
                f"- Streak: {stats['streak']}\n"
                f"- Questions Solved: {stats['questions_solved']}\n"
                f"- Questions Solved Last Week: {stats['questions_solved_week']}"
            )
        else:
            await ctx.send("Failed to fetch Codeforces stats.")
    else:
        await ctx.send("User not found in the database.")

# @bot.command()
# async def help(ctx):
#     await ctx.send(
#         "**Available Commands:**\n"
#         "- `!verifycf <handle>`: Verify your Codeforces account.\n"
#         "- `!cfinfo [@user]` : Get Codeforces stats of yourself or another user.\n"
#         "- `!help` : Show this help message."
#     )

@tasks.loop(hours=6)
async def update_roles():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        logger.warning("Guild not found.")
        return
    
    cursor.execute("SELECT user_id, handle, rank FROM verified_users WHERE verified = 1")
    users = cursor.fetchall()
    
    for user_id, handle, old_rank in users:
        stats = get_codeforces_stats(handle)
        if stats and stats["rank"] != old_rank:
            member = guild.get_member(user_id)
            if member:
                new_role_name = ROLE_MAP.get(stats["rank"].lower())
                if new_role_name:
                    new_role = discord.utils.get(guild.roles, name=new_role_name)
                    if new_role:
                        await member.add_roles(new_role)
                        logger.info(f"Updated role for {member.name} to {new_role_name}")
                        cursor.execute("UPDATE verified_users SET rank = ? WHERE user_id = ?", (stats["rank"], user_id))
                        db.commit()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    cursor.execute("DELETE FROM verified_users WHERE verified = 0")
    db.commit()
    update_roles.start()

bot.run(TOKEN)

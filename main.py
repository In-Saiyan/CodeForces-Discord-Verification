import discord
from discord.ui import View, Button
import json
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

db = sqlite3.connect("/app/data/codeforces_users.db") # for docker container
# db = sqlite3.connect("./data/codeforces_users.db") # for local testing
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

class StatsView(View):
    def __init__(self, ctx, handle, solved_by_difficulty, solved_by_topic, member):
        super().__init__()
        self.ctx = ctx
        self.handle = handle
        self.solved_by_difficulty = solved_by_difficulty
        self.solved_by_topic = solved_by_topic
        self.member = member
        self.current_page = 1
        self.message = None

    def create_embed(self):
        embed = discord.Embed(
            title=f"Codeforces Stats for {self.handle}",
            url=f"https://codeforces.com/profile/{self.handle}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.member.avatar.url if self.member else self.ctx.author.avatar.url)

        if self.current_page == 1:
            embed.description = "**Solved Problems by Difficulty:**"
            for difficulty, count in sorted(self.solved_by_difficulty.items(), key=lambda x: (x[0] == "Unrated", x[0])):
                embed.add_field(name=f"Difficulty {difficulty}", value=str(count), inline=True)
        else:
            embed.description = "**Solved Problems by Topic:**"
            for topic, count in sorted(self.solved_by_topic.items(), key=lambda x: -x[1]):
                embed.add_field(name=topic.title(), value=str(count), inline=True)

        embed.set_footer(text=f"Page {self.current_page}/2")
        return embed

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page == 2:
            self.current_page = 1
            await self.update_message(interaction)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page == 1:
            self.current_page = 2
            await self.update_message(interaction)

    async def update_message(self, interaction):
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


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
async def cfstats(ctx, member: discord.Member = None):
    """Displays the number of solved questions categorized by difficulty and topics."""
    user_id = member.id if member else ctx.author.id
    handle = get_handle_from_userid(user_id)

    if not handle:
        await ctx.send("User not found in the database.")
        return

    url = f"https://codeforces.com/api/user.status?handle={handle}"
    response = requests.get(url).json()

    if "result" not in response:
        await ctx.send("Failed to fetch Codeforces stats.")
        return

    solved_by_difficulty = {}
    solved_by_topic = {}
    solved_problems = set()  # Store solved problem IDs to avoid duplicates

    for submission in response["result"]:
        if submission["verdict"] == "OK":
            problem = submission["problem"]
            problem_id = (problem["contestId"], problem["index"])  # Unique identifier

            if problem_id not in solved_problems:
                solved_problems.add(problem_id)

                difficulty = problem.get("rating", "Unrated")
                tags = problem.get("tags", [])

                solved_by_difficulty[difficulty] = solved_by_difficulty.get(difficulty, 0) + 1
                for tag in tags:
                    solved_by_topic[tag] = solved_by_topic.get(tag, 0) + 1

    view = StatsView(ctx, handle, solved_by_difficulty, solved_by_topic, member)
    view.message = await ctx.send(embed=view.create_embed(), view=view)

# @bot.command()
# async def cfstats(ctx, member: discord.Member = None):
#     """Displays the number of solved questions categorized by difficulty and topics."""
#     user_id = member.id if member else ctx.author.id
#     handle = get_handle_from_userid(user_id)

#     if not handle:
#         await ctx.send("User not found in the database.")
#         return

#     url = f"https://codeforces.com/api/user.status?handle={handle}"
#     response = requests.get(url).json()

#     if "result" not in response:
#         await ctx.send("Failed to fetch Codeforces stats.")
#         return

#     solved_by_difficulty = {}
#     solved_by_topic = {}
#     solved_problems = set()  # Store solved problem IDs to avoid duplicates

#     for submission in response["result"]:
#         if submission["verdict"] == "OK":
#             problem = submission["problem"]
#             problem_id = (problem["contestId"], problem["index"])  # Unique identifier

#             if problem_id not in solved_problems:
#                 solved_problems.add(problem_id)

#                 difficulty = problem.get("rating", "Unrated")
#                 tags = problem.get("tags", [])

#                 solved_by_difficulty[difficulty] = solved_by_difficulty.get(difficulty, 0) + 1
#                 for tag in tags:
#                     solved_by_topic[tag] = solved_by_topic.get(tag, 0) + 1

#     def create_embed(page):
#         embed = discord.Embed(title=f"Codeforces Stats for {handle}", url=f"https://codeforces.com/profile/{handle}", color=discord.Color.blue())
#         embed.set_thumbnail(url=member.avatar.url if member else ctx.author.avatar.url)

#         if page == 1:
#             embed.description = "**Solved Problems by Difficulty:**"
#             for difficulty, count in sorted(solved_by_difficulty.items(), key=lambda x: (x[0] == "Unrated", x[0])):
#                 embed.add_field(name=f"Difficulty {difficulty}", value=str(count), inline=True)
#         else:
#             embed.description = "**Solved Problems by Topic:**"
#             for topic, count in sorted(solved_by_topic.items(), key=lambda x: -x[1]):
#                 embed.add_field(name=topic.title(), value=str(count), inline=True)

#         embed.set_footer(text=f"Page {page}/2 | Use ⬅️ and ➡️ to navigate.")
#         return embed

#     message = await ctx.send(embed=create_embed(1))
#     await message.add_reaction("⬅️")
#     await message.add_reaction("➡️")

#     def check(reaction, user):
#         return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

#     current_page = 1

#     while True:
#         try:
#             reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)

#             if str(reaction.emoji) == "➡️" and current_page == 1:
#                 current_page = 2
#             elif str(reaction.emoji) == "⬅️" and current_page == 2:
#                 current_page = 1

#             await message.edit(embed=create_embed(current_page))
#             await message.remove_reaction(reaction, user)

#         except asyncio.TimeoutError:
#             break
        
@bot.command()
async def cfinfo(ctx, member: discord.Member = None):
    """Displays the info of the mentioned user or the user who invoked the command in an embed."""
    user_id = member.id if member else ctx.author.id
    handle = get_handle_from_userid(user_id)
    
    if handle:
        stats = get_codeforces_stats(handle)
        if stats:
            embed = discord.Embed(
                title=f"Codeforces Profile: {handle}",
                url=f"https://codeforces.com/profile/{handle}",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.avatar.url if member else ctx.author.avatar.url)
            embed.add_field(name="Max Rating", value=stats["max_rating"], inline=True)
            embed.add_field(name="Rank", value=stats["rank"].title(), inline=True)
            embed.add_field(name="Streak", value=stats["streak"], inline=True)
            embed.add_field(name="Questions Solved", value=stats["questions_solved"], inline=True)
            embed.add_field(name="Solved Last Week", value=stats["questions_solved_week"], inline=True)

            await ctx.send(embed=embed)
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

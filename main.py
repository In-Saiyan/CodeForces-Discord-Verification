import discord
from discord.ui import View, Button
import re
import json
import asyncio
import requests
import sqlite3
import time
import logging
import os
from discord.ext import commands, tasks
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

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

# Database setup
cconn = sqlite3.connect('/app/data/codechef_users.db')
ccursor = cconn.cursor()
ccursor.execute('''
    CREATE TABLE IF NOT EXISTS verified_users (
        discord_id INTEGER PRIMARY KEY,
        codechef_username TEXT,
        rating INTEGER,
        last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
cconn.commit()

logger.info("Database initialized and table verified_users ensured.")

# Function to scrape CodeChef for verification using Selenium
async def check_codechef_submission(username):
    url = f"https://www.codechef.com/users/{username}"
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get(url)
        
        # Wait for rating to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "rating-number"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Extract rating
        rating_tag = soup.find("div", class_="rating-number")
        rating = int(rating_tag.text.strip()) if rating_tag else 0
        
        # Wait for the submissions table to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "dataTable"))
        )
        
        # Parse the updated page
        soup = BeautifulSoup(driver.page_source, "html.parser")
        submissions_table = soup.select_one("table.dataTable tbody")
        
        if not submissions_table:
            logging.info(f"User {username} has no submissions.")
            return False, rating
        
        rows = submissions_table.find_all("tr")
        logging.info(f"Total submissions found: {len(rows)}")
        
        # Debugging: Log first 3 rows
        for i, row in enumerate(rows[:3]):
            columns = row.find_all("td")
            row_data = [col.text.strip() for col in columns]
            # logging.info(f"Row {i+1}: {row_data}")
        
        # Check the most recent submission for compilation error
        last_submission = rows[0]  # First row is the latest submission
        result_td = last_submission.find_all("td")[2]  # 3rd column
        result_span = result_td.find("span", {"title": True})
        verdict = result_span["title"].strip().lower() if result_span else ""
        
        logging.info(f"Last submission status: {verdict}")
        
        if "compilation error" in verdict:
            logging.info(f"User {username} has a compilation error in their last submission.")
            return True, rating
        
        logging.info(f"User {username} does NOT have a compilation error in their last submission.")
    
    except Exception as e:
        logging.error(f"Error in check_codechef_submission: {e}")
    
    finally:
        driver.quit()
    
    return False, rating



# Command to verify CodeChef users
@bot.command()
async def verifycc(ctx, codechef_username: str):
    """Verify a CodeChef user by checking for a compilation error every 30 seconds for 5 minutes."""
    user = ctx.author
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        return
    await user.send(f"Hello {user.mention}, please submit a compilation error on CodeChef. I'll check every 30 seconds for the next 5 minutes. Username: {codechef_username}")

    logging.info(f"Verification started for {user} with CodeChef username {codechef_username}")

    for _ in range(10):  # Check 10 times (every 30 seconds for 5 minutes)
        await asyncio.sleep(30)
        verification_success, rating = await check_codechef_submission(codechef_username)

        if verification_success and rating:
            ccursor.execute("INSERT OR REPLACE INTO verified_users (discord_id, codechef_username, rating) VALUES (?, ?, ?)", 
                            (user.id, codechef_username, rating))
            cconn.commit()
            await user.send(f"✅ Verification successful! Your CodeChef rating: {rating}")
            await update_user_role_cc(user, rating)
            return
    
    await user.send("❌ Verification failed. I couldn't detect a compilation error within 5 minutes. Please try again.")
    logging.warning(f"User {user.id} verification failed for CodeChef username {codechef_username}.")


# Function to update roles based on rating
async def update_user_role_cc(member, rating):
    guild = member.guild
    role_mapping = {
        0   : "★",
        1400: "★★",
        1600: "★★★",
        1800: "★★★★",
        2000: "★★★★★",
        2200: "★★★★★★",
        2500: "★★★★★★★"
    }
    assigned_role = None
    for threshold, role_name in sorted(role_mapping.items(), reverse=True):
        if rating >= threshold:
            assigned_role = discord.utils.get(guild.roles, name=role_name)
            break
    
    if assigned_role:
        await member.add_roles(assigned_role)
        logging.info(f"Assigned role {assigned_role} to {member}")

# Periodic task to update roles
@tasks.loop(hours=6)
async def update_roles_task():
    await bot.wait_until_ready()
    guild = bot.guilds[0]  # Assuming bot is in one server
    ccursor.execute("SELECT discord_id, rating FROM verified_users")
    for discord_id, rating in ccursor.fetchall():
        member = guild.get_member(discord_id)
        if member:
            await update_user_role_cc(member, rating)
# crazy marker

class CCStatsView(View):
    def __init__(self, ctx, handle, stats, member):
        super().__init__()
        self.ctx = ctx
        self.handle = handle
        self.stats = stats
        self.member = member
        self.message = None

    def get_codechef_pfp(self, handle):
        """Fetch CodeChef profile picture using the API."""
        url = f"https://codechef-api.vercel.app/handle/{handle}"
        response = requests.get(url).json()
        
        return response.get("profile", self.ctx.author.avatar.url)  # Returns profile picture URL if found, else None


    def create_embed(self):
        embed = discord.Embed(
            title=f"CodeChef Stats for {self.handle}",
            url=f"https://www.codechef.com/users/{self.handle}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=self.get_codechef_pfp(self.handle) or self.ctx.author.avatar.url)

        embed.add_field(name="Rating", value=self.stats["max_rating"], inline=True)
        embed.add_field(name="Stars", value=self.stats["stars"], inline=True)
        embed.add_field(name="Global Rank", value=self.stats["global_rank"], inline=True)
        embed.add_field(name="Country Rank", value=self.stats["country_rank"], inline=True)
        embed.add_field(name="Total Problems Solved", value=self.stats["questions_solved"], inline=True)

        return embed


def get_codechef_handle_from_userid(user_id):
    ccursor.execute("SELECT codechef_username FROM verified_users WHERE discord_id = ?", (user_id,))
    result = ccursor.fetchone()
    return result[0] if result else None

def get_codechef_stats(handle):
    url = f"https://www.codechef.com/users/{handle}"
    response = requests.get(url).text
    soup = BeautifulSoup(response, "html.parser")

    # Extracting stats
    rating = soup.find("div", class_="rating-number").text.strip() if soup.find("div", class_="rating-number") else "Unknown"
    stars = soup.find("span", class_="rating").text.strip() if soup.find("span", class_="rating") else "Unknown"

    # Extracting global & country rank from the correct section
    global_rank = "Unknown"
    country_rank = "Unknown"

    rank_section = soup.find("div", class_="rating-ranks")
    if rank_section:
        ranks = rank_section.find_all("strong")
        if len(ranks) >= 2:
            global_rank = ranks[0].text.strip()
            country_rank = ranks[1].text.strip()

    # Extracting total problems solved
    total_solved = "Unknown"
    total_solved_tag = soup.find("h3", string=re.compile(r"Total Problems Solved: (\d+)"))
    if total_solved_tag:
        match = re.search(r"Total Problems Solved: (\d+)", total_solved_tag.text)
        if match:
            total_solved = match.group(1)

    return {
        "max_rating": rating,
        "stars": stars,
        "global_rank": global_rank,
        "country_rank": country_rank,
        "questions_solved": total_solved
    }



@bot.command()
async def ccstats(ctx, member: discord.Member = None):
    """Displays the user's CodeChef stats."""
    user_id = member.id if member else ctx.author.id
    handle = get_codechef_handle_from_userid(user_id)

    if not handle:
        await ctx.send("User not found in the database.")
        return

    stats = get_codechef_stats(handle)
    if not stats:
        await ctx.send("Failed to fetch CodeChef stats.")
        return

    view = CCStatsView(ctx, handle, stats, member)
    view.message = await ctx.send(embed=view.create_embed())


# crazy




class StatsView(View):
    def __init__(self, ctx, handle, stats, solved_by_difficulty, solved_by_topic, member):
        super().__init__()
        self.ctx = ctx
        self.handle = handle
        self.stats = stats
        self.solved_by_difficulty = solved_by_difficulty
        self.solved_by_topic = solved_by_topic
        self.member = member
        self.current_page = 1
        self.message = None

    def get_codeforces_pfp(self, handle):
        url = f"https://codeforces.com/api/user.info?handles={handle}"
        response = requests.get(url).json()
        
        if "result" in response:
            return response["result"][0].get("titlePhoto", None)  # This returns the profile picture URL
        return None
    
    def create_embed(self):
        embed = discord.Embed(
            title=f"Codeforces Stats for {self.handle}",
            url=f"https://codeforces.com/profile/{self.handle}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.get_codeforces_pfp(self.handle) or self.ctx.author.avatar.url) # Use user's avatar if no profile picture found

        if self.current_page == 1:
            embed.add_field(name="Max Rating", value=self.stats["max_rating"], inline=True)
            embed.add_field(name="Rank", value=self.stats["rank"].title(), inline=True)
            embed.add_field(name="Streak", value=self.stats["streak"], inline=True)
            embed.add_field(name="Questions Solved", value=self.stats["questions_solved"], inline=True)
            embed.add_field(name="Solved Last Week", value=self.stats["questions_solved_week"], inline=True)
        elif self.current_page == 2:
            embed.description = "**Solved Problems by Difficulty:**"
            for difficulty, count in sorted(self.solved_by_difficulty.items(), key=lambda x: (x[0] == "Unrated", x[0])):
                embed.add_field(name=f"Difficulty {difficulty}", value=str(count), inline=True)
        else:
            embed.description = "**Solved Problems by Topic:**"
            for topic, count in sorted(self.solved_by_topic.items(), key=lambda x: -x[1]):
                embed.add_field(name=topic.title(), value=str(count), inline=True)

        embed.set_footer(text=f"Page {self.current_page}/3")
        return embed

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < 3:
            self.current_page += 1
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


@bot.event
async def on_message(message):
    """Deletes messages in the verification channel after 5 seconds."""
    await bot.process_commands(message)
    if message.channel.id == VERIFY_CHANNEL_ID and not message.author.bot:
        await asyncio.sleep(5)
        try:
            await message.delete()
        except discord.NotFound:
            pass  # Message was already deleted

      # Ensures commands still work

@bot.command()
async def verifycf(ctx, handle: str = None):
    """Verify your Codeforces account."""
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        return

    if not handle:
        await ctx.author.send(f"Please provide your Codeforces handle. Usage: `!verifycf your_handle`")
        logger.warning(f"User {ctx.author.id} attempted verification without a handle.")
        await ctx.message.delete()
        return

    user = ctx.author
    await ctx.message.delete()
    await user.send(f"Submit a compilation error on Codeforces. I'll check every 30 seconds for the next 5 minutes. Handle: {handle}")

    for _ in range(10):  # Check 10 times (every 30 seconds for 5 minutes)
        await asyncio.sleep(30)
        if check_compilation_error(handle):
            if verify_user(user.id, handle):
                rank = get_codeforces_rank(handle)
                role_name = ROLE_MAP.get(rank.lower(), "Newbie")
                role = discord.utils.get(ctx.guild.roles, name=role_name)

                if role:
                    await user.add_roles(role)
                    await user.send(f"✅ You have been verified and assigned the `{role_name}` role!")
                    logger.info(f"User {user.id} verified and assigned role {role_name}.")
                else:
                    await user.send(f"✅ You have been verified, but I couldn't find the `{role_name}` role.")
                    logger.warning(f"Role {role_name} not found for user {user.id}.")

                # Add user to the database
                try:
                    cursor.execute('''INSERT INTO verified_users (user_id, handle, rank, verified) 
                                      VALUES (?, ?, ?, ?) 
                                      ON CONFLICT(user_id) DO UPDATE SET handle = excluded.handle, rank = excluded.rank, verified = excluded.verified''',
                                   (user.id, handle, rank, 1))
                    db.commit()
                    logger.info(f"User {user.id} ({handle}) added to the database.")
                except sqlite3.Error as e:
                    logger.error(f"Database error while adding user {user.id}: {e}")
                    await user.send("⚠️ There was an issue saving your verification data. Please contact an admin.")

                return
    
    await user.send("❌ Verification failed. I couldn't detect a compilation error within 5 minutes. Please try again.")
    logger.warning(f"User {user.id} verification failed due to no detected compilation error.")

@bot.command()
async def unverifycf(ctx):
    """Unverifies the user and removes their Codeforces handle from the database."""
    user_id = ctx.author.id
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        return
    cursor.execute("SELECT handle FROM verified_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result:
        await ctx.send("❌ You are not verified.")
        return

    handle = result[0]
    
    # Remove user from database
    cursor.execute("DELETE FROM verified_users WHERE user_id = ?", (user_id,))
    db.commit()

    await ctx.send(f"✅ You have been unverified and your Codeforces handle `{handle}` has been removed from the database.")
    logger.info(f"User {user_id} ({handle}) unverified.")

@bot.command()
async def unverifycc(ctx):
    """Unverifies the user and removes their CodeChef handle from the database."""
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        return
    user_id = ctx.author.id

    ccursor.execute("SELECT codechef_username FROM verified_users WHERE discord_id = ?", (user_id,))
    result = ccursor.fetchone()

    if not result:
        await ctx.send("❌ You are not verified on CodeChef.")
        return

    handle = result[0]

    # Remove user from database
    ccursor.execute("DELETE FROM verified_users WHERE discord_id = ?", (user_id,))
    cconn.commit()

    await ctx.send(f"✅ You have been unverified and your CodeChef handle `{handle}` has been removed from the database.")
    logger.info(f"User {user_id} ({handle}) unverified from CodeChef.")



@bot.command()
async def cfstats(ctx, member: discord.Member = None):
    """Displays the user's Codeforces stats, problems solved by difficulty, and problems solved by topic."""
    user_id = member.id if member else ctx.author.id
    handle = get_handle_from_userid(user_id)

    if not handle:
        await ctx.send("User not found in the database.")
        return

    stats = get_codeforces_stats(handle)
    if not stats:
        await ctx.send("Failed to fetch Codeforces stats.")
        return

    url = f"https://codeforces.com/api/user.status?handle={handle}"
    response = requests.get(url).json()

    if "result" not in response:
        await ctx.send("Failed to fetch Codeforces stats.")
        return

    solved_by_difficulty = {}
    solved_by_topic = {}
    solved_problems = set()

    for submission in response["result"]:
        if submission["verdict"] == "OK":
            problem = submission["problem"]
            problem_id = (problem["contestId"], problem["index"])

            if problem_id not in solved_problems:
                solved_problems.add(problem_id)
                difficulty = problem.get("rating", "Unrated")
                tags = problem.get("tags", [])

                solved_by_difficulty[difficulty] = solved_by_difficulty.get(difficulty, 0) + 1
                for tag in tags:
                    solved_by_topic[tag] = solved_by_topic.get(tag, 0) + 1

    view = StatsView(ctx, handle, stats, solved_by_difficulty, solved_by_topic, member)
    view.message = await ctx.send(embed=view.create_embed(), view=view)


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

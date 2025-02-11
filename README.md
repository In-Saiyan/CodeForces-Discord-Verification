# Codeforces Verification Discord Bot

## Overview
This bot verifies Codeforces users on Discord by checking their submissions and assigning them roles based on their rank.

## Features
- Users can verify their Codeforces account using `!verifycf <handle>`.
- Displays CodeForces question statistics of the user via  `!cfstats [@user]`.
- Users can verify their CodeChef account using `!verifycc <handle>`.
- Displays CodeChef profile statistics of the user via  `!ccstats [@user]`.
- Automatically updates roles every 6 hours.
- Removes unverified users from the database.

## Installation
### Requirements
- Python > 3.8+ and < 3.13 (some packages are missing in Python 3.13 which are required by discord.py)
- SQLite3
- Required Python packages (listed in `requirements.txt`)
- A Discord bot token

### Setup
1. Clone the repository:
   ```sh
   git clone https://github.com/In-Saiyan/CodeForces-Discord-Verification.git
   cd CodeForces-Discord-Verification
   ```
2. Create a virtual environment and activate it:
   ```sh
   python3.11 -m venv .venv
   source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
   ```
3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
4. Create a `.env` file and add:
   ```ini
   DISCORD_BOT_TOKEN=your_discord_token_here #important
   GUID=your_discord_server_id #important
   VCID=verification_channel_id
   ACID=announcement_channel_id
   ```
5. Run the bot:
   ```sh
   python main.py
   ```

## Docker Deployment
### Build and Run with Docker
1. Build the Docker image:
   ```sh
   docker build -t cf-discord-bot .
   ```
2. Run the container:
   ```sh
   docker run -v $(pwd)/data:/app/data -d cf-discord-bot 
   ```

## Caution
- Ensure your `.env` file contains a valid Discord bot token.
- The bot requires proper permissions to assign roles in your Discord server.

## Notes
- The bot deletes unverified users from the database on startup.
- Roles update automatically every 6 hours.

## Info
- Created by: **Aryan Singh**
- Also check out the same project but with Discord.js: [ThunderBlaze/Cp_Discord_Bot](https://github.com/Thunder-Blaze/Cp_Discord_Bot)


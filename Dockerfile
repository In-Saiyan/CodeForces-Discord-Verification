FROM python:3.10

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

ENV DISCORD_BOT_TOKEN="your_token_here"
ENV DISCORD_GUILD_ID="your_guild_id_here"
ENV VERIFICATION_CHANNEL_ID="verification_channel_id_here"
ENV ANNOUCEMENT_CHANNEL_ID="announcement_channel_id_here"

CMD ["python", "main.py"]

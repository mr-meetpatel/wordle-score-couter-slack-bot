import slack
import os
import re
from constants import WORDLE_REGEX
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from slackeventsapi import SlackEventAdapter
from datetime import datetime
attemps = {}
stats_count = {}
# App Instances
app = Flask(__name__)

# Event Adapter
slack_events_adapter = SlackEventAdapter(
    os.environ["SIGNING_SECRET"], "/slack/events", app
)

# Read data from .env file

env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

client = slack.WebClient(token=os.environ["SLACK_OAUTH_TOKEN"])
BOT_ID = client.api_call("auth.test")["user_id"]

@slack_events_adapter.on("message")
def message(payload):
    response = payload.get("event", {})
    channel_id = response.get("channel")
    user_id = response.get("user")
    text = response.get("text")
    if BOT_ID != user_id and re.fullmatch(WORDLE_REGEX, text):
        client.chat_postMessage(channel=channel_id, text=text)
        client.chat_postMessage(
            channel=user_id,
            text=f"Hello <@{user_id}> Thank you solving today's wordle :tada:",
        )
        today = datetime.now().date().strftime("%Y-%m-%d")
        if today in attemps:
            attemps[today].append(user_id)
        else:
            attemps[today]=[user_id]
        stats_count[user_id] = stats_count[user_id]+1 if user_id in stats_count else 1
        print(attemps,stats_count)
if __name__ == "__main__":
    app.run(debug=True)

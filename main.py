import slack
import os
import re
from constants import WORDLE_REGEX
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from slackeventsapi import SlackEventAdapter
from datetime import datetime

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


def send_message(channel_id, text):
    client.chat_postMessage(channel=channel_id, text=text)


@slack_events_adapter.on("message")
def message(payload):
    response = payload.get("event", {})
    channel_id = response.get("channel")
    user_id = response.get("user")
    text = response.get("text")
    if BOT_ID != user_id and re.fullmatch(WORDLE_REGEX, text):
        today = datetime.now().date().strftime("%Y-%m-%d")

        if user_id in stats_count:
            if str(stats_count[user_id][1]) != today:
                stats_count[user_id][0] += 1
                send_message(user_id, text)
        else:
            stats_count[user_id] = [1, today]
            send_message(user_id, text)
        print(stats_count)


if __name__ == "__main__":
    app.run(debug=True)

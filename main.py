import slack
import os
import re
import schedule
import time
from constants import WORDLE_REGEX, GREETING_MESSAGE
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from slackeventsapi import SlackEventAdapter
from datetime import datetime,date,timedelta
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

def calculate_wordle_stats():
    global stats_count
    stats = """
    <!channel>
    Stats for Attempted WORDLE for the week of {} to {}
    There {} this week.. :crown:
    Check your stats below :tada:
    
    {}
    """
    no_of_royalties = sum(stats_count[user][0] == 5 for user in stats_count)
    msg = f"is {no_of_royalties} royalty"
    if no_of_royalties > 1:
         msg = f"are {no_of_royalties} royalties"

    royalties = ""
    non_royalties = ""
    for user in stats_count:
        if stats_count[user][0]==5:
            if not royalties:
                royalties += f"*Leaderboard* :trophy:\n"

            royalties+=f"- <@{user}>\n"
        else:
            if not non_royalties:
                non_royalties += "*\tRemaining Players List* :clap:\n"
            non_royalties+=f"- {client.users_info(user=user)['user']['real_name']} ({stats_count[user][0]}/5)\n"
    stats_count = {}
    send_message("#test",stats.format((date.today() - timedelta(4)).strftime("%d %b"),date.today().strftime("%d %b"),msg,royalties+non_royalties))
@slack_events_adapter.on("message")
def message(payload):
    response = payload.get("event", {})
    channel_id = response.get("channel")
    user_id = response.get("user")
    text = response.get("text")
    if BOT_ID != user_id and re.fullmatch(WORDLE_REGEX, text):
        reaction = "tada"
        today = datetime.now().date().strftime("%Y-%m-%d")
        if user_id in stats_count:
            if str(stats_count[user_id][1]) != today and stats_count[user_id][0] <= 4:
                stats_count[user_id][0] += 1
                send_message(user_id, f"{GREETING_MESSAGE.format(user_id)}")
        else:
            stats_count[user_id] = [1, today]
            send_message(user_id, f"{GREETING_MESSAGE.format(user_id)}")

        # Adding Reaction base on score
        if text[11] == "X":
            reaction="thumbsup"
        elif text[11] in ["1","2"]:
            reaction = "fire"
        print(user_id)
        client.reactions_add(name=reaction,channel=channel_id,timestamp=response["ts"])
@app.route("/")
def index():
    schedule.every().day.at("06:00").do(send_message, "#test", "Good Morning!")
    schedule.every().wednesday.at("07:00").do(send_message,"#test","Happy Wednesday ...")
    schedule.every().day.at("15:29").do(send_message,"U04RLBVPJ48","Bot is Working...")
    schedule.every().friday.at("18:30").do(calculate_wordle_stats)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    app.run()
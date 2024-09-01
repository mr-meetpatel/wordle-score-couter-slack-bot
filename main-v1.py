import slack
import re
import sys
from constants import WORDLE_REGEX, SLACK_OAUTH_TOKEN, SIGING_SECRET, CHANNEL_NAME, NO_OF_DAYS
from flask import Flask,Response,request
import time
import pytz
from slackeventsapi import SlackEventAdapter
from datetime import datetime,date,timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func



# App Instances
app = Flask(__name__)

# DB Setup
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql://MrProfessor:Mysql2410@MrProfessor.mysql.pythonanywhere-services.com/MrProfessor$wordle-stats"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 500
app.config['SQLALCHEMY_POOL_RECYCLE'] = 60 * 60 * 8

db = SQLAlchemy(app)


class StatsCount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.Text,nullable=False)
    name = db.Column(db.Text,nullable=False)
    count = db.Column(db.Integer,nullable=False)
    date = db.Column(db.Text,nullable=False)

    def __repr__(self):
        return f'<StatsCount {self.id}-{self.user}-{self.count}>'

client = slack.WebClient(token=SLACK_OAUTH_TOKEN)

# Event Adapter
slack_events_adapter = SlackEventAdapter(
    SIGING_SECRET, "/slack/events", app
)
BOT_ID = client.api_call("auth.test")["user_id"]

class WordleMessage:
    START_TEXT = {}
    LEADERBOARD = {
			"type": "section",
			"text": {
				"type": "mrkdwn",
			}
		}
    DIVIDER = {'type': 'divider'}
    OTHER = {
			"type": "section",
			"text": {
				"type": "mrkdwn",
			}
		}

    def __init__(self, channel,count=NO_OF_DAYS):
        self.channel = channel
        self.from_date = (date.today() - timedelta(4)).strftime("%d %b")
        self.to_date = date.today().strftime("%d %b")
        self.count = count
        #self.no_of_royalties = len(StatsCount.query.filter_by(count=self.count).all())
        self.no_of_royalties = len(StatsCount.query.filter(StatsCount.count >= count).all())
        self.msg = ""
        self.send_leaderboard=False
        self.send_other=False


    def calculate_wordle_stats(self,send=True):
        self.LEADERBOARD['text']['text']=f"*Leaderboard* :trophy:"
        self.OTHER['text']['text']=f"*Remaining Players List :clap:*"
        stats_count = StatsCount.query.all()
        if self.no_of_royalties > 1:
            self.msg = f"are {str(self.no_of_royalties)} royalties"
        else:
            self.msg = f"is {str(self.no_of_royalties)} royalty"
        self.START_TEXT = {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"<!channel>\n\nStats for Attempted WORDLE for the week of {self.from_date} to {self.to_date}\nThere {self.msg} this week.. :crown:\nCheck your stats below :tada:"
			}
		}

        # royalties = ""
        # non_royalties = ""
        for user in stats_count:
            if user.count == 0:
                continue
            if user.count>=self.count:
                # if not royalties:
                #     royalties += "*Leaderboard* :trophy:\n"
                self.send_leaderboard=True
                self.LEADERBOARD['text']['text']+=f"\n- <@{user.user}>"
            else:
                # if not non_royalties:
                #     non_royalties += "*\tRemaining Players List* :clap:\n"
                self.send_other=True
                self.OTHER['text']['text']+=f"\n- {client.users_info(user=user.user)['user']['real_name']} ({user.count}/{self.count})"
        # user.count = 0
        # db.session.commit()
        if send:
            self.send_message()
        return str(self.get_message())

    def send_message(self):
        client.chat_postMessage(**self.get_message())

    def get_message(self):
        blocks = [self.START_TEXT]
        if self.send_leaderboard:
            blocks.append(self.LEADERBOARD)
        if self.send_other:
            blocks.append(self.OTHER)
        return {
            'channel': self.channel,
            'blocks': blocks
        }

def send_message(wordle):
    client.chat_postMessage(**wordle.get_message())


@slack_events_adapter.on("message")
def message(payload):
    response = payload.get("event", {})
    channel_id = response.get("channel")
    user_id = response.get("user")
    text = response.get("text")
    f = open("log.txt", "a")
    match = re.search(WORDLE_REGEX,text)
    if not match:
        f.write(f"\nuser_id {user_id} name : {client.users_info(user=user_id)['user']['real_name']}  FAILED:invalid wordle post  {text}")
    if BOT_ID != user_id and match:
        f.write(f"\nuser_id {user_id} name : {client.users_info(user=user_id)['user']['real_name']}")
        reaction = "tada"
        today = datetime.now().date().strftime("%Y-%m-%d")
        stats = StatsCount.query.filter_by(user=user_id).first()

        if not stats is None:
            if stats.date != today and stats.count <= 4:
                stats.count += 1
                stats.count += 1
                stats.date = today
                db.session.add(stats)
                db.session.commit()
        else:
            obj = StatsCount(user=user_id,count=1,date=today,name=client.users_info(user=user_id)['user']['real_name'])
            db.session.add(obj)
            db.session.commit()

        # Adding Reaction base on score
        if match.group("score") == "X":
            reaction="thumbsup"
        elif match.group("score") in ["1","2"]:
            reaction = "fire"
        client.reactions_add(name=reaction,channel=channel_id,timestamp=response["ts"])
    f.close()

@app.route("/")
def index():
    return "Slack Bot is working"

@app.route("/msg")
def msg():
    wordle=WordleMessage("#channel-english-101")
    # wordle=WordleMessage("#test")
    return wordle.calculate_wordle_stats(send=False)

@app.route("/score")
def scoreboard():
    users = StatsCount.query.all()
    str = """
    <table border="1" align="center">
    <tr>
    <th>SrNo</th>
    <th>Name</th>
    <th>Count</th>
    </tr>
    """
    for id,user in enumerate(users,start=1):
        if user.count == 0:
            continue
        str+="<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(id,client.users_info(user=user.user)['user']['real_name'],user.count)
    str+="</table>"
    return str

@app.route("/thankyou")
def thankyou():
    return "<h1>Thank you for installing my slack bot to your workspace</h1>"


@app.route("/send-stats",methods=['POST','GET'])
def send():
    error = ""
    data = request.form
    wordle=WordleMessage(CHANNEL_NAME)
    if data.get("text") == "password":

        wordle.calculate_wordle_stats()
    else:
        error = "Invalid Password"
    return (Response(error), 200) if error else (Response(), 200)

if __name__ == '__main__':
    app.run()
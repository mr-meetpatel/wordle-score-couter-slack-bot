import slack
import re
from flask import Flask, Response, request
from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from slackeventsapi import SlackEventAdapter
from constants import WORDLE_REGEX, SLACK_OAUTH_TOKEN, SIGING_SECRET, NO_OF_DAYS, CHANNEL_NAME

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
    __tablename__ = 'stats_count'

    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    count = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<StatsCount {self.id}-{self.user}-{self.count}>'


class SlackClientWrapper:
    def __init__(self, token):
        self.client = slack.WebClient(token=token)
        self.bot_id = self.client.api_call("auth.test")["user_id"]

    def post_message(self, channel, blocks):
        self.client.chat_postMessage(channel=channel, blocks=blocks)

    def add_reaction(self, reaction, channel, timestamp):
        self.client.reactions_add(name=reaction, channel=channel, timestamp=timestamp)

    def get_user_info(self, user_id):
        return self.client.users_info(user=user_id)['user']['real_name']


client = SlackClientWrapper(token=SLACK_OAUTH_TOKEN)

# Event Adapter
slack_events_adapter = SlackEventAdapter(
    SIGING_SECRET, "/slack/events", app
)


class MessageFactory:
    @staticmethod
    def create_wordle_message(channel, count=NO_OF_DAYS):
        return WordleMessage(channel, count)


class WordleMessage:
    def __init__(self, channel, count=NO_OF_DAYS):
        self.channel = channel
        self.from_date = (date.today() - timedelta(4)).strftime("%d %b")
        self.to_date = date.today().strftime("%d %b")
        self.count = count
        self.no_of_royalties = len(StatsCount.query.filter(StatsCount.count >= count).all())
        self.blocks = []
        self._prepare_blocks()

    def _prepare_blocks(self):
        start_text = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<!channel>\n\nStats for Attempted WORDLE for the week of {self.from_date} to {self.to_date}\n"
                        f"There {'are' if self.no_of_royalties > 1 else 'is'} {self.no_of_royalties} royalty{'ies' if self.no_of_royalties > 1 else ''} "
                        f"this week.. :crown:\nCheck your stats below :tada:"
            }
        }
        self.blocks.append(start_text)

        leaderboard, other = self._generate_leaderboard_and_other()
        if leaderboard:
            self.blocks.append(self._generate_section_block("Leaderboard", ":trophy:", leaderboard))
        if other:
            self.blocks.append(self._generate_section_block("Remaining Players List", ":clap:", other))

    def _generate_leaderboard_and_other(self):
        leaderboard = []
        other = []

        for user in StatsCount.query.all():
            if user.count == 0:
                continue
            if user.count >= self.count:
                leaderboard.append(f"<@{user.user}>")
            else:
                other.append(f"{client.get_user_info(user.user)} ({user.count}/{self.count})")

        return leaderboard, other

    @staticmethod
    def _generate_section_block(title, emoji, users):
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}* {emoji}\n" + "\n".join(f"- {user}" for user in users)
            }
        }

    def get_message_payload(self):
        return {
            'channel': self.channel,
            'blocks': self.blocks
        }

    def send(self):
        client.post_message(self.channel, self.blocks)


class ReactionStrategy:
    def add_reaction(self, client, channel_id, timestamp):
        raise NotImplementedError("This method should be overridden by subclasses")


class FireReaction(ReactionStrategy):
    def add_reaction(self, client, channel_id, timestamp):
        reaction = "fire"
        client.add_reaction(reaction, channel_id, timestamp)


class ThumbsUpReaction(ReactionStrategy):
    def add_reaction(self, client, channel_id, timestamp):
        reaction = "thumbsup"
        client.add_reaction(reaction, channel_id, timestamp)

class TadaReaction(ReactionStrategy):
    def add_reaction(self, client, channel_id, timestamp):
        reaction = "tada"
        client.add_reaction(reaction, channel_id, timestamp)


class StatsRecorder:
    def __init__(self, user_id, text, channel_id, timestamp):
        self.user_id = user_id
        self.text = text
        self.channel_id = channel_id
        self.timestamp = timestamp
        self.reaction_strategy = None

    def process(self):
        if not re.search(WORDLE_REGEX, self.text):
            return

        self._set_reaction_strategy()
        self._record_stats()
        self._add_reaction()

    def _set_reaction_strategy(self):
        match = re.search(WORDLE_REGEX, self.text)
        score = match.group("score")

        if score in ["1", "2"]:
            self.reaction_strategy = FireReaction()
        elif score == "X":
            self.reaction_strategy = ThumbsUpReaction()
        else:
            self.reaction_strategy = TadaReaction()

    def _record_stats(self):
        stats = StatsCount.query.filter_by(user=self.user_id).first()
        today = datetime.now().date().strftime("%Y-%m-%d")

        if stats:
            if stats.date != today and stats.count <= 4:
                stats.count += 1
                stats.date = today
                db.session.add(stats)
                db.session.commit()
        else:
            new_stat = StatsCount(
                user=self.user_id,
                count=1,
                date=today,
                name=client.get_user_info(self.user_id)
            )
            db.session.add(new_stat)
            db.session.commit()

    def _add_reaction(self):
        self.reaction_strategy.add_reaction(client, self.channel_id, self.timestamp)


class SlackEventObserver:
    def update(self, event):
        raise NotImplementedError("This method should be overridden by subclasses")


class MessageEventObserver(SlackEventObserver):
    def update(self, event):
        user_id = event.get("user")
        text = event.get("text")
        channel_id = event.get("channel")
        timestamp = event.get("ts")

        if user_id != client.bot_id:
            recorder = StatsRecorder(user_id, text, channel_id, timestamp)
            recorder.process()


class SlackEventManager:
    def __init__(self):
        self._observers = []

    def attach(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer):
        self._observers.remove(observer)

    def notify(self, event):
        for observer in self._observers:
            observer.update(event)


event_manager = SlackEventManager()
message_event_observer = MessageEventObserver()
event_manager.attach(message_event_observer)


@slack_events_adapter.on("message")
def handle_message(payload):
    event = payload.get("event", {})
    event_manager.notify(event)
    #event_manager.detach(message_event_observer)


@app.route("/")
def index():
    return "Slack Bot is working"


@app.route("/msg")
def msg():
    wordle = MessageFactory.create_wordle_message(CHANNEL_NAME)
    return wordle.get_message_payload()


@app.route("/score")
def scoreboard():
    users = StatsCount.query.all()
    return generate_scoreboard(users)


def generate_scoreboard(users):
    scoreboard_html = """
    <table border="1" align="center">
    <tr>
    <th>SrNo</th>
    <th>Name</th>
    <th>Count</th>
    </tr>
    """
    for id, user in enumerate(users, start=1):
        if user.count > 0:
            scoreboard_html += f"<tr><td>{id}</td><td>{client.get_user_info(user.user)}</td><td>{user.count}</td></tr>"
    scoreboard_html += "</table>"
    return scoreboard_html


@app.route("/thankyou")
def thankyou():
    return "<h1>Thank you for installing my slack bot to your workspace</h1>"

@app.route("/send-stats", methods=['POST', 'GET'])
def send_stats():
    data = request.form
    if data.get("text") == "password":
        # event_manager._observers
        return Response(str(len(event_manager._observers)),200)
    else:
        error = "Invalid Password"
    return (Response(error), 200) if error else (Response(), 200)

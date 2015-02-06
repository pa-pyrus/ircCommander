# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

"""
bot.py

ircCommander IRC client and command handler.
It sets up a server connection, joins configured channels and listens for
commands.

Copyright (c) 2015 Pyrus <pyrus at coffee dash break dot at>
See the file LICENSE for copying permission.
"""

from datetime import datetime, timedelta
from random import randint, choice

import re

from pytz import timezone, utc

from twisted.python import log
from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.task import LoopingCall

import configuration
from ladder import LadderParser
from leader import LeaderParser
from twitch import TwitchParser
from twitter import TwitterParser
from tourney import TourneyParser
from patch import PatchParser
from misc import MiscParser


class TownCrierScheduler(object):
    def __init__(self, event=datetime.utcnow()):
        """Initialize the announcement scheduler for an event."""
        if not isinstance(event, datetime):
            raise TypeError("event is not a datetime.datetime ojbect")

        self._event = event
        self._timer = None

    @property
    def event(self):
        return self._event

    @event.setter
    def event(self, new_event):
        if not isinstance(new_event, datetime):
            raise TypeError("new_event is not a datetime.datetime object")
        self._event = new_event

    @property
    def timer(self):
        return self._timer

    @timer.setter
    def timer(self, new_timer):
        self._timer = new_timer

    def __iter__(self):
        return self

    def next(self):
        """
        Return the seconds until next update is due for datetime specified.
        Delay is calculated in following increments:
            > 1d | 24h
            >12h |  4h
            > 6h |  2h
            > 3h |  1h
            > 1h | 30m
            > 0h | 15m
            else | raise StopIterator
        """

        now = datetime.utcnow()
        if now >= self._event:
            raise StopIteration

        countdown = self._event - now
        if countdown.days:
            next_update = self._event - timedelta(countdown.days)
        elif countdown.seconds > 43200:  # 12h
            # round to multiples of 4 hours
            next_update_seconds = (countdown.seconds // 14400) * 14400
            next_update = self._event - timedelta(0, next_update_seconds)
        elif countdown.seconds > 21600:  # 6h
            # round to multiples of 2 hours
            next_update_seconds = (countdown.seconds // 7200) * 7200
            next_update = self._event - timedelta(0, next_update_seconds)
        elif countdown.seconds > 10800:  # 3h
            # round to full hours
            next_update_seconds = (countdown.seconds // 3600) * 3600
            next_update = self._event - timedelta(0, next_update_seconds)
        elif countdown.seconds > 3600:  # 1h
            # round to full 30m
            next_update_seconds = (countdown.seconds // 1800) * 1800
            next_update = self._event - timedelta(0, next_update_seconds)
        else:
            # round to full 15m
            next_update_seconds = (countdown.seconds // 900) * 900
            next_update = self._event - timedelta(0, next_update_seconds)

        return (next_update - now).total_seconds()


class CommanderBot(irc.IRCClient):
    """
    The Commander IRC bot.

    It authenticates with NickServ, joins channels and listens for commands.
    """

    # timestamp for flood prevention
    lastcmd = datetime.utcnow()
    started = datetime.utcnow()
    twitch = TwitchParser()
    ladder = LadderParser()
    leader = LeaderParser()
    tweets = TwitterParser()
    tourney = TourneyParser()
    patch = PatchParser()
    misc = MiscParser()
    last_patches = None
    towncrier = TownCrierScheduler()

    def sendLine(self, line):
        """Encode all lines as utf-8. Is this a good idea?"""
        if isinstance(line, unicode):
            line = line.encode("utf-8")
        irc.IRCClient.sendLine(self, line)

    def connectionMade(self):
        """
        Upon successful connection establishment, we set up our nickname, real
        name and message rate.
        """
        self.nickname = self.factory.nickname
        self.realname = self.factory.realname
        self.lineRate = self.factory.linerate
        irc.IRCClient.connectionMade(self)

    def signedOn(self):
        """
        Authenticate with NickServ and join the configured channels as soon as
        the welcome message is received.
        """
        irc.IRCClient.signedOn(self)
        log.msg("Connection established successfully.")

        if self.factory.nickserv:
            log.msg("Authenticating with NickServ.")
            self.msg("NickServ", "IDENTIFY {0}".format(self.factory.nickserv))

        log.msg("Joining channels {0}.".format(self.factory.channels))
        for channel in self.factory.channels:
            self.join(channel)

        log.msg("Starting event checker.")
        LoopingCall(self.check_events).start(120, True)

    def privmsg(self, user, channel, msg):
        """Handle messages to either the bot itself or the channel it is in."""
        irc.IRCClient.privmsg(self, user, channel, msg)
        # ignore everything that's not a command
        if not msg.startswith(self.factory.prefix):
            return

        nick = user.split("!")[0]
        # is this a query? if so, send messages to nick instead
        if channel == self.nickname:
            channel = nick

        now = datetime.utcnow()
        if (now - self.lastcmd).seconds < self.factory.cmdlimit:
            self.notice(nick, "Sorry, I only answer requests every "
                              "\x02{0}\x02 seconds.".format(
                                  self.factory.cmdlimit))
            return
        self.lastcmd = now

        # this might be a bad idea but we assume all data to be utf-8
        msg = msg.decode("utf-8")
        log.msg(u"Received {0} from {1} on {2}.".format(
            msg.encode("ascii", "xmlcharrefreplace"), nick, channel))

        # command is always separated by a space
        parts = msg.split(" ", 1)
        cmd = parts[0]
        args = parts[1].strip() if len(parts) == 2 else None

        # check if we can handle that command
        cmd_name = "handle_command_{0}".format(cmd[1:])
        handle_command = getattr(self, cmd_name, None)
        if handle_command and callable(handle_command):
            handle_command(channel, nick, args)

    def handle_command_help(self, channel, nick, args):
        """
        Handle !help command.
        Print a list of supported commands.
        """
        commands = ("!ladder [activity]", "!stats <user>", "!rank <user>",
                    "!forecast <user1> <user2>", "!ratio <user1> <user2>",
                    "!suggest <user>",
                    "!top [uber|platinum|gold|silver|bronze]",
                    "!twitch", "!uptime",
                    "!twitter [3|5]",
                    "!tourney [next|last]",
                    "!patch", "!news",
                    "!exodus",
                    "!now", "!roll [[<n>]d<n>]")

        self.msg(channel, u"Available commands: "
                          u"{0}".format(", ".join(commands)))
        self.notice(nick, u"Want more? Ask \x02Pyrus\x02 to add it!")

    def handle_command_exodus(self, channel, nick, args):
        """
        Handle !exodus command.
        Print information on their website.
        """
        self.msg(channel, u"\x02eXodus eSports\x02. "
                          u"Visit http://exodusesports.com/")

    def handle_command_uptime(self, channel, nick, args):
        """
        Handle !uptime command.
        Print the time since bot was started.
        """
        self.msg(channel, u"I've been alive for {0}".format(
            datetime.utcnow() - self.started))

    def handle_command_ladder(self, channel, nick, args):
        """
        Handler !ladder command.
        It always shows the top N players. The optional argument can be used to
        filter by activity. It defaults to active players in the last 28 days.
        Trigger an update on self.ladder an print topN.
        """
        activity = int(args) if args and args.isdigit() else 28
        self.ladder.top(activity).addCallback(self.tell_ladder, channel)

    def handle_command_stats(self, channel, nick, args):
        """
        Handle !stats command.
        It expects (part of) a username in args.
        Trigger an update on self.adder and print stats for player.
        """
        if not args:
            self.notice(nick, "You need to include a player name.")
            return

        userstats = args
        self.ladder.stats(userstats).addCallback(self.tell_stats,
                                                 channel, userstats)

    def handle_command_rank(self, channel, nick, args):
        """
        Handle !rank command.
        It expects (part of) a username in args.
        Trigger an update on self.adder and print player's rank.
        """
        if not args:
            self.notice(nick, "You need to include a player name.")
            return

        userrank = args
        self.ladder.rank(userrank).addCallback(self.tell_rank,
                                               channel, userrank)

    def handle_command_forecast(self, channel, nick, args):
        """
        Handle !forecast command.
        It expects (parts of) two usernames in args.
        Trigger an update on self.ladder and print match quality.
        """
        if not args:
            self.notice(nick, "You need to specify exactly two players.")
            return

        users = args.split(" ", 1)
        if len(users) != 2:
            self.notice(nick, "You need to specify exactly two players.")
            return

        self.ladder.forecast(users[0], users[1]).addCallback(
            self.tell_forecast, channel, users[0], users[1])

    def handle_command_ratio(self, channel, nick, args):
        """
        Handle !ratio command.
        It expects (parts of) two usernames in args.
        Trigger an update on self.ladder and print match ratio.
        """
        if not args:
            self.notice(nick, "You need to specify exactly two players.")
            return

        users = args.split(" ", 1)
        if len(users) != 2:
            self.notice(nick, "You need to specify exactly two players.")
            return

        self.ladder.ratio(users[0], users[1]).addCallback(
            self.tell_ratio, channel, users[0], users[1])

    def handle_command_suggest(self, channel, nick, args):
        """
        Handle !suggest command.
        It expects (part of) a username in args.
        Trigger an update on self.ladder and print opponents for player.
        """
        if not args:
            self.notice(nick, "You need to include a player name.")
            return

        usersuggest = args

        self.ladder.suggest(usersuggest, 5).addCallback(
            self.tell_suggestion, channel, usersuggest)

    def handle_command_top(self, channel, nick, args):
        """
        Handle !top command.
        It expects a league in args. Valid values are "uber", "platinum",
        "gold", "silver", "bronze".
        Trigger an update on self.leader and print top 10.
        """
        league = "uber"
        initial_dict = {e[0]: e for e in
                        ("uber", "platinum", "gold", "silver", "bronze")}
        if args and args[0] in initial_dict:
            league = initial_dict[args[0]]

        self.leader.top(league).addCallback(self.tell_top, channel, league)

    def handle_command_twitch(self, channel, nick, args):
        """
        Handle !twitch command.
        Trigger an update on self.twitch and print current streams.
        """
        self.twitch.live().addCallback(self.tell_streams, channel)

    def handle_command_twitter(self, channel, nick, args):
        """
        Handler !twitter command.
        It expects the number of tweets to print in args (defaults to 1).
        Trigger an update on self.twitter and print up to N tweets.
        """
        n = int(args) if args and args in ("3", "5", "10") else 1
        self.tweets.latest(n).addCallback(self.tell_tweets, channel)

    def handle_command_tourney(self, channel, nick, args):
        """
        Handle !tourney command.
        It expects either "next" or "last" in args (defaults to "next").
        Trigger an update on self.tourney and print next/last tournament.
        """
        if (not args or args == "next" or args not in ("next", "last")):
            self.tourney.next().addCallback(self.tell_tourney,
                                            "next", channel)
        else:
            self.tourney.last().addCallback(self.tell_tourney,
                                            "last", channel)

    def handle_command_patch(self, channel, nick, args):
        """
        Handle !patch command.
        It doesn't take any arguments.
        Trigger an update on self.patch and print stable/PTE build ID.
        """
        self.patch.patches().addCallback(self.tell_patch, channel)

    def handle_command_news(self, channel, nick, args):
        """
        Handle !news command.
        It doesn't take any arguments.
        Trigger an update on self.misc and print most recent news item.
        """
        self.misc.news(1).addCallback(self.tell_news, channel)

    def handle_command_now(self, channel, nick, args):
        """
        Handle !now command.
        Print current UTC (and US/Pacific) time and date.
        """
        if 0 == randint(0, 999):
            self.msg(channel, u"It is time to dance!")
            self.describe(channel, "dances.")
            return

        now = datetime.utcnow().replace(microsecond=0, tzinfo=utc)
        ubernow = now.astimezone(timezone("US/Pacific"))

        self.msg(channel, u"It is now \x02{0}\x02 (UTC) / "
                          u"\x02{1}\x02 (Ubertime)".format(
                              now.isoformat(" "), ubernow.isoformat(" ")))

    def handle_command_roll(self, channel, nick, args):
        """
        Handle !roll command.
        Print the result of dice rolls.
        """
        dice_pattern = r"(?P<count>\d+)?d(?P<sides>\d+)"
        dice_result = re.match(dice_pattern, args) if args else None
        dice_dict = dice_result.groupdict() if dice_result else dict()

        # by default we toss a coin
        count = int(dice_dict["count"]) if dice_dict.get("count") else 1
        sides = int(dice_dict["sides"]) if dice_dict.get("sides") else 2

        # nothing to do
        if count < 1:
            return

        if count > 10:
            self.describe(channel, "only has 10.")
            count = 1

        if sides is 0:
            self.describe(channel, "slowly backs away from the singularity.")
        elif sides is 1:
            self.msg(channel, u"Rolling {0}... got \x02{1}\x02. Duh.".format(
                "a marble" if count == 1 else "some marbles", count))
        elif sides is 2:
            coins = (choice(("Heads", "Tails")) for _ in range(count))
            coins_bold = map(lambda coin: "\x02{0}\x02".format(coin), coins)
            numerus = "a coin" if count == 1 else "{0} coins".format(count)
            self.msg(channel, u"Tossing {0}... got {1}.".format(
                numerus, ", ".join(coins_bold)))
        elif sides > 100:
            self.describe(channel, "doesn't have one of those.")
        else:
            rolls = [randint(1, sides) for _ in range(count)]
            total = sum(rolls)
            rolls_bold = map(lambda roll: "\x02{0}\x02".format(roll), rolls)
            numerus = ("a d{0}".format(sides) if count == 1 else
                       "{0} d{1}s".format(count, sides))
            self.msg(channel, u"Rolling {0}... got {1}{2}.".format(
                numerus, ", ".join(rolls_bold),
                " => {0}".format(total) if count > 1 else ""))

    def tell_ladder(self, top, channel):
        """Write top n uberskill players to channel."""
        top_n_str = (u"\x02{0}\x02. {1}".format(x + 1, top[x])
                     for x in range(0, len(top)))

        self.msg(channel, u"1on1 Ladder Top \x02{0}\x02: {1}".format(
                          len(top), ", ".join(top_n_str)))

    def tell_stats(self, stats, channel, user):
        """Write win/loss statistic for a specific user to channel."""
        if not stats:
            self.msg(channel, u"1on1 Ladder Stats: "
                              u"Cannot acquire stats for "
                              u"\x02{0}\x02.".format(user))
            return

        name, won, drawn, lost, url = stats
        self.msg(channel, u"1on1 Ladder Stats: "
                          u"\x02{0}\x02 has "
                          u"\x02{1}\x02 wins, "
                          u"\x02{2}\x02 losses and "
                          u"\x02{3}\x02 draws. "
                          u"PA Stats: {4}".format(name,
                                                  won,
                                                  lost,
                                                  drawn,
                                                  url))

    def tell_rank(self, result, channel, user):
        """Write total number of players and the rank of a user to channel."""
        if not result:
            self.msg(channel, u"1on1 Ladder Ranking: "
                              u"\x02{0}\x02 is not ranked.".format(user))
            return

        name, rank, total = result
        if not rank:
            self.msg(channel, u"1on1 Ladder Ranking: "
                              u"\x02{0}\x02 currently is not ranked due to "
                              u"lack of activity.".format(name))
        else:
            self.msg(channel, u"1on1 Ladder Ranking: "
                              u"\x02{0}\x02 is ranked "
                              u"\x02{1}.\x02 out of \x02{2}\x02.".format(
                                  name, rank, total))

    def tell_forecast(self, forecast, channel, user1, user2):
        """Write likely match outcome between to players to channel."""
        if not forecast:
            self.msg(channel, u"1on1 Ladder Forecast: "
                              u"Cannot estimate outcome "
                              u"of \x02{0}\x02 vs \x02{1}\x02.".format(user1,
                                                                       user2))
            return

        name1, name2, draw, score1, score2 = forecast
        # highlight the player most likely to win
        if score1 > score2:
            name1 = "\x02" + name1 + "\x02"
        elif score2 > score1:
            name2 = "\x02" + name2 + "\x02"

        fuzzy = ("Evenly Matched" if draw >= 0.8 else
                 "Skewed Odds" if draw >= 0.5 else
                 "Utter Annihilation")

        self.msg(channel, u"1on1 Ladder Forecast: "
                          u"Match quality for {0} vs {1} is "
                          u"\x02{2:.2%}\x02: \x02{3}\x02.".format(name1,
                                                                  name2,
                                                                  draw,
                                                                  fuzzy))

    def tell_ratio(self, ratio, channel, user1, user2):
        """Write likely match outcome between to players to channel."""
        if not ratio:
            self.msg(channel, u"1on1 Ladder Match Ratio: "
                              u"Cannot determine match ratio between "
                              u"\x02{0}\x02 and \x02{1}\x02.".format(user1,
                                                                     user2))
            return

        name1, name2, nof_games, wins1, wins2 = ratio

        if not nof_games:
            self.msg(channel, u"1on1 Ladder Match Ratio: "
                              u"\x02{0}\x02 and \x02{1}\x02 have not yet "
                              u"played against each other.".format(name1,
                                                                   name2))
            return

        self.msg(channel, u"1on1 Ladder Match Ratio: "
                          u"\x02{0}\x02 and \x02{1}\x02 "
                          u"have played {2} games. "
                          u"Ratio is {3}:{4}.".format(name1, name2,
                                                      nof_games, wins1, wins2))

    def tell_suggestion(self, result, channel, user):
        """Write a user's most interesting opponents to channel."""
        if not result:
            self.msg(channel, u"1on1 Ladder: Cannot suggest opponents for "
                              u"\x02{0}\x02.".format(user))
            return

        name, best = result
        self.msg(channel, u"1on1 Ladder: Most interesting opponents for "
                          u"\x02{0}\x02: {1}.".format(name,
                                                      ", ".join(best)))

    def tell_top(self, top, channel, league):
        """Write top10 for the specified league to channel."""
        top_n_str = (u"\x02{0}\x02. {1}".format(x + 1, top[x])
                     for x in range(0, len(top)))

        self.msg(channel, u"1on1 \x02{0}\x02 Leaderboard: {1}".format(
                          league.capitalize(), ", ".join(top_n_str)))

    def tell_streams(self, streams, channel):
        """Write streams to channel."""
        if not len(streams):
            self.msg(channel, u"There are no Planetary Annihilation streams "
                              u"on \x02twitch\x02 at the moment.")
            return

        number = len(streams)
        if number > 5:
            self.msg(channel, u"There are \x02{0}\x02 PA streams on Twitch. "
                              u"For a full list visit http://www.twitch.tv/"
                              u"directory/game/Planetary%20Annihilation/. "
                              u"Five most viewed streams: ".format(number))
            number = 5
        elif number > 1:
            self.msg(channel, u"There are \x02{0}\x02 PA streams "
                              u"on Twitch:".format(number))
        else:
            self.msg(channel, u"There is \x02{0}\x02 PA stream "
                              u"on Twitch:".format(number))

        for x in range(number):
            desc = streams[x]["desc"] or "No Description"
            self.msg(channel, u"Stream #{0}: {1} "
                              u"by \x02{2}\x02 ({3})".format(
                                  x + 1,
                                  desc.replace("\n", ""),
                                  streams[x]["name"],
                                  streams[x]["url"]))

    def tell_tweets(self, tweets, channel):
        """Write tweets to channel."""
        if not len(tweets):
            self.msg(channel, "Could not acquire any Tweets for #UberRTS.")
            return

        self.msg(channel, u"\x02{0}\x02 latest Tweets "
                          u"for #UberRTS:".format(len(tweets)))

        for tweet in tweets:
            self.msg(channel, u"\x02{0}\x02: » {1} « [{2}]".format(
                tweet["name"], tweet["text"],
                tweet["date"].isoformat(" ")))

    def tell_tourney(self, tourney, state, channel):
        """Write tourney to channel."""
        if not tourney:
            if state == "last":
                self.msg(channel, u"No finished tournaments found.")
            else:
                self.msg(channel, u"No upcoming tournaments found.")
            return

        if state == "next":
            now = datetime.utcnow().replace(microsecond=0)
            if now < tourney["date"]:
                countdown = (u"\u23f3"
                             u"\x033 {0}\x0F".format(tourney["date"] - now))

                self.msg(channel, u"Upcoming tournament: "
                                  u"\x02{0}\x02, \u23f0 {1} (UTC) [{2}]: "
                                  u"{3} ({4})".format(
                                      tourney["name"],
                                      tourney["date"].isoformat(" "),
                                      countdown,
                                      tourney["mode"], tourney["url"]))
            else:
                self.msg(channel, u"Tournament in progress: "
                                  u"\x02{0}\x02, \u23f0 {1} (UTC): "
                                  u"{2} ({3})".format(
                                      tourney["name"],
                                      tourney["date"].isoformat(" "),
                                      tourney["mode"], tourney["url"]))
        else:
            self.msg(channel, u"Latest tournament: "
                              u"\x02{0}\x02, \u23f0 {1} (UTC): "
                              u"Winner(s) \x02{2}\x02 ({3})".format(
                                  tourney["name"],
                                  tourney["date"].isoformat(" "),
                                  tourney["winner"], tourney["url"]))

    def tell_patch(self, patches, channel, **kwargs):
        """Write current build IDs to channel."""
        if not patches:
            self.msg(channel, u"Could not query current patch versions.")
            return

        if (kwargs.get("only_new", False) and self.last_patches == patches):
            return

        # remember patches so we don't announce those we've seen already
        self.last_patches = patches

        info = ("{2}: \x02{0}\x02 ({1})".format(
                patch["build"], patch["date"].isoformat(" "), patch["desc"])
                for patch in patches)

        full_info = u"Latest patch versions: {0}".format(", ".join(info))
        if isinstance(channel, list):
            for c in channel:
                self.msg(c, full_info)
        else:
            self.msg(channel, full_info)

    def tell_news(self, news, channel):
        """Write news item to channel."""
        if not news:
            self.msg(channel, u"Could not retrieve news items.")
            return

        # only use latest news
        news = news[0]

        self.msg(channel, u"Latest News: \x02{1}\x02 [{0}]".format(
            news["date"].isoformat(" "), news["title"]))

    def tell_tourney_countdown(self):
        """Write tourney countdown to all channels and schedule next update."""
        now = datetime.utcnow().replace(microsecond=0)

        if now < self.towncrier.event:
            for channel in self.factory.channels:
                self.msg(channel, u"Next tourney will begin in\x033 {0}\x0F. "
                                  u"Use !tourney for details.".format(
                                      self.towncrier.event - now))

        # schedule next update
        try:
            countdown = next(self.towncrier)
            log.msg(u"Scheduling next tournament announcement in {0}s".format(
                countdown))
            self.towncrier.timer = reactor.callLater(
                countdown, self.tell_tourney_countdown)
        except StopIteration:
            self.towncrier.timer = None

    def handle_tourney_countdown(self, tournament):
        """
        Check if we already have a countdown going for this tournament (or we
        no longer need one).
        """
        # are we already waiting for this one?
        if self.towncrier.event == tournament["date"]:
            return

        # remember this event
        self.towncrier.event = tournament["date"]

        # stop old timer if we have one
        if self.towncrier.timer:
            self.towncrier.timer.cancel()
            self.towncrier.timer = None

        # announce event right away for the first time
        self.tell_tourney_countdown()

    def check_events(self):
        """
        Check for events we need to react on.
        Currently these include new patches and new tournaments.
        """
        # we tell everyone about new patches
        self.patch.patches().addCallback(self.tell_patch,
                                         self.factory.channels,
                                         only_new=True)

        # tournaments are not announced, instead we handle countdowns
        self.tourney.next().addCallback(self.handle_tourney_countdown)


class CommanderFactory(protocol.ClientFactory):
    """
    Factory for Commander IRC connections.

    Reads the configuration, stores relevant settings and passes them to the
    protocol object in buildProtocol.
    """

    instance = None

    def __init__(self):
        """Read configuration from a file or store defaults."""
        irc_cfg = configuration.get_config("irc")

        self.channels = irc_cfg["channels"]
        self.linerate = irc_cfg["linerate"]
        self.nickname = irc_cfg["nickname"]
        self.nickserv = irc_cfg["nickserv"]
        self.realname = irc_cfg["realname"]
        self.username = irc_cfg["username"]

        cmd_cfg = configuration.get_config("cmd")
        self.prefix = cmd_cfg["prefix"]
        self.cmdlimit = cmd_cfg["cmdlimit"]

    def buildProtocol(self, address):
        """Build a new CommanderBot instance and remember it."""
        newBot = CommanderBot()
        newBot.factory = self
        self.instance = newBot
        return newBot

    def getInstance(self):
        """Return a list of created CommanderBots."""
        return self.instance

    def clientConnectionLost(self, connector, reason):
        """Reconnect to the server if we got disconnected."""
        log.msg("Disconnected from server: {0}".format(
            reason.getErrorMessage()))
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        """Stop the reactor if the connection fails."""
        log.msg("Connection to server failed: {0}".format(
            reason.getErrorMessage()))
        reactor.stop()

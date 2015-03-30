# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from datetime import datetime, timedelta
from itertools import chain
from urllib import urlencode

from sqlalchemy import func

from twisted.internet.defer import Deferred, succeed
from twisted.python import log

import trueskill
# default values are fine, let's assume 0.3% draw chance
trueskill.setup(draw_probability=0.003)

from database import Session
from database.models import Player, Game

PASTATS_PLAYER_URL = "http://pastats.com/player"


class LadderParser(object):
    """
    Parser for the gentlemen's 1on1 ladder.

    Reads the current match history asynchronously and parses the output.
    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Initialize database connection."""
        log.msg("Initializing Ladder parser.")
        self.session = Session()

    def getPlayer(self, name):
        """Return a player dictionary for a given name or None if not found."""
        player = (self.session.query(Player)
                  .filter(Player.name.ilike("%"+name+"%"))
                  .first())
        if player:
            return player
        else:
            return None

    def top(self, activity):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            top_query = self.session.query(Player.name)

            if activity:
                treshold = datetime.utcnow() - timedelta(activity)
                top_query = top_query.filter(Player.updated >= treshold)

            top_query = top_query.order_by(Player.rating.desc()).limit(10)

            top = chain(*top_query.all())
            newDeferred.callback(list(top))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

    def stats(self, user):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            player = self.getPlayer(user)
            if player is None:
                newDeferred.callback(None)
            else:
                player_url = ("{0}?{1}"
                              .format(PASTATS_PLAYER_URL,
                                      urlencode({"player": player.pid})))
                w, d, l = player.wdl
                newDeferred.callback((player.name, w, d, l, player_url))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

    def rank(self, user):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            player = self.getPlayer(user)

            treshold = datetime.utcnow() - timedelta(28)
            qry_count = (self.session.query(func.count(Player.pid))
                                     .filter(Player.updated >= treshold))
            total = qry_count.scalar()

            if player is None:
                newDeferred.callback(None)
            elif player.updated < treshold:
                newDeferred.callback((player.name, None, total))
            else:
                cmp_rating = (self.session.query(Player.rating)
                                  .filter(Player.pid == player.pid).subquery())
                rank = qry_count.filter(Player.rating > cmp_rating).scalar()
                newDeferred.callback((player.name, 1 + rank, total))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

    def forecast(self, user1, user2):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            p1 = self.getPlayer(user1)
            p2 = self.getPlayer(user2)

            if p1 is None or p2 is None or p1 == p2:
                newDeferred.callback(None)
            else:
                newDeferred.callback((p1.name, p2.name,
                                      trueskill.quality_1vs1(p1.skill,
                                                             p2.skill),
                                      p1.rating, p2.rating))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

    def suggest(self, user, n):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            player = self.getPlayer(user)
            if player is None:
                newDeferred.callback(None)
            else:
                players = (self.session.query(Player)
                           .filter(Player.pid != player.pid)
                           .all())

                best = [(other.name, trueskill.quality_1vs1(player.skill,
                                                            other.skill))
                        for other in players]

                best = sorted(best, key=lambda p: p[1], reverse=True)
                best_names = [p[0] for p in best[0:n]]
                newDeferred.callback((player.name, best_names))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

    def ratio(self, user1, user2):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            p1 = self.getPlayer(user1)
            p2 = self.getPlayer(user2)

            if p1 is None or p2 is None or p1 == p2:
                newDeferred.callback(None)
            else:
                games = (self.session.query(Game)
                         .filter(Game.players.contains(p1),
                                 Game.players.contains(p2))
                         .all())

                p1_wins = sum(1 for g in games if g.wid == p1.pid)
                p2_wins = sum(1 for g in games if g.wid == p2.pid)
                newDeferred.callback((p1.name, p2.name,
                                      len(games), p1_wins, p2_wins))

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

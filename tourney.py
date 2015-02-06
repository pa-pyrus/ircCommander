# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from twisted.internet.defer import Deferred, succeed
from twisted.python import log

from sqlalchemy import func, extract

from database import Session
from database.models import Tournament


class TourneyParser(object):
    """
    Access the crowd sourced Tournament schedule.

    All tournaments are stored in a local database. No external information is
    queried and nothing is parsed per se.

    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Initialize database connection."""
        log.msg("Initializing Tourney parser.")
        self.session = Session()

    def next(self):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            query = self.session.query(Tournament)
            query = query.filter(Tournament.winner.is_(None))
            query = query.order_by(func.abs(extract(
                "epoch", func.now() - Tournament.date)))
            tournament = query.limit(1).first()
            if not tournament:
                newDeferred.callback(None)
            else:
                tourney_dict = {"name": tournament.title,
                                "date": tournament.date,
                                "mode": tournament.mode,
                                "url": tournament.url}
                newDeferred.callback(tourney_dict)
            self.session.close()
        updateDeferred.addCallback(updateDone)

        return newDeferred

    def last(self):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            query = self.session.query(Tournament)
            query = query.filter(Tournament.winner.isnot(None))
            query = query.order_by(func.abs(extract(
                "epoch", func.now() - Tournament.date)))
            tournament = query.limit(1).first()
            if not tournament:
                newDeferred.callback(None)
            else:
                tourney_dict = {"name": tournament.title,
                                "date": tournament.date,
                                "winner": tournament.winner,
                                "mode": tournament.mode,
                                "url": tournament.url}
                newDeferred.callback(tourney_dict)
            self.session.close()
        updateDeferred.addCallback(updateDone)

        return newDeferred

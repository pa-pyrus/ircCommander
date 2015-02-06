# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from database import Session
from database.models import LeaderBoardEntry, UberAccount

from twisted.internet.defer import Deferred, succeed
from twisted.python import log


class LeaderParser(object):
    """
    Retrieves most recently cached rankings for the specified league.
    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Initialize a database session."""
        log.msg("Initializing Ubernet Leaderboard parser.")
        self.session = Session()

    def top(self, league):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        league = league.capitalize()

        def updateDone(value):
            """Callback method for update."""
            entries = (self.session.query(LeaderBoardEntry.uid,
                                          UberAccount.dname)
                           .outerjoin(UberAccount,
                                      UberAccount.uid == LeaderBoardEntry.uid)
                           .filter(LeaderBoardEntry.league == league)
                           .order_by(LeaderBoardEntry.rank))

            newDeferred.callback([e[1] for e in entries])

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

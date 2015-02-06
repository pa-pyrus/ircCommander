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
        """Read configuration from a file or store defaults."""
        log.msg("Initializing Ubernet Leaderboard parser.")
        self.session = Session()

    def startUpdate(self):
        """
        Initiate an update using Twisted.

        The request is handled asynchronously. It will call onUpdate if it's
        successful and onError otherwise.
        """
        deferred = succeed(None)
        deferred.addCallbacks(self.onUpdate, self.onError)
        return deferred

    def onUpdate(self, value):
        """Patches are updated by a cronjob, no need to do it here."""
        return None

    def onError(self, error):
        """Error callback for retrieving Uberent API data."""
        log.err("Encountered an error: {0}".format(
            error.getErrorMessage()))
        return error

    def top(self, league):
        """Start an update and return a deferred containing the results."""
        updateDeferred = self.startUpdate()
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

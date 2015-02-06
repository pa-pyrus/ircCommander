# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from twisted.internet.defer import Deferred, succeed
from twisted.python import log

from database import Session
from database.models import Patch


class PatchParser(object):
    """
    Parser for PA patch webservice.

    Retrieves the most recently cached patch and stream information.
    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Initialize a database session."""
        log.msg("Initializing Ubernet Patch parser.")
        self.session = Session()

    def patches(self):
        """Start an update and return a deferred containing the results."""
        updateDeferred = succeed(None)
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            patches_query = self.session.query(Patch.description,
                                               Patch.build,
                                               Patch.updated).all()
            if not patches_query:
                newDeferred.callback(None)
            else:
                patches = [{"desc": patch.description,
                            "build": patch.build,
                            "date": patch.updated}
                           for patch in patches_query]
                newDeferred.callback(patches)

            self.session.close()

        updateDeferred.addCallback(updateDone)

        return newDeferred

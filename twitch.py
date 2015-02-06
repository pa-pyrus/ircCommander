# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from binascii import crc32
from json import loads

from twisted.internet.defer import Deferred
from twisted.python import log
from twisted.web.client import getPage

TWITCH_URL = "https://api.twitch.tv/kraken/streams?game=Planetary+Annihilation"


class TwitchParser(object):
    """
    Parser for the Twitch.tv web API.

    Reads a Twitch.tv web API URL asynchronously and parses the JSON output.
    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Initialize Twitch parser members."""
        log.msg("Initializing Twitch parser.")

        # initialize our data members
        self.streams = tuple()
        self.crc32 = 0

    def startUpdate(self):
        """
        Initiate an update using Twisted.

        The request is handled asynchronously. It will call onUpdate if it's
        successful and onError otherwise.
        """
        log.msg("Updating URL contents for: {0}".format(TWITCH_URL))
        deferred = getPage(TWITCH_URL)
        deferred.addCallbacks(self.onUpdate, self.onError)
        return deferred

    def onUpdate(self, value):
        """Value callback for retrieving Twitch API data."""
        # compare checksum to avoid work
        new_crc = crc32(value)
        if self.crc32 == new_crc:
            log.msg("CRC32 hasn't changed, not parsing data.")
            return self.streams
        self.crc32 = new_crc

        data = loads(value, encoding="utf-8")

        streams = tuple({"name": stream["channel"]["display_name"],
                         "desc": stream["channel"]["status"],
                         "url": stream["channel"]["url"],
                         "viewers": stream["viewers"]}
                        for stream in data["streams"])
        self.streams = sorted(streams,
                              key=lambda x: x["viewers"],
                              reverse=True)

        log.msg("Received and parsed new data: {0}".format(self.streams))
        return self.streams

    def onError(self, error):
        """Error callback for retrieving Twitch API data."""
        log.err("Encountered an error: {0}".format(
            error.getErrorMessage()))
        return error

    def live(self):
        """Start an update and return a deferred containing the results."""
        updateDeferred = self.startUpdate()
        newDeferred = Deferred()
        updateDeferred.addCallbacks(newDeferred.callback, newDeferred.errback)
        return newDeferred

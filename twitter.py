# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from base64 import b64encode
from binascii import crc32
from datetime import datetime
from json import loads
from urllib import urlencode, quote
from HTMLParser import HTMLParser

from twisted.internet.defer import Deferred, fail, succeed
from twisted.python import log
from twisted.web.client import getPage

import configuration

CREATED_AT_FORMAT = "%a %b %d %H:%M:%S +0000 %Y"
TWITTER_SEARCH_URL = "https://api.twitter.com/1.1/search/tweets.json"
TWITTER_OAUTH2_URL = "https://api.twitter.com/oauth2/token"


class TwitterParser(object):
    """
    Reads Tweets matching the configured query using the Twitter API and parses
    the output.
    Provides deferred functions that can be called from other Twisted
    applications.
    """

    def __init__(self):
        """Read configuration from a file or store defaults."""
        log.msg("Initializing Twitter parser.")

        twitter_cfg = configuration.get_config("twitter")

        self.b64token = b64encode("{0}:{1}".format(
            quote(twitter_cfg["key"]), quote(twitter_cfg["secret"])))

        params = {"q": twitter_cfg["query"],
                  "count": 100,
                  "lang": "en",
                  "result_type": "recent",
                  "include_entities": "false"}
        self.url = "{0}?{1}".format(TWITTER_SEARCH_URL, urlencode(params))
        log.msg("Encoded Twitter API URL: {0}".format(self.url))

        # initialize our data members
        self.bearer = None
        self.tweets = tuple()
        self.crc32 = 0

    def getBearer(self):
        """Get the bearer token used to authenticate for the API call."""
        # if we already have the bearer token we return success right away
        if self.bearer:
            return succeed(True)

        log.msg("Requesting bearer token for application.")

        headers = {"Authorization": "Basic {0}".format(self.b64token),
                   "Content-Type": "application/x-www-form-urlencoded;"
                                   "charset=UTF-8"}

        deferred = getPage(TWITTER_OAUTH2_URL,
                           method="POST",
                           postdata="grant_type=client_credentials",
                           headers=headers)
        deferred.addCallbacks(self.onBearer, self.onError)
        return deferred

    def onBearer(self, bearer):
        """Callback for when the bearer token is received."""
        # bearer is json, extract the token
        data = loads(bearer, encoding="utf-8")
        self.bearer = data.get("access_token")
        return True if "access_token" in data else False

    def startUpdate(self):
        """
        Initiate an update using Twisted.

        The request is handled asynchronously. It will call onUpdate if it's
        successful and onError otherwise.
        """
        # get bearer either from cache or with a new request
        bearerDeferred = self.getBearer()

        def gotBearer(success):
            """Local callback for bearer token."""
            # if we can't get the token, report failure
            if not success or not self.bearer:
                return fail()
            # otherwise we start the update here
            log.msg("Updating URL contents for: {0}".format(self.url))
            headers = {"Authorization": "Bearer {0}".format(self.bearer)}
            deferred = getPage(self.url, headers=headers)
            deferred.addCallbacks(self.onUpdate, self.onError)
            return deferred

        # now chain the callbacks together
        bearerDeferred.addCallback(gotBearer)
        return bearerDeferred

    def onUpdate(self, value):
        """Value callback for retrieving Twitter API data."""
        # compare checksum to avoid work
        new_crc = crc32(value)
        if self.crc32 == new_crc:
            log.msg("CRC32 hasn't changed, not parsing data.")
            return self.tweets
        self.crc32 = new_crc

        data = loads(value, encoding="utf-8")
        parser = HTMLParser()
        self.tweets = tuple({"date": datetime.strptime(status["created_at"],
                                                       CREATED_AT_FORMAT),
                             "text": parser.unescape(status["text"]),
                             "name": status["user"]["name"],
                             "screen": status["user"]["screen_name"]}
                            for status in data["statuses"]
                            if not status["text"].startswith("RT"))

        log.msg("Received and parsed new data.")
        return self.tweets

    def onError(self, error):
        """Error callback for retrieving Twitter API data."""
        log.err("Encountered an error: {0}".format(
            error.getErrorMessage()))
        return error

    def latest(self, n):
        """Start an update and return a deferred containing the results."""
        updateDeferred = self.startUpdate()
        newDeferred = Deferred()

        def updateDone(value):
            """Callback method for update."""
            newDeferred.callback(self.tweets[0:n])
        updateDeferred.addCallback(updateDone)

        return newDeferred

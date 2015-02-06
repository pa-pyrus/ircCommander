# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

from datetime import datetime
from json import loads
from urllib import urlencode

from twisted.internet.defer import Deferred
from twisted.python import log
from twisted.web.client import getPage

UBERNET_NEWS_URL = "http://uberent.com/GameClient/GetNews"


class MiscParser(object):
    """
    Parser for miscellaneous web API calls.

    It supports reading a variety of different APIs returning JSON data.
    """

    def __init__(self):
        """Do nothing for now."""
        pass

    def startNewsUpdate(self, count):
        """
        Initiate an update using Twisted.

        The request is handled asynchronously. It will call onUpdate if it's
        successful and onError otherwise.
        """
        log.msg("Updating URL contents for: {0}".format(self.news_url))
        url = "{0}?{1}".format(self.news_url, urlencode({"titleid": 4,
                                                         "count": count}))
        deferred = getPage(url)
        deferred.addCallbacks(self.onNewsUpdate, self.onError)
        return deferred

    def onNewsUpdate(self, value):
        """Value callback for retrieving Uberent News data."""
        data = loads(value, encoding="utf-8")

        news = [{"date": datetime.strptime(item["Timestamp"],
                                           "%Y-%m-%d.%H:%M:%S"),
                 "title": item["Title"]}
                for item in data["News"]]

        log.msg("Received and parsed new data: {0}".format(news))
        return news

    def news(self, count):
        """Start an update and return a deferred containing the results."""
        updateDeferred = self.startNewsUpdate(count)
        newDeferred = Deferred()
        updateDeferred.addCallbacks(newDeferred.callback, newDeferred.errback)
        return newDeferred

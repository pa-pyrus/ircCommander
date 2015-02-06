#!/usr/bin/env twistd
# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79:ft=python

"""
commander.tac

Twisted service description file.
It sets up logging, the IRC client and an (optional) SSH manhole.

Copyright (c) 2015 Pyrus <pyrus at coffee dash break dot at>
See the file LICENSE for copying permission.
"""

from twisted.application import internet, service
from twisted.conch import manhole, manhole_ssh
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.cred import portal
from twisted.internet import ssl
from twisted.python import log
from twisted.python.logfile import LogFile

import configuration
from bot import CommanderFactory

# now read config and setup application
twisted_cfg = configuration.get_config("twisted")

application = service.Application(twisted_cfg["appname"])
logfile = LogFile(twisted_cfg["logname"],
                  twisted_cfg["logpath"],
                  maxRotatedFiles=twisted_cfg["logrotate"])
application.setComponent(log.ILogObserver, log.FileLogObserver(logfile).emit)

factory = CommanderFactory()

irc_cfg = configuration.get_config("irc")
irc_server = irc_cfg["hostname"]
irc_port = irc_cfg["port"]

if irc_cfg["ssl"]:
    irc_client = internet.SSLClient(
            irc_server, irc_port, factory, ssl.CertificateOptions())
else:
    irc_client = internet.TCPClient(irc_server, irc_port, factory)

irc_client.setServiceParent(service.IService(application))

manhole_cfg = configuration.get_config("manhole")
if manhole_cfg["port"]:
    def getManholeFactory(namespace):
        """Create a manhole factory for the given namespace dict."""
        realm = manhole_ssh.TerminalRealm()

        def getManhole(_):
            """Return a manhole for the given namespace dict."""
            return manhole.Manhole(namespace)

        realm.chainedProtocolFactory.protocolFactory = getManhole
        p = portal.Portal(realm)
        p.registerChecker(SSHPublicKeyDatabase())
        return manhole_ssh.ConchFactory(p)

    namespace = {"getBot": factory.getInstance}
    manhole_server = internet.TCPServer(manhole_cfg["port"],
                                        getManholeFactory(namespace))
    manhole_server.setServiceParent(service.IService(application))

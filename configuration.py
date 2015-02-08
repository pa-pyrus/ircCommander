# vim:fenc=utf-8:ts=8:et:sw=4:sts=4:tw=79:ft=python

"""
configuration.py

The Commander IRC bot configuration loader.
It reads configuratiom from environment variables and provides access to
component specific dictionaries.

Copyright (c) 2015 Pyrus <pyrus at coffee dash break dot at>
See the file LICENSE for copying permission.
"""

from os import environ


def __get_irc_config():
    """Get a configuration dictionary for IRC specific settings."""
    channel_list = environ["COMMANDER_IRC_CHANNELS"]
    channels = channel_list.split(";")

    return {"hostname": environ["COMMANDER_IRC_HOSTNAME"],
            "port": int(environ["COMMANDER_IRC_PORT"]),
            "ssl": True if "COMMANDER_IRC_SSL" in environ else False,
            "nickserv": environ.get("COMMANDER_IRC_NICKSERV"),
            "nickname": environ["COMMANDER_IRC_NICKNAME"],
            "username": environ["COMMANDER_IRC_USERNAME"],
            "realname": environ["COMMANDER_IRC_REALNAME"],
            "linerate": int(environ["COMMANDER_IRC_LINERATE"]),
            "channels": channels}


def __get_cmd_config():
    """Get a configuration dictionary for command handling settings."""
    return {"prefix": environ.get("COMMANDER_CMD_PREFIX", "!"),
            "cmdlimit": int(environ["COMMANDER_CMD_CMDLIMIT"])}


def __get_twitter_config():
    """Get a configuration dictionary for a CommandHandler instance."""

    return {"key": environ["COMMANDER_TWITTER_KEY"],
            "query": environ["COMMANDER_TWITTER_QUERY"],
            "secret": environ["COMMANDER_TWITTER_SECRET"]}


def __get_manhole_config():
    """Get a configuration dictionary for Twisted manhole settings."""
    port = environ.get("COMMANDER_MANHOLE_PORT")

    return {"port": int(port) if port else port}


def __get_twisted_config():
    """Get a configuration dictionary for Twisted settings."""

    return {"appname": environ["COMMANDER_TWISTED_APP_NAME"],
            "logpath": environ["COMMANDER_TWISTED_LOG_PATH"],
            "logname": environ["COMMANDER_TWISTED_LOG_NAME"],
            "logrotate": int(environ["COMMANDER_TWISTED_LOG_ROTATE"])}


def get_config(component):
    """
    Get a configuration dictionary for a specific component.
    Valid components are:
    - irc
    - cmd
    - twitter
    - twisted
    - manhole
    """
    if component == "irc":
        return __get_irc_config()
    elif component == "cmd":
        return __get_cmd_config()
    elif component == "twitter":
        return __get_twitter_config()
    elif component == "twisted":
        return __get_twisted_config()
    elif component == "manhole":
        return __get_manhole_config()

    # we don't know that config
    raise KeyError("No such component: {0}".format(component))

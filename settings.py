#!/usr/bin/env python
# -*- coding: utf8 -*-

from os import path, getenv
from sys import exit
import ConfigParser
import logging
from UserDict import IterableUserDict

CONFIG_DIR = '/etc/showtime/'
CONFIG_FILE = 'showtime.conf'

DEFAULTS = {
    'viewer': {
        'show_splash': True,
        'audio_output': 'hdmi',
        'loglevel': 20,
        'base_url' : '',
        'verify_ssl' : False,
        'uzbl_configfile': '/etc/showtime/uzbl.rc',
        'debug' : False,
        'base_path' : ''
    },
}

# Initiate logging
logging.basicConfig(level=logging.DEBUG,
                    filename='/tmp/showtime_viewer.log',
                    format='%(asctime)s [%(levelname)8s] %(filename)12s:%(lineno)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

# Silence urllib info messages ('Starting new HTTP connection')
# that are triggered by the remote url availability check in view_web
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.DEBUG)

logging.debug('Starting settings.py')

class ShowtimeSettings(IterableUserDict):
    "Showtime Settings."

    def __init__(self, *args, **kwargs):
        rv = IterableUserDict.__init__(self, *args, **kwargs)
        self.home = getenv('HOME')
        self.conf_file = self.get_configfile()

        if not path.isfile(self.conf_file):
            print 'Config-file %s missing' % (self.conf_file)
            exit(1)
        else:
            self.load()
        return rv

    def _get(self, config, section, field, default):
        try:
            if isinstance(default, bool):
                self[field] = config.getboolean(section, field)
            elif isinstance(default, int):
                self[field] = config.getint(section, field)
            else:
                self[field] = config.get(section, field)
        except ConfigParser.Error as e:
            logging.debug("Could not parse setting '%s.%s': %s. Using default value: '%s'." % (section, field, unicode(e), default))
            self[field] = default
        if field in ['database', 'assetdir']:
            self[field] = str(path.join(self.home, self[field]))

    def _set(self, config, section, field, default):
        if isinstance(default, bool):
            config.set(section, field, self.get(field, default) and 'on' or 'off')
        else:
            config.set(section, field, unicode(self.get(field, default)))

    def load(self):
        "Loads the latest settings from showtime.conf into memory."
        logging.debug('Reading config-file...')
        config = ConfigParser.ConfigParser()
        config.read(self.conf_file)

        for section, defaults in DEFAULTS.items():
            for field, default in defaults.items():
                self._get(config, section, field, default)

    def save(self):
        # Write new settings to disk.
        config = ConfigParser.ConfigParser()
        for section, defaults in DEFAULTS.items():
            config.add_section(section)
            for field, default in defaults.items():
                self._set(config, section, field, default)
        with open(self.conf_file, "w") as f:
            config.write(f)
        self.load()

    def get_configdir(self):
        return path.join(CONFIG_DIR)

    def get_configfile(self):
        return path.join(CONFIG_DIR, CONFIG_FILE)

    def get_listen_ip(self):
        return self['listen'].split(':')[0]

    def get_listen_port(self):
        return self['listen'].split(':')[1]

settings = ShowtimeSettings()

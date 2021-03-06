#!/usr/bin/env python
# -*- coding: utf8 -*-

from datetime import datetime, timedelta
import time
from os import path, getenv, utime
from platform import machine
from random import shuffle
from requests import get as req_get
from time import sleep, time
from json import load as json_load
import sys
import signal
import logging
import sh
import json
import subprocess
import urllib2

from settings import settings
from utils import url_fails

SPLASH_DELAY = 0  # secs
EMPTY_PL_DELAY = 5  # secs

WATCHDOG_PATH = settings.get('watchdog')
UZBLRC = settings.get('uzbl_configfile')  # absolute path
BASE_URL = settings.get('base_url')
BASE_PATH = settings.get('base_path')
ASSET_PATH = '{0}/assets'.format(BASE_PATH)
BLACK_PAGE = '{0}/static/black_page.html'.format(BASE_PATH)
SPLASH_PAGE = '{0}/pages/splash'.format(BASE_URL)

print settings

current_browser_url = None
browser = None

VIDEO_TIMEOUT=20  # secs

class Scheduler(object):
    def __init__(self, *args, **kwargs):
        logging.info('Scheduler init')
        self.update_playlist()

    def get_next_asset(self):
        logging.debug('get_next_asset')
        self.refresh_playlist()
        logging.debug('get_next_asset after refresh')
        if self.nassets == 0:
            return None
        idx = self.index
        self.index = (self.index + 1) % self.nassets
        logging.debug('get_next_asset counter %s returning asset %s of %s', self.counter, idx + 1, self.nassets)
        return self.assets[idx]

    def refresh_playlist(self):
        logging.debug('refresh_playlist')
        time_cur = int(time())
        logging.debug('refresh: counter: (%s) deadline (%s) timecur (%s)', self.counter, self.deadline, time_cur)
        logging.debug("current deadline: {0}".format(self.deadline))
        logging.debug("current time:     {0}".format(time_cur))
        logging.debug("db modtime:        {0}".format(self.get_db_mtime()))
        logging.debug("db modtime stored: {0}".format(self.last_update_db_mtime))
        
        
        if self.get_db_mtime() != self.last_update_db_mtime:
            logging.info('updating playlist due to database modification')
            self.update_playlist()
        elif self.deadline and self.deadline <= time_cur:
            logging.info('updating playlist due to deadline')
            self.update_playlist()

    def update_playlist(self):

        logging.debug('update_playlist')
        self.last_update_db_mtime = self.get_db_mtime()
        (self.assets, self.deadline) = generate_asset_list()
        self.nassets = len(self.assets)
        self.counter = 0
        self.index = 0
        logging.debug('update_playlist done, count %s, counter %s, index %s, deadline %s', self.nassets, self.counter, self.index, self.deadline)

    def get_db_mtime(self):
        return urllib2.urlopen("{0}/json/get_playlist_modtime/{1}".format(BASE_URL, get_active_playlist())).read()
    

def generate_asset_list():
    logging.debug('Generating asset-list...')
    
    playlist = json.loads(urllib2.urlopen("{0}/json/client_assetlist/{1}".format(BASE_URL, get_device_id())).read())
    
    deadline = sorted([asset['end_date'] for asset in playlist])[0] if len(playlist) > 0 else None
    logging.debug('generate_asset_list deadline: %s', deadline)

    return (playlist, deadline)

def get_device_id():
    return urllib2.urlopen("{0}/json/get_device_id".format(BASE_URL)).read()
    
def get_active_playlist():
    return json.loads(urllib2.urlopen("{0}/json/get_active_playlist/{1}".format(BASE_URL, get_device_id())).read())

def watchdog():
    """Notify the watchdog file to be used with the watchdog-device."""
    """if not path.isfile(WATCHDOG_PATH):
        open(WATCHDOG_PATH, 'w').close()
    else:
        utime(WATCHDOG_PATH, None)"""
    pass


def load_browser(url=None):
    global browser, current_browser_url
    logging.debug('Loading browser...')

    if browser:
        logging.info('killing previous uzbl %s', browser.pid)
        browser.process.kill()

    if not url is None:
        current_browser_url = url

    # --config=-       read commands (and config) from stdin
    # --print-events   print events to stdout
    if settings.get('debug') == 0:
        browser = sh.Command('uzbl-browser')(print_events=True, config='-', uri=current_browser_url, _bg=True)
        logging.debug('Browser loading %s. Running as PID %s.', current_browser_url, browser.pid)
        uzbl_rc = 'ssl_verify {}\n'.format('1' if settings['verify_ssl'] else '0')
        with open(UZBLRC) as f:  # load uzbl.rc
            uzbl_rc = f.read() + uzbl_rc
    
        logging.debug("UZBL config: "+uzbl_rc)
        browser_send(uzbl_rc)
    else:
        logging.debug("Not starting browser due to debugmode")



def browser_send(command, cb=lambda _: True):
    if not (browser is None) and browser.process.alive:
        while not browser.process._pipe_queue.empty():  # flush stdout
            browser.next()

        browser.process.stdin.put(command + '\n')
        while True:  # loop until cb returns True
            if cb(browser.next()):
                break
    else:
        logging.warning('browser found dead, restarting')
        load_browser()


def browser_clear(force=False):
    """Load a black page. Default cb waits for the page to load."""
    browser_url(BLACK_PAGE, force=force, cb=lambda buf: 'LOAD_FINISH' in buf and BLACK_PAGE in buf)


def browser_url(url, cb=lambda _: True, force=False):
    global current_browser_url
    logging.info("Current url: {0}".format(url))

    if url == current_browser_url and not force:
        logging.info('Already showing %s, keeping it.', current_browser_url)
    else:
        current_browser_url = url
        browser_send('uri ' + current_browser_url, cb=cb)
        logging.info('current url is %s', current_browser_url)


def view_image(uri):
    browser_clear()
    logging.info("Current uri: {0}".format(uri))
    browser_send('js window.setimg("{0}")'.format(uri), cb=lambda b: 'COMMAND_EXECUTED' in b and 'setimg' in b)


def view_video(uri, duration, live = ''):
    logging.info('Displaying video %s for %s ', uri, duration)
    
    if arch == 'armv6l':
        player_args = ['omxplayer', uri, live, "-o", "hdmi"]
	"""        player_kwargs = {'o': settings['audio_output'], '_bg': True, '_ok_code': [0, 124]}"""
        player_kwargs = {'_bg': True, '_ok_code': [0, 124]}

        player_kwargs['_ok_code'] = [0, 124]
    else:
        player_args = ['mplayer', uri, '-nosound']
        player_kwargs = {'_bg': True}

    if duration and duration != 'N/A':
        player_args = ['timeout', VIDEO_TIMEOUT + int(duration.split('.')[0])] + player_args

    run = sh.Command(player_args[0])(*player_args[1:], **player_kwargs)

    browser_clear(force=True)
    while run.process.alive:
        print run.process
        watchdog()
        sleep(1)
    if run.exit_code == 124:
        logging.error('omxplayer timed out')

def view_livestream(uri, duration):
    logging.info('Displaying video {0} for {1} '.format(uri, duration))
    logging.info("LIVESTREAMING")
    player_args = ['livestreamer', uri, 'best', '--fifo', '--player', '/usr/bin/omxplayer']
    player_kwargs = {'o': settings['audio_output'], '_bg': True, '_ok_code': [0, 124]}
    player_kwargs = {'_ok_code': [0, 1, 124]}
        
    cmd = subprocess.Popen(("livestreamer", uri, "best", "--fifo", "--player", "/usr/bin/omxplayer"))
    sleep(float(duration))
    cmd.terminate()
    logging.info("DONE LIVESTREAMING")

def load_settings():
    """Load settings and set the log level."""
    settings.load()
    
def asset_loop(scheduler):
    logging.debug("")
    logging.debug("")
    logging.debug("New Loop")
    asset = scheduler.get_next_asset()
    logging.info("Active Playlist: {0}".format(get_active_playlist()))
    logging.info("Asset: {}".format(asset))
    
    if asset is None:
        logging.info(('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY))
        view_url(SPLASH_PAGE)
        sleep(EMPTY_PL_DELAY)

    elif path.isfile(asset['uri']) or not url_fails(asset['uri']):
        name, mime, uri = asset['name'], asset['mimetype'], asset['uri']
        logging.info('Showing asset %s (%s)', name, mime)
        logging.info('Asset URI %s', uri)
        watchdog()
        
        if 'image' in mime:
            logging.debug("VIEWING IMAGE")
            view_image("file://{0}/{1}".format(ASSET_PATH, uri))
        elif 'webpage' in mime:
            logging.debug("VIEWING WEB")
            browser_url(uri)
        elif 'video' in mime:
            logging.debug("VIEWING VIDEO")
            view_video("{0}/{1}".format(ASSET_PATH, uri), asset['duration'])
        elif 'rtmp' in mime:
            logging.debug("VIEWING RTMP")
            view_video(uri, asset['duration'], '--live')
        elif 'livestream' in mime:
            logging.debug("VIEWING LIVESTREAM")
            view_livestream(uri, asset['duration'])
        else:
            logging.error('Unknown MimeType %s', mime)

        if 'image' in mime or 'web' in mime:
            duration = int(asset['duration'])
            logging.debug('Sleeping for %s', duration)
            sleep(duration)
    else:
        logging.warning('Asset %s at %s is not available, skipping.', asset['name'], asset['uri'])
        sleep(0.5)

    
def main_loop(scheduler):
    while True:
        asset_loop(scheduler)
    
    
def setup():
    global HOME, arch, DB, device_id
    HOME = getenv('HOME', '/home/pi')
    arch = machine()

    """ Setup some signalhandlers """
    signal.signal(signal.SIGUSR1, sigusr1)
    signal.signal(signal.SIGUSR2, sigusr2)
    signal.signal(signal.SIGINT, sigint)
    signal.signal(signal.SIGTERM, sigterm)

    load_settings()
    
    device_id = get_device_id()

def sigusr1(signum, frame):
    """
    The signal interrupts sleep() calls, so the currently playing web or image asset is skipped.
    omxplayer is killed to skip any currently playing video assets.
    """
    logging.info('USR1 received, skipping.')
    sh.killall('omxplayer.bin', _ok_code=[1])


def sigusr2(signum, frame):
    """Reload settings"""
    logging.info("USR2 received, reloading settings.")
    load_settings()
    
def sigint(signum, frame):    
    logging.info("User interrupt Exiting gracefully.")
    sys.exit(0)
    
def sigterm(signum, frame):    
    logging.info("Termination. Exiting gracefully.")
    sys.exit(0)
    
def main():
    setup()
    
    logging.info("Splash url: {0}".format(SPLASH_PAGE))
    logging.info("Splash delay: {0}".format(SPLASH_DELAY))

    load_browser(url=SPLASH_PAGE)
    logging.debug("sleeping: {0}".format(SPLASH_DELAY))
    sleep(SPLASH_DELAY)
    logging.debug("done sleeping")
    
    logging.info("Device ID: {0}".format(get_device_id()))

    scheduler = Scheduler()
    logging.debug('Entering infinite loop.')
    while True:
        asset_loop(scheduler)
    #thread.start_new_thread( main_loop, (scheduler,) )

        


if __name__ == "__main__":
    main()

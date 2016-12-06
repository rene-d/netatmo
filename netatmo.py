#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:set ts=4 sw=4 et:

# rene, november 2016

"""
    Python API for Netatmo Weather Station

    inspired by https://github.com/philippelt/netatmo-api-python
"""

import sys
import os
import time
import datetime
import re
import argparse
import configparser
import json
import csv
import pprint
import requests

verbosity = 0

DEFAULT_RC_FILE = "~/.netatmorc"


# Common definitions
_BASE_URL            = "https://api.netatmo.com/"
_AUTH_REQ            = _BASE_URL + "oauth2/token"
_GETSTATIONSDATA_REQ = _BASE_URL + "api/getstationsdata"
_GETMEASURE_REQ      = _BASE_URL + "api/getmeasure"

class Colors:
    """
        ANSI SGR codes
        https://en.wikipedia.org/wiki/ANSI_escape_code#graphics
    """
    Reset        = '\033[0m'        # Reset / Normal
    Bold         = '\033[1m'        # Bold or increased intensity
    Faint        = '\033[2m'        # Faint (decreased intensity)
    Underline    = '\033[4m'        # Underline: Single
    Blink        = '\033[5m'        # Blink: Slow
    Inverse      = '\033[7m'        # Image: Negative
    Black        = '\033[0;30m'
    Red          = '\033[0;31m'
    Green        = '\033[0;32m'
    Yellow       = '\033[0;33m'
    Blue         = '\033[0;34m'
    Magenta      = '\033[0;35m'
    Cyan         = '\033[0;36m'
    LightGray    = '\033[0;37m'
    DarkGray     = '\033[1;30m'
    LightRed     = '\033[1;31m'
    LightGreen   = '\033[1;32m'
    LightYellow  = '\033[1;33m'
    LightBlue    = '\033[1;34m'
    LightMagenta = '\033[1;35m'
    LightCyan    = '\033[1;36m'
    White        = '\033[1;37m'

trace_output = sys.stdout

if not trace_output.isatty():
    for _ in dir(Colors):
        if not _.startswith('__'): setattr(Colors, _, '')

def trace(level, *args, pretty=False):
    """ print a colorized message when stdoud is a terminal """
    if verbosity >= level:
        pretty = pprint.pformat if pretty else str
        cc = {
            -2: Colors.LightRed,
            -1: Colors.LightYellow,
            0: '',
            1: Colors.Green,
            2: Colors.Yellow,
            3: Colors.Red
        }
        color = cc.get(level, '')
        trace_output.write(color)
        for i, v in enumerate(args):
            if i != 0: trace_output.write(' ')
            trace_output.write(pretty(v))
        trace_output.write(Colors.Reset)
        trace_output.write('\n')


def _post_request(url, params):
    """
        wrapper to the GET request

        url
        params
    """
    trace(1, ">>>> " + url)
    trace(2, params, pretty=True)
    if verbosity >= 1:
        t = time.time()
    resp = requests.post(url, data=params)
    if verbosity >= 1:
        trace(1, "<<<< %d bytes in %.3f s" % (len(resp.content), time.time() - t))
    ret = json.loads(resp.text)
    trace(2, ret, pretty=True)
    return ret


class WeatherStation:
    """
        class to access data
    """

    def __init__(self, configuration):
        self._access_token = None
        self._refresh_token = None
        self._expiration = None

        self.auth(None, None, None, None)
        self.default_station = None
        self.user = None
        self.devices = None
        self.rc_file = None

        if isinstance(configuration, dict):
            _ = configuration
            self.auth(_['client_id'], _['client_secret'], _['username'], _['password'])
            self.default_station = _['device'] if 'device' in _ else None
        elif isinstance(configuration, str):
            self.rc_file = configuration
        elif configuration is None:
            self.rc_file = DEFAULT_RC_FILE

        if self.rc_file:
            self.load_credentials()
            self.load_tokens()

    def auth(self, client_id, client_secret, username, password):
        """
            set credentials
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self._access_token = None

    def load_credentials(self):
        """
            load credentials from the configuration file
        """
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
            trace(1, "load credentials from", rc)
        try:
            self.auth(config['netatmo']['client_id'],
                      config['netatmo']['client_secret'],
                      config['netatmo']['username'],
                      config['netatmo']['password'])
            if config.has_option('netatmo', 'default_station'):
                self.default_station = config['netatmo']['default_station']
        except:
            self.auth(None, None, None, None)

    def save_credentials(self):
        """
            save credentials to the configuration file
        """
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        if not config.has_section('netatmo'):
            config.add_section('netatmo')
        config['netatmo']['client_id'] = str(self.client_id)
        config['netatmo']['client_secret'] = str(self.client_secret)
        config['netatmo']['username'] = str(self.username)
        config['netatmo']['password'] = str(self.password)
        if self.default_station is None:
            config.remove_option('netatmo', 'default_station')
        else:
            config['netatmo']['default_station'] = self.default_station
        config.remove_section('netatmo/tokens')
        with open(rc, "w") as f:
            config.write(f)
            trace(1, "save credentials to", rc)

    def load_tokens(self):
        """
            load the tokens from the configuration file
        """
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
            trace(1, "load tokens from", rc)
        try:
            c = config['netatmo/tokens']
            self._access_token = c['access_token']
            self._refresh_token = c['refresh_token']
            self._expiration = datetime.datetime.strptime(c['expiration'], "%Y-%m-%dT%H:%M:%S").timestamp()
        except:
            self._access_token = None

    def save_tokens(self):
        """
            save the tokens to the configuration file
        """
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        config['netatmo/tokens'] = {
            'access_token': self._access_token,
            'refresh_token': self._refresh_token,
            'expiration': datetime.datetime.fromtimestamp(int(self._expiration)).isoformat()
        }
        with open(rc, "w") as f:
            config.write(f)
            trace(1, "save tokens to", rc)

    @property
    def access_token(self):
        """
            refresh if necessary and return the access_token
        """
        if self.client_id is None or self.client_secret is None:
            return None

        if self._access_token is None:
            # We should authenticate

            if self.username is None or self.password is None:
                return None

            post_params = {
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": self.username,
                "password": self.password,
                "scope": "read_station"
            }
            resp = _post_request(_AUTH_REQ, post_params)
            if resp is None: return False
            if 'error' in resp:
                print("error", resp['error'], _AUTH_REQ)
                return None

            self._access_token = resp['access_token']
            self._refresh_token = resp['refresh_token']
            self._expiration = resp['expires_in'] + time.time()
            #self._scope = resp['scope']
            self.save_tokens()
            trace(1, _AUTH_REQ, post_params, resp)

        elif self._expiration <= time.time():
            # Token should be renewed

            post_params = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            resp = _post_request(_AUTH_REQ, post_params)
            if resp is None: return False
            if 'error' in resp:
                print("error", resp['error'], _AUTH_REQ)
                return None

            self._access_token = resp['access_token']
            self._refresh_token = resp['refresh_token']
            self._expiration = resp['expires_in'] + time.time()
            self.save_tokens()
            trace(1, _AUTH_REQ, post_params, resp)

        else:
            trace(2, "access_token still valid")

        return self._access_token


    def get_data(self, device_id=None):
        """
            retrieve data from netatmo server
        """
        auth_token = self.access_token
        if auth_token is None: return False

        post_params = {"access_token": auth_token, "get_favorites": False}

        if device_id is None:
            post_params["device_id"] = self.default_station
        elif device_id != '*':
            post_params["device_id"] = device_id

        resp = _post_request(_GETSTATIONSDATA_REQ, post_params)
        if resp is None: return False
        if 'error' in resp:
            print("error", resp['error'], _GETSTATIONSDATA_REQ)
            return False

        raw_data = resp['body']

        self.user = raw_data['user']
        self.devices = raw_data['devices']

        trace(1, "device count:", len(self.devices))

        return True


    def set_default_station(self, device):
        """
            set the default station by its MAC or name (requires connection)
        """
        if device == '':
            self.default_station = None
            return True

        # if we give a MAC address, do not search the station by its name
        if bool(re.match('^' + r'[\:\-]'.join(['([0-9a-f]{2})']*6) + '$', device.lower())):
            self.default_station = device.lower()
            return True

        self.get_data('*')
        i = self.station_by_name(device)
        if i:
            self.default_station = i['_id']
            return True
        else:
            return False

    def station_by_name(self, station=None):
        """
            return a station by its name or MAC if parameter is not None
            the default or the first is parameter is None
        """
        if self.devices is None: return None
        if not station: station = self.default_station
        for i in self.devices:
            if station == '' or station is None: return i
            if i['station_name'] == station: return i
            if i['_id'].lower() == station.lower(): return i
        return None

    def module_by_name(self, module, station=None):
        """
            return a module by its name or MAC
        """
        s = self.station_by_name(station)
        if s is None: return None
        if s['module_name'] == module: return s
        if s['_id'] == module: return s
        for mod in s['modules']:
            if mod['module_name'] == module: return mod
            if mod['_id'] == module: return mod
        return None

    def get_measure(self, device_id=None, scale='max', mtype='*', module_id=None,
                    date_begin=None, date_end=None, limit=None, optimize=False, real_time=False):
        """
            https://dev.netatmo.com/dev/resources/technical/reference/common/getmeasure
            Name              Required
            access_token      yes
            device_id         yes         70:ee:50:09:f0:xx
            module_id         yes         70:ee:50:09:f0:xx
            scale             yes         max
            type              yes         Temperature,Humidity
            date_begin        no          1459265427
            date_end          no          1459265487
            limit             no
            optimize          no
            real_time         no
        """
        auth_token = self.access_token
        if auth_token is None: return
        post_params = {"access_token": auth_token}

        if device_id is None:
            device_id = self.station_by_name()['_id']

        post_params['device_id'] = device_id
        if module_id: post_params['module_id'] = module_id
        post_params['scale'] = scale

        if mtype == '*':
            if module_id is None:
                mtype = self.station_by_name(device_id)['data_type']
            else:
                mtype = self.module_by_name(module_id, device_id)['data_type']
            mtype = ','.join(mtype)

        post_params['type'] = mtype
        if date_begin: post_params['date_begin'] = date_begin
        if date_end: post_params['date_end'] = date_end
        if limit: post_params['limit'] = limit
        post_params['optimize'] = "true" if optimize else "false"
        post_params['real_time'] = "true" if real_time else "false"
        return _post_request(_GETMEASURE_REQ, post_params)


def last_timestamp(filename):
    """
        find the most recent timestamp in a csv File
    """
    if not os.path.exists(filename):
        return 0
    with open(filename, "rb") as f:
        f.seek(0, os.SEEK_END)
        taille = min(f.tell(), 100)
        if taille != 0:
            f.seek(-taille, os.SEEK_END)
            last = f.readlines()[-1].decode('ascii')
            t = last[0:last.find(';')]
            if t.isnumeric():
                return int(t)
    return 0


def dl_csv(ws, csv_file, device_id, module_id, fields, date_end=None):
    """
        download measures from a module (or the main module of a station) to a csv file
    """

    start = last_timestamp(csv_file)
    if start > 0: start += 1

    csv_file = open(csv_file, "a")
    csv_writer = csv.writer(csv_file, delimiter=';', quotechar='"',
                            quoting=csv.QUOTE_NONNUMERIC, lineterminator='\n')

    if csv_file.tell() == 0:
        values = ["Timestamp", "DateTime"] + fields
        csv_writer.writerow(values)

    n = 0
    while True:
        n += 1
        print("getmeasure {} date_begin={} {}".format(n, start, time.ctime(start)))

        v = ws.get_measure(device_id, "max", ','.join(fields), module_id, date_begin=start)

        if not 'status' in v or v['status'] != 'ok':
            print("error", v)
            break

        if len(v['body']) == 0:
            #print("the end", v)
            break

        for _, (t, v) in enumerate(sorted(v['body'].items())):
            t = int(t)
            values = [t, datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")]
            values += v
            #print("{:2} {}".format(_, values))
            csv_writer.writerow(values)
            if start < t: start = t

        if start >= date_end:
            #print("last measure")
            break

        start += 1

    csv_file.close()


def fetch(rc_file_or_dict=None):
    """
        retrieve measures from station and append them to csv files

        rc_file the configuration file
    """
    ws = WeatherStation(rc_file_or_dict)
    if not ws.get_data(): return
    s = ws.station_by_name()
    m = s['modules'][0]
    print("station_name : {}".format(s['station_name']))
    print("device_id    : {}".format(s['_id']))
    print("module_name  : {}".format(s['module_name']))
    print("data_type    : {}".format(s['data_type']))
    print("module_id    : {}".format(m['_id']))
    print("module_name  : {}".format(m['module_name']))
    print("data_type    : {}".format(m['data_type']))

    data_type = ['Temperature', 'CO2', 'Humidity', 'Noise', 'Pressure']
    dl_csv(ws, "netatmo_station.csv", s['_id'], None, data_type, s['dashboard_data']['time_utc'])

    data_type = ['Temperature', 'Humidity']
    dl_csv(ws, "netatmo_module.csv", s['_id'], m['_id'], data_type, m['dashboard_data']['time_utc'])


def self_test(args):
    """
        check the connection
    """
    ws = WeatherStation(args.rc_file)
    ok = ws.get_data()
    if sys.stdout.isatty():
        if ok:
            print("netatmo.py %(mail)s : OK" % ws.user)
        else:
            print("netatmo.py : ERROR")
    exit(0 if ok else 1)


def fmtdate(t):
    """
        return the date to human readable format
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(t)))


def dump(args):
    """
        dump various data from the station
    """
    ws = WeatherStation(args.rc_file)
    if not ws.get_data('*'): return

    def dump1(values, is_module):
        """ utility print function """

        # from Netatmo-API-PHP/Examples/Utils.php
        device_types = {
            "NAModule1": "Outdoor",
            "NAModule2": "Wind Sensor",
            "NAModule3": "Rain Gauge",
            "NAModule4": "Indoor",
            "NAMain": "Main device"
        }

        if values is None: return
        try:
            print("module %s - %s" % (values['module_name'], device_types.get(values['type'], values['type'])))
            print("%20s : %s" % ('_id', values['_id']))
            print("%20s : %s" % ('data_type', values['data_type']))
            if is_module:
                print("%20s : %s - %s" % ('last_setup', values['last_setup'], fmtdate(values['last_setup'])))
                print("%20s : %s" % ('firmware', values['firmware']))
                print("%20s : %s (90=low, 60=highest)" % ('rf_status', values['rf_status']))
                print("%20s : %s %%" % ('battery_percent', values['battery_percent']))
                print("%20s : %s - %s" % ('last_message', values['last_message'], fmtdate(values['last_setup'])))
                print("%20s : %s - %s" % ('last_seen', values['last_seen'], fmtdate(values['last_setup'])))

            for sensor, value in sorted(values['dashboard_data'].items()):
                if sensor in values['data_type']:
                    continue
                if sensor.startswith("date_") or sensor.startswith("time_"):
                    print("%20s > %s - %s" % (sensor, value, fmtdate(value)))
                else:
                    print("%20s > %s" % (sensor, value))

            for sensor in sorted(values['data_type']):
                print("%20s = %s" % (sensor, values['dashboard_data'][sensor]))
        except:
            pprint.pprint(values)
            raise

    s = ws.station_by_name(args.device)

    if s is None: return

    #TODO
    #print("user %s" % (ws.user['mail']))
    #pprint.pprint(ws.user)

    print("station %s" % (s['station_name']))
    print("%20s : %s - %s" % ('date_setup', s['date_setup'], fmtdate(s['date_setup'])))
    print("%20s : %s - %s" % ('last_setup', s['last_setup'], fmtdate(s['last_setup'])))
    print("%20s : %s - %s" % ('last_upgrade', s['last_upgrade'], fmtdate(s['last_upgrade'])))
    print("%20s : %s %s / alt %s" % ('place', s['place']['city'], s['place']['country'], s['place']['altitude']))
    print("%20s : %s" % ('wifi_status', s['wifi_status']))
    print("%20s : %s - %s" % ('last_status_store', s['last_status_store'], fmtdate(s['last_status_store'])))

    dump1(s, False) # dumps the main module / the weatherstation
    for mod in s['modules']:
        dump1(mod, True) # dumps an attached module

    def dump2(name, v):
        """ utility print function """
        print("module", name)
        if not 'status' in v or v['status'] != 'ok':
            print(v)
        else:
            for i, (t, v) in enumerate(sorted(v['body'].items())):
                print("{:2} {} {} {}".format(i, t, fmtdate(t), v))

    half_hour = int(time.time()) - 1800

    measure = ws.get_measure(date_begin=half_hour, device_id=s['_id'])
    dump2(s['module_name'], measure)
    for mod in s['modules']:
        measure = ws.get_measure(date_begin=half_hour, device_id=s['_id'], module_id=mod['_id'])
        dump2(mod['module_name'], measure)


def list_stations(args):
    """
        list all stations
    """
    ws = WeatherStation(args.rc_file)
    ws.get_data('*')
    for i, d in enumerate(ws.devices):
        print(i + 1, "station", d['_id'], d['station_name'], d['place']['city'], d['place']['country'])
        for _, m in enumerate([d] + d['modules']):
            print("   module", m['_id'], m['module_name'], ','.join(m['data_type']))


def action_config(parser, args):
    """
        write or read the configuration file

        parser the argparse.ArgumentParser object
        args the dict with command-line parameters
    """
    ws = WeatherStation(args.rc_file)

    n = 0
    if not args.username is None: n += 1
    if not args.password is None: n += 1
    if not args.client_id is None: n += 1
    if not args.client_secret is None: n += 1

    if n >= 1 and n < 4:
        parser.print_help()
        exit(2)

    elif n == 4 or not args.device is None:
        ws.load_credentials()
        if n == 4:
            ws.auth(args.client_id, args.client_secret, args.username, args.password)
        if not args.device is None:
            ws.set_default_station(args.device)
        ws.save_credentials()

        print("Write config")
    else:
        print("Read config")

    ws.load_credentials()
    print("username:", ws.username)
    print("password:", ws.password)
    print("client_id:", ws.client_id)
    print("client_secret:", ws.client_secret)
    print("default_station:", ws.default_station)


class HelpFormatter40(argparse.HelpFormatter):
    """
        a help formatter for long options
    """
    def __init__(self, prog, indent_increment=2, max_help_position=24, width=None):
        super(HelpFormatter40, self).__init__(prog, indent_increment, 40)


def main():
    """
        main function
    """
    global verbosity

    parser = argparse.ArgumentParser(description='netatmo Python3 library',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-v", "--verbose", help="increase verbosity level", action="count", default=verbosity)
    parser.add_argument("-c", "--rc-file", help="configuration file", default=DEFAULT_RC_FILE, metavar="RC")

    subparsers = parser.add_subparsers(help='sub-commands', dest='action')

    sp1 = subparsers.add_parser("config", help="Set or show the credentials", formatter_class=HelpFormatter40)

    group1 = sp1.add_argument_group('Options to set credentials')
    group1.add_argument('-u', '--username', help="User address email", required=False)
    group1.add_argument('-p', '--password', help="User password", required=False)
    group1.add_argument('-i', '--client-id', help="Your app client_id", metavar='ID')
    group1.add_argument('-s', '--client-secret', help="Your app client_secret", metavar='SECRET')

    group2 = sp1.add_argument_group('Option to set the default device')
    group2.add_argument('-d', '--device', help="device id or station name", required=False)

    subparsers.add_parser("fetch", help="fetch last measures into csv files")

    subparsers.add_parser("list", help="list waether stations")

    subparsers.add_parser("test", help="test the connection")

    sp2 = subparsers.add_parser("dump", help="get and display some measures")
    sp2.add_argument('-d', '--device', help="device id or station name", required=False)

    args = parser.parse_args()

    # set the verbose level as a global variable
    verbosity = args.verbose

    trace(1, str(args))

    if args.action == 'config':
        action_config(sp1, args)
    elif args.action == 'list':
        list_stations(args)
    elif args.action == 'fetch':
        fetch(args.rc_file)
    elif args.action == 'dump':
        dump(args)
    elif args.action == 'test':
        self_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

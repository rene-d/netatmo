#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:set ts=4 sw=4 et:

# rene, november 2016
    
# Python API for Netatmo Weather Station

# inspired by https://github.com/philippelt/netatmo-api-python

import json, time
import requests
import os
import argparse
import configparser
import csv
import datetime
import re
import pprint

verbosity = 0

DEFAULT_RC_FILE = "~/.netatmorc"


# Common definitions
_BASE_URL            = "https://api.netatmo.com/"
_AUTH_REQ            = _BASE_URL + "oauth2/token"
_GETSTATIONSDATA_REQ = _BASE_URL + "api/getstationsdata"
_GETMEASURE_REQ      = _BASE_URL + "api/getmeasure"


def _postRequest(url, params):
    if verbosity >= 1:
        print(">>>> " + url)
        t = time.time()
    if verbosity >= 2:
        pprint.pprint(params)
    resp = requests.post(url, data=params)
    if verbosity >= 1:
        print("<<<< %d bytes in %.3f s" % (len(resp.content), time.time() - t))
    if verbosity >= 2:
        pprint.pprint(json.loads(resp.text))
        print()
    return json.loads(resp.text)


class WeatherStation:

    def __init__(self, configuration):
        
        self.auth(None, None, None, None)
        self.default_station = None
        self.devices = None
        self.rc_file = None

        if type(configuration) is dict:
            _ = configuration
            self.auth(_['client_id'], _['client_secret'], _['username'], _['password'])
            self.default_station = _['device'] if 'device' in _ else None
        elif type(configuration) is str:
            self.rc_file = configuration
        elif configuration is None:
            self.rc_file = DEFAULT_RC_FILE

        if self.rc_file:
            self.loadCredentials()
            self.loadTokens()

    def auth(self, client_id, client_secret, username, password, device_id=None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._access_token = None

    def loadCredentials(self):
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        try:
            self.auth(config['netatmo']['client_id'],
                      config['netatmo']['client_secret'],
                      config['netatmo']['username'],
                      config['netatmo']['password'])
            if config.has_option('netatmo', 'default_station'):
                self.default_station = config['netatmo']['default_station']
        except:
            self.auth(None, None, None, None)

    def saveCredentials(self):
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        if not config.has_section('netatmo'):
            config.add_section('netatmo')
        config['netatmo']['client_id'] = str(self._client_id)
        config['netatmo']['client_secret'] = str(self._client_secret)
        config['netatmo']['username'] = str(self._username)
        config['netatmo']['password'] = str(self._password)
        if self.default_station is None:
            config.remove_option('netatmo', 'default_station')
        else:
            config['netatmo']['default_station'] = self.default_station
        config.remove_section('netatmo/tokens')
        with open(rc, "w") as f:
            config.write(f)

    def loadTokens(self):
        if self.rc_file is None: return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        try:
            c = config['netatmo/tokens']
            self._access_token = c['access_token']
            self._refresh_token = c['refresh_token']
            self._expiration = datetime.datetime.strptime(c['expiration'], "%Y-%m-%dT%H:%M:%S").timestamp()
        except:
            self._access_token = None

    def saveTokens(self):
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

    @property
    def accessToken(self):
        if self._client_id is None or self._client_secret is None:
            return None

        if self._access_token is None:
            # We should authenticate

            if self._username is None or self._password is None:
                return None

            postParams = {
                    "grant_type": "password",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "username": self._username,
                    "password": self._password,
                    "scope": "read_station"
                    }

            resp = _postRequest(_AUTH_REQ, postParams)
            if  resp is None:
                return
            if 'error' in resp:
                print("error", resp['error'])
                return None

            self._access_token = resp['access_token']
            self._refresh_token = resp['refresh_token']
            self._expiration = resp['expires_in'] + time.time()
            #self._scope = resp['scope']
            self.saveTokens()
            if verbosity >= 1:
                print(_AUTH_REQ, postParams, resp)

        elif self._expiration <= time.time():
            # Token should be renewed

            postParams = {
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret
                    }
            resp = _postRequest(_AUTH_REQ, postParams)

            self._access_token = resp['access_token']
            self._refresh_token = resp['refresh_token']
            self._expiration = resp['expires_in'] + time.time()
            self.saveTokens()
            if verbosity >= 1:
                print(_AUTH_REQ, postParams, resp)

        return self._access_token


    def getData(self, device_id=None):
        authToken = self.accessToken
        if authToken is None: return False

        postParams = { "access_token": authToken, "get_favorites": False }

        if device_id is None:
            postParams["device_id"] = self.default_station
        elif device_id != '*':
            postParams["device_id"] = device_id

        resp = _postRequest(_GETSTATIONSDATA_REQ, postParams)
        #TODO
        rawData = resp['body']

        self.user = rawData['user']
        self.devices = rawData['devices']
        #if self.default_station is None: self.default_station = self.devices[0]['_id']
        return True

    def setDefaultStation(self, device):
        if device == '':
            self.default_station = None
            return True

        if bool(re.match('^' + '[\:\-]'.join(['([0-9a-f]{2})']*6) + '$', device.lower())):
            self.default_station = device.lower()
            return True

        self.getData('*')
        i = self.stationByName(device)
        if i:
            self.default_station = i['_id']
            return True
        else:
            return False

    def stationByName(self, station=None):
        if self.devices is None: return None
        if not station: station = self.default_station
        for i in self.devices:
            if station == '' or station is None: return i
            if i['station_name'] == station: return i
            if i['_id'].lower() == station.lower(): return i
        return None

    def moduleByName(self, module, station=None):
        s = self.stationByName(station)
        if s is None: return None
        if s['module_name'] == module: return s
        if s['_id'] == module: return s
        for mod in s['modules']:
            if mod['module_name'] == module: return mod
            if mod['_id'] == module: return mod
        return None

    # https://dev.netatmo.com/dev/resources/technical/reference/common/getmeasure
    # Name              Required
    # access_token      yes
    # device_id         yes         70:ee:50:09:f0:xx
    # module_id         yes         70:ee:50:09:f0:xx
    # scale             yes         max
    # type              yes         Temperature,Humidity
    # date_begin        no          1459265427
    # date_end          no          1459265487
    # limit             no
    # optimize          no
    # real_time         no
    #
    def getMeasure(self, device_id=None, scale='max', mtype='*', module_id=None, date_begin=None, date_end=None, limit=None, optimize=False, real_time=False):
        authToken = self.accessToken
        if authToken is None: return
        postParams = { "access_token": authToken }

        if device_id is None:
            device_id = self.stationByName()['_id']

        postParams['device_id'] = device_id
        if module_id: postParams['module_id'] = module_id
        postParams['scale'] = scale

        if mtype == '*':
            if module_id is None:
                mtype = self.stationByName(device_id)['data_type']
            else:
                mtype = self.moduleByName(module_id, device_id)['data_type']
            mtype = ','.join(mtype)

        postParams['type'] = mtype
        if date_begin: postParams['date_begin'] = date_begin
        if date_end: postParams['date_end'] = date_end
        if limit: postParams['limit'] = limit
        postParams['optimize'] = "true" if optimize else "false"
        postParams['real_time'] = "true" if real_time else "false"
        return _postRequest(_GETMEASURE_REQ, postParams)


def last_timestamp(filename):
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


##
# @brief download measures from a module (or the main module of a station)
#
# @param ws WeatherStation object
# @param filename csv filename
# @param device_id
# @param module_id
# @param fields
# @param date_end
#
# @return 
def dl_csv(ws, filename, device_id, module_id, fields, date_end=None):

    start = last_timestamp(filename)
    if start > 0: start += 1

    csv_file = open(filename, "a")
    csv_writer = csv.writer(csv_file, delimiter=';', quotechar='"',
                            quoting=csv.QUOTE_NONNUMERIC, lineterminator='\n')

    if csv_file.tell() == 0:
        values = [ "Timestamp", "DateTime" ] + fields
        csv_writer.writerow(values)

    n = 0
    while True:
        n += 1
        print("getmeasure {} date_begin={} {}".format(n, start, time.ctime(start)))

        v = ws.getMeasure(device_id, "max", ','.join(fields), module_id, date_begin=start)

        if not 'status' in v or v['status'] != 'ok':
            print("error", v)
            break

        if len(v['body']) == 0:
            #print("the end", v)
            break

        for i, (t, v) in enumerate(sorted(v['body'].items())):
            t = int(t)
            values = [ t, datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") ]
            values += v
            #print("{:2} {}".format(i, values))
            csv_writer.writerow(values)
            if start < t: start = t

        if start >= date_end:
            #print("last measure")
            break

        start += 1

    csv_file.close()


##
# @brief retrieve measures from station and append them to csv files
#
# @param rc_file the configuration file
#
# @return 
def fetch(rc_file_or_dict=None):
    ws = WeatherStation(rc_file_or_dict)
    if not ws.getData(): return
    s = ws.stationByName()
    m = s['modules'][0]
    print("station_name : {}".format(s['station_name']))
    print("device_id    : {}".format(s['_id']))
    print("module_name  : {}".format(s['module_name']))
    print("data_type    : {}".format(s['data_type']))
    print("module_id    : {}".format(m['_id']))
    print("module_name  : {}".format(m['module_name']))
    print("data_type    : {}".format(m['data_type']))

    data_type = ['Temperature', 'CO2', 'Humidity', 'Noise', 'Pressure']
    dl_csv(ws, "netatmo_station.csv", s['_id'], None, data_type,  s['dashboard_data']['time_utc'])

    data_type = ['Temperature', 'Humidity']        
    dl_csv(ws, "netatmo_module.csv", s['_id'], m['_id'], data_type, m['dashboard_data']['time_utc'])


def self_test(args):
    from sys import stdout
    ws = WeatherStation(args.rc_file)
    ok = ws.getData()
    if stdout.isatty():
        if ok:
            print("netatmo.py %(mail)s : OK" % ws.user)
        else:
            print("netatmo.py : ERROR")
    exit(0 if ok else 1)


def dump(args):
    ws = WeatherStation(args.rc_file)
    if not ws.getData(): return

    def dump1(values):
        print("module %s" % (values['module_name']))
        print("%20s : %s" % ('_id', values['_id']))
        print("%20s : %s" % ('data_type', values['data_type']))

        for sensor, value in sorted(values['dashboard_data'].items()):
            if sensor in values['data_type']:
                continue
            if sensor.startswith("date_") or sensor.startswith("time_"):
                print("%20s : %s - %s" % (sensor, value, time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime(int(value)))))
            else:
                print("%20s : %s" % (sensor, value))

        for sensor in sorted(values['data_type']):
            print("%20s = %s" % (sensor, values['dashboard_data'][sensor]))

    s = ws.stationByName()
    dump1(s)
    for mod in s['modules']:
        dump1(mod)

    def dump2(name, v):
        print("module", name)
        if not 'status' in v or v['status'] != 'ok':
            print(v)
        else:
            for i, (t, v) in enumerate(sorted(v['body'].items())):
                print("{:2} {} {} {}".format(i, t,
                    datetime.datetime.fromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M:%S"), v))

    half_hour = int(time.time()) - 1800

    measure = ws.getMeasure(date_begin=half_hour, device_id=s['_id'])
    dump2(s['module_name'], measure)
    for mod in s['modules']:
        measure = ws.getMeasure(date_begin=half_hour, device_id=s['_id'], module_id=mod['_id'])
        dump2(mod['module_name'], measure)


def list_stations(args):
    ws = WeatherStation(args.rc_file)
    ws.getData('*')
    for i, d in enumerate(ws.devices):
        print(i + 1, "station", d['_id'], d['station_name'], d['place']['city'], d['place']['country'])
        for j, m in enumerate([d] + d['modules']):
            print("   module", m['_id'], m['module_name'], ','.join(m['data_type']))


##
# @brief write or read the configuration file
#
# @param parser the argparse.ArgumentParser object
# @param args the dict with command-line parameters
#
# @return 
def action_config(parser, args):
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
        ws.loadCredentials()
        if n == 4:
            ws.auth(args.client_id, args.client_secret, args.username, args.password)
        if not args.device is None:
            ws.setDefaultStation(args.device)
        ws.saveCredentials()

        print("Write config")
    else:
        print("Read config")

    ws.loadCredentials()
    print("username:", ws._username)
    print("password:", ws._password)
    print("client_id:", ws._client_id)
    print("client_secret:", ws._client_secret)
    print("default_station:", ws.default_station)


##
# @brief a help formatter for long options
class HelpFormatter40(argparse.HelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=24, width=None):
        super(HelpFormatter40, self).__init__(prog, indent_increment, 40)


def main():
    global verbosity

    parser = argparse.ArgumentParser(description='netatmo Python3 library', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

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

    subparsers.add_parser("dump", help="get and display some measures")

    args = parser.parse_args()
    #print(args)

    verbosity = args.verbose

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

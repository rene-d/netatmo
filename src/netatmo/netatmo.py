#! /usr/bin/env python3
# rene, 2016-2019

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
import pkg_resources


VERBOSITY = 0

DEFAULT_RC_FILE = "~/.netatmorc"


# Common definitions
_BASE_URL = "https://api.netatmo.com/"
_AUTH_REQ = _BASE_URL + "oauth2/token"
_GETSTATIONSDATA_REQ = _BASE_URL + "api/getstationsdata"
_GETMEASURE_REQ = _BASE_URL + "api/getmeasure"


class Colors:
    """
    ANSI SGR codes
    https://en.wikipedia.org/wiki/ANSI_escape_code#graphics
    """

    Reset = "\033[0m"  # Reset / Normal
    Bold = "\033[1m"  # Bold or increased intensity
    Faint = "\033[2m"  # Faint (decreased intensity)
    Underline = "\033[4m"  # Underline: Single
    Blink = "\033[5m"  # Blink: Slow
    Inverse = "\033[7m"  # Image: Negative
    Black = "\033[0;30m"
    Red = "\033[0;31m"
    Green = "\033[0;32m"
    Yellow = "\033[0;33m"
    Blue = "\033[0;34m"
    Magenta = "\033[0;35m"
    Cyan = "\033[0;36m"
    LightGray = "\033[0;37m"
    DarkGray = "\033[1;30m"
    LightRed = "\033[1;31m"
    LightGreen = "\033[1;32m"
    LightYellow = "\033[1;33m"
    LightBlue = "\033[1;34m"
    LightMagenta = "\033[1;35m"
    LightCyan = "\033[1;36m"
    White = "\033[1;37m"


if not sys.stdout.isatty():
    for _ in dir(Colors):
        if not _.startswith("__"):
            setattr(Colors, _, "")


def trace(level, *args, pretty=False):
    """ print a colorized message when stdout is a terminal """
    if level <= VERBOSITY:
        pretty = pprint.pformat if pretty else str
        color_codes = {
            -2: Colors.LightRed,
            -1: Colors.LightYellow,
            0: "",
            1: Colors.Green,
            2: Colors.Yellow,
            3: Colors.Red,
        }
        color = color_codes.get(level, "")
        sys.stdout.write(color)
        for i, arg in enumerate(args):
            if i != 0:
                sys.stdout.write(" ")
            sys.stdout.write(pretty(arg))
        sys.stdout.write(Colors.Reset)
        sys.stdout.write("\n")


def post_request(url, params):
    """
    wrapper to the GET request
    """
    trace(1, ">>>> " + url)
    trace(2, params, pretty=True)
    start_time = time.time()
    resp = requests.post(url, data=params)
    trace(1, "<<<< %d bytes in %.3f s" % (len(resp.content), time.time() - start_time))
    ret = json.loads(resp.content)
    trace(2, ret, pretty=True)
    return ret


class WeatherStation:
    """
    class to access data
    """

    def __init__(self, configuration=None):
        self._access_token = None
        self._refresh_token = None
        self._expiration = None

        self.auth(None, None, None, None)
        self.default_device_id = None
        self.user = None
        self.devices = None
        self.rc_file = None

        if isinstance(configuration, dict):
            _ = configuration
            self.auth(_["client_id"], _["client_secret"], _["username"], _["password"])
            self.default_device_id = _["device"] if "device" in _ else None

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
        if self.rc_file is None:
            return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
            trace(1, "load credentials from", rc)
        try:
            self.auth(
                config["netatmo"]["client_id"],
                config["netatmo"]["client_secret"],
                config["netatmo"]["username"],
                config["netatmo"]["password"],
            )
            if config.has_option("netatmo", "default_device_id"):
                self.default_device_id = config["netatmo"]["default_device_id"]
        except:
            self.auth(None, None, None, None)

    def save_credentials(self):
        """
        save credentials to the configuration file
        """
        if self.rc_file is None:
            return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        if not config.has_section("netatmo"):
            config.add_section("netatmo")
        config["netatmo"]["client_id"] = str(self.client_id)
        config["netatmo"]["client_secret"] = str(self.client_secret)
        config["netatmo"]["username"] = str(self.username)
        config["netatmo"]["password"] = str(self.password)
        if self.default_device_id is None:
            config.remove_option("netatmo", "default_device_id")
        else:
            config["netatmo"]["default_device_id"] = self.default_device_id
        config.remove_section("netatmo/tokens")
        try:
            os.umask(0o077)
        except:
            pas
        with open(rc, "w") as file_handle:
            config.write(file_handle)
            trace(1, "save credentials to", rc)

    def load_tokens(self):
        """
        load the tokens from the configuration file
        """
        if self.rc_file is None:
            return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
            trace(1, "load tokens from", rc)
        try:
            tokens = config["netatmo/tokens"]
            self._access_token = tokens["access_token"]
            self._refresh_token = tokens["refresh_token"]
            self._expiration = datetime.datetime.strptime(
                tokens["expiration"], "%Y-%m-%dT%H:%M:%S"
            ).timestamp()
        except:
            self._access_token = None

    def save_tokens(self):
        """
        save the tokens to the configuration file
        """
        if self.rc_file is None:
            return
        config = configparser.ConfigParser()
        rc = os.path.expanduser(self.rc_file)
        if os.path.exists(rc):
            config.read(rc)
        config["netatmo/tokens"] = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expiration": datetime.datetime.fromtimestamp(
                int(self._expiration)
            ).isoformat(),
        }
        with open(rc, "w") as file_handle:
            config.write(file_handle)
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
                "scope": "read_station",
            }
            resp = post_request(_AUTH_REQ, post_params)
            if resp is None:
                return False
            if "error" in resp:
                print("error", resp["error"], _AUTH_REQ)
                return None

            self._access_token = resp["access_token"]
            self._refresh_token = resp["refresh_token"]
            self._expiration = resp["expires_in"] + time.time()
            # self._scope = resp['scope']
            self.save_tokens()
            trace(1, _AUTH_REQ, post_params, resp)

        elif self._expiration <= time.time():
            # Token should be renewed

            post_params = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
            resp = post_request(_AUTH_REQ, post_params)
            if resp is None:
                return False
            if "error" in resp:
                print("error", resp["error"], _AUTH_REQ)
                return None

            self._access_token = resp["access_token"]
            self._refresh_token = resp["refresh_token"]
            self._expiration = resp["expires_in"] + time.time()
            self.save_tokens()
            trace(1, _AUTH_REQ, post_params, resp)

        else:
            trace(2, "access_token still valid")

        return self._access_token

    def get_data(self, device_id=None):
        """
        retrieve data from netatmo server for one or all devices
        """
        auth_token = self.access_token
        if auth_token is None:
            return False

        post_params = {"access_token": auth_token, "get_favorites": False}

        if device_id is None or device_id == "*":
            post_params["device_id"] = self.default_device_id
        else:
            post_params["device_id"] = device_id

        resp = post_request(_GETSTATIONSDATA_REQ, post_params)
        if resp is None:
            return False
        if "error" in resp:
            print("error", resp["error"], _GETSTATIONSDATA_REQ)
            return False

        raw_data = resp["body"]

        self.user = raw_data["user"]
        self.devices = raw_data["devices"]

        trace(1, "device count:", len(self.devices))

        return True

    def set_default_station(self, device):
        """
        set the default station by its MAC address or name (requires connection in this case)
        """
        if device == "":
            self.default_device_id = None
            return True

        # if we have a MAC address, do not search the station by its name
        if bool(
            re.match("^" + r"[\:\-]".join(["([0-9a-f]{2})"] * 6) + "$", device.lower())
        ):
            self.default_device_id = device.lower()
            return True

        self.get_data("*")
        station = self.station_by_name(device)
        if station:
            self.default_device_id = station["_id"]
            return True
        else:
            return False

    def station_by_name(self, station_name=None):
        """
        return a station by its name or MAC if parameter is not None
        the default or the first is parameter is None
        """
        if self.devices is None:
            return None
        if not station_name:
            station_name = self.default_device_id
        for device in self.devices:
            if station_name == "" or station_name is None:
                return device
            if device["station_name"] == station_name:
                return device
            if device["_id"].lower() == station_name.lower():
                return device
        return None

    def module_by_name(self, module, station_name=None):
        """
        return a module by its name or MAC
        """
        station = self.station_by_name(station_name)
        if station is None:
            return None
        if station["module_name"] == module:
            return station
        if station["_id"] == module:
            return station
        for mod in station["modules"]:
            if mod["module_name"] == module:
                return mod
            if mod["_id"] == module:
                return mod
        return None

    def get_measure(
        self,
        device_id=None,
        scale="max",
        mtype="*",
        module_id=None,
        date_begin=None,
        date_end=None,
        limit=None,
        optimize=False,
        real_time=False,
    ):
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
        if auth_token is None:
            return
        post_params = {"access_token": auth_token}

        if device_id is None:
            device_id = self.station_by_name()["_id"]

        post_params["device_id"] = device_id
        if module_id:
            post_params["module_id"] = module_id
        post_params["scale"] = scale

        if mtype == "*":
            if module_id is None:
                mtype = self.station_by_name(device_id)["data_type"]
            else:
                mtype = self.module_by_name(module_id, device_id)["data_type"]
            mtype = ",".join(mtype)

        post_params["type"] = mtype
        if date_begin:
            post_params["date_begin"] = date_begin
        if date_end:
            post_params["date_end"] = date_end
        if limit:
            post_params["limit"] = limit
        post_params["optimize"] = "true" if optimize else "false"
        post_params["real_time"] = "true" if real_time else "false"
        return post_request(_GETMEASURE_REQ, post_params)


def last_timestamp(filename):
    """
    find the most recent timestamp in a csv File
    """
    if not os.path.exists(filename):
        return 0
    with open(filename, "rb") as file_handle:
        file_handle.seek(0, os.SEEK_END)
        taille = min(file_handle.tell(), 100)
        if taille != 0:
            file_handle.seek(-taille, os.SEEK_END)
            last = file_handle.readlines()[-1].decode("ascii")
            # timestamp is the first field
            timestamp = last[0 : last.find(";")]
            if timestamp.isnumeric():
                return int(timestamp)
    return 0


def dl_csv(ws, csv_file, device_id, module_id, fields, date_end=None):
    """
    download measures from a module (or the main module of a station) to a csv file
    """

    start = last_timestamp(csv_file)
    if start > 0:
        start += 1

    csv_file = open(csv_file, "a")
    csv_writer = csv.writer(
        csv_file,
        delimiter=";",
        quotechar='"',
        quoting=csv.QUOTE_NONNUMERIC,
        lineterminator="\n",
    )

    if csv_file.tell() == 0:
        values = ["Timestamp", "DateTime"] + fields
        csv_writer.writerow(values)

    n = 0
    while True:
        n += 1
        print("getmeasure {} date_begin={} {}".format(n, start, time.ctime(start)))

        measures = ws.get_measure(
            device_id, "max", ",".join(fields), module_id, date_begin=start
        )

        if "status" not in measures or measures["status"] != "ok":
            print("error", measures)
            break

        if len(measures["body"]) == 0:
            break

        for _, (timestamp, value) in enumerate(sorted(measures["body"].items())):
            timestamp = int(timestamp)
            values = [
                timestamp,
                datetime.datetime.fromtimestamp(timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ]
            values += value

            csv_writer.writerow(values)
            if start < timestamp:
                start = timestamp

        if start >= date_end:
            break

        start += 1

    csv_file.close()


def fetch(rc_file_or_dict=None):
    """
    retrieve measures from station and append them to csv files

    rc_file the configuration file
    """
    ws = WeatherStation(rc_file_or_dict)
    if not ws.get_data():
        return
    station = ws.station_by_name()
    module = station["modules"][0]
    print("station_name : {}".format(station["station_name"]))
    print("device_id    : {}".format(station["_id"]))
    print("module_name  : {}".format(station["module_name"]))
    print("data_type    : {}".format(station["data_type"]))
    print("module_id    : {}".format(module["_id"]))
    print("module_name  : {}".format(module["module_name"]))
    print("data_type    : {}".format(module["data_type"]))

    data_type = ["Temperature", "CO2", "Humidity", "Noise", "Pressure"]
    dl_csv(
        ws,
        "netatmo_station.csv",
        station["_id"],
        None,
        data_type,
        station["dashboard_data"]["time_utc"],
    )

    try:
        data_type = ["Temperature", "Humidity"]
        dl_csv(
            ws,
            "netatmo_module.csv",
            station["_id"],
            module["_id"],
            data_type,
            module["dashboard_data"]["time_utc"],
        )
    except KeyError:
        pass

    n_module = len(station["modules"])
    if n_module > 1:
        for i in range(1, n_module):
            module = station["modules"][i]
            print("station_name : {}".format(station["station_name"]))
            print("device_id    : {}".format(station["_id"]))
            print("module_name  : {}".format(station["module_name"]))
            print("data_type    : {}".format(station["data_type"]))
            print("module_id    : {}".format(module["_id"]))
            print("module_name  : {}".format(module["module_name"]))
            print("data_type    : {}".format(module["data_type"]))
            try:
                data_type = ["Temperature", "CO2", "Humidity"]
                dl_csv(
                    ws,
                    f"netatmo_module_in_{i}.csv",
                    station["_id"],
                    module["_id"],
                    data_type,
                    module["dashboard_data"]["time_utc"],
                )
            except KeyError:
                pass


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


def fmtdate(timestamp):
    """
    return the date to human readable format
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(timestamp)))


def dump(args):
    """
    dump various data from the station
    """
    ws = WeatherStation(args.rc_file)
    if not ws.get_data("*"):
        return

    def dump1(values, is_module):
        """ utility print function """

        # from Netatmo-API-PHP/Examples/Utils.php
        device_types = {
            "NAModule1": "Outdoor",
            "NAModule2": "Wind Sensor",
            "NAModule3": "Rain Gauge",
            "NAModule4": "Indoor",
            "NAMain": "Main device",
        }

        if values is None:
            return

        try:
            print(
                "module %s - %s"
                % (
                    values["module_name"],
                    device_types.get(values["type"], values["type"]),
                )
            )
            print("%20s : %s" % ("_id", values["_id"]))
            print("%20s : %s" % ("data_type", values["data_type"]))

            if is_module:
                print(
                    "%20s : %s - %s"
                    % (
                        "last_setup",
                        values["last_setup"],
                        fmtdate(values["last_setup"]),
                    )
                )
                print("%20s : %s" % ("firmware", values["firmware"]))
                print(
                    "%20s : %s (90=low, 60=highest)"
                    % ("rf_status", values["rf_status"])
                )
                print("%20s : %s %%" % ("battery_percent", values["battery_percent"]))
                print(
                    "%20s : %s - %s"
                    % (
                        "last_message",
                        values["last_message"],
                        fmtdate(values["last_setup"]),
                    )
                )
                print(
                    "%20s : %s - %s"
                    % ("last_seen", values["last_seen"], fmtdate(values["last_setup"]))
                )

            for sensor, value in sorted(values["dashboard_data"].items()):
                if sensor in values["data_type"]:
                    continue
                if sensor.startswith("date_") or sensor.startswith("time_"):
                    print("%20s > %s - %s" % (sensor, value, fmtdate(value)))
                else:
                    print("%20s > %s" % (sensor, value))

            for sensor in sorted(values["data_type"]):
                if sensor in values["dashboard_data"]:
                    print("%20s = %s" % (sensor, values["dashboard_data"][sensor]))
        except:
            pprint.pprint(values)
            raise

    station = ws.station_by_name(args.device)

    if station is None:
        return

    # TODO
    # print("user %s" % (ws.user['mail']))
    # pprint.pprint(ws.user)

    print("station %s" % (station["station_name"]))
    print(
        "%20s : %s - %s"
        % ("date_setup", station["date_setup"], fmtdate(station["date_setup"]))
    )
    if "last_setup" in station:
        print(
            "%20s : %s - %s"
            % ("last_setup", station["last_setup"], fmtdate(station["last_setup"]))
        )
    if "last_upgrade" in station:
        print(
            "%20s : %s - %s"
            % (
                "last_upgrade",
                station["last_upgrade"],
                fmtdate(station["last_upgrade"]),
            )
        )
    print(
        "%20s : %s %s / alt %s"
        % (
            "place",
            station["place"]["city"],
            station["place"]["country"],
            station["place"]["altitude"],
        )
    )
    print("%20s : %s" % ("wifi_status", station["wifi_status"]))
    print(
        "%20s : %s - %s"
        % (
            "last_status_store",
            station["last_status_store"],
            fmtdate(station["last_status_store"]),
        )
    )

    dump1(station, False)  # dumps the main module / the weatherstation
    for mod in station["modules"]:
        dump1(mod, True)  # dumps an attached module

    def dump2(name, measures):
        """ utility print function """
        print("module", name)
        if "status" not in measures or measures["status"] != "ok":
            print(measures)
        else:
            for i, (timestamp, values) in enumerate(sorted(measures["body"].items())):
                print("{:2} {} {} {}".format(i, timestamp, fmtdate(timestamp), values))

    half_hour = int(time.time()) - 1800

    measures = ws.get_measure(date_begin=half_hour, device_id=station["_id"])
    dump2(station["module_name"], measures)
    for mod in station["modules"]:
        measures = ws.get_measure(
            date_begin=half_hour, device_id=station["_id"], module_id=mod["_id"]
        )
        dump2(mod["module_name"], measures)


def list_stations(args):
    """
    list all stations
    """
    ws = WeatherStation(args.rc_file)
    ws.get_data("*")
    for i, device in enumerate(ws.devices):
        print(
            i + 1,
            "station",
            device["_id"],
            device["station_name"],
            device["place"]["city"],
            device["place"]["country"],
        )
        for _, module in enumerate([device] + device["modules"]):
            print(
                "   module",
                module["_id"],
                module["module_name"],
                ",".join(module["data_type"]),
            )


def action_config(args):
    """
    write or read the configuration file

    parser the argparse.ArgumentParser object
    args the dict with command-line parameters
    """
    ws = WeatherStation(args.rc_file)

    n = 0
    if args.username is not None:
        n += 1
    if args.password is not None:
        n += 1
    if args.client_id is not None:
        n += 1
    if args.client_secret is not None:
        n += 1

    if n >= 1 and n < 4:
        args.parser.print_help()
        exit(2)

    elif n == 4 or args.device is not None:
        ws.load_credentials()
        if n == 4:
            ws.auth(args.client_id, args.client_secret, args.username, args.password)
        if args.device is not None:
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
    print("default_device_id:", ws.default_device_id)


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
    global VERBOSITY

    parser = argparse.ArgumentParser(
        description="netatmo Python3 library",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--version", help="show version", action="store_true")
    parser.add_argument(
        "-v",
        "--verbose",
        help="increase VERBOSITY level",
        action="count",
        default=VERBOSITY,
    )
    parser.add_argument(
        "-c",
        "--rc-file",
        help="configuration file",
        default=DEFAULT_RC_FILE,
        metavar="RC",
    )

    subparsers = parser.add_subparsers(help="sub-commands", dest="action")

    # action "config"
    sp = subparsers.add_parser(
        "config", help="Set or show the credentials", formatter_class=HelpFormatter40
    )
    sp.set_defaults(parser=sp)
    sp.set_defaults(func=action_config)

    group1 = sp.add_argument_group("Options to set credentials")
    group1.add_argument("-u", "--username", help="User address email", required=False)
    group1.add_argument("-p", "--password", help="User password", required=False)
    group1.add_argument("-i", "--client-id", help="Your app client_id", metavar="ID")
    group1.add_argument(
        "-s", "--client-secret", help="Your app client_secret", metavar="SECRET"
    )

    group2 = sp.add_argument_group("Option to set the default device")
    group2.add_argument(
        "-d", "--device", help="device id or station name", required=False
    )

    # action "fetch"
    sp = subparsers.add_parser("fetch", help="fetch last measures into csv files")
    sp.set_defaults(func=lambda args: fetch(args.rc_file))

    # action "list"
    subparsers.add_parser("list", help="list waether stations").set_defaults(
        func=list_stations
    )

    # action "test"
    subparsers.add_parser("test", help="test the connection").set_defaults(
        func=self_test
    )

    # action "dummp"
    sp = subparsers.add_parser("dump", help="get and display some measures")
    sp.add_argument("-d", "--device", help="device id or station name", required=False)
    sp.set_defaults(func=dump)

    args = parser.parse_args()

    if args.version:
        print(pkg_resources.require("netatmo")[0])
        exit(0)

    # set the verbose level as a global variable
    VERBOSITY = args.verbose

    trace(1, str(args))

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

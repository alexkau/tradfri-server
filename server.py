#!/usr/bin/env python3
#
# Server wrapper from https://gist.github.com/senko/4491981

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from subprocess import call
from pytradfri import Gateway
from pytradfri.api.libcoap_api import api_factory
from time import sleep
import configparser
import sys

class RequestHandler(BaseHTTPRequestHandler):
    key = None
    hubip = None

    BAD_REQUEST = -1
    SUCCESS = 0

    # these values are not double-checked
    # if any mistakes are made here, things might blow up in your face
    COLOR = 'color'
    SWITCH = 'switch'
    BRIGHTNESS = 'brightness'

    # these values are the specific ones that the white spectrum tradfri bulbs use
    # they should not be changed, since the bulbs physically can't display other colors
    # i haven't tested the full-spectrum bulbs, but they should presumably support any color
    COLOR_TO_HEX_MAP = {
        'warm': 'efd275',
        'orange': 'efd275',
        'red': 'efd275',

        'normal': 'f1e0b5',
        'yellow': 'f1e0b5',

        'cool': 'f5faf6',
        'cold': 'f5faf6',
        'white': 'f5faf6',
        'blue': 'f5faf6'
    }
    COMMAND_PART_TYPE_TO_VALUES = {
        COLOR: list(COLOR_TO_HEX_MAP.keys()),
        SWITCH: ['on', 'off'],
        BRIGHTNESS: list(str(i) for i in range(101))
    }

    ZONES = ['living', 'living room', 'bathroom', 'bedroom', 'office']
    ZONE_ALIAS_MAP = {
        'living room': 'Living Room',
        'living': 'Living Room',
        'bedroom': 'Bedroom',
        'bathroom': 'Bathroom',
        'office': 'Office'
    }
    # ?[zone] [on|off]
    # ?[zone] [color]
    # ?[zone] [brightness]
    # ?[zone] [color] [brightness]
    # ?[zone] [brightness] [color]
    FORMATS = [
        [SWITCH],
        [COLOR],
        [BRIGHTNESS],
        [COLOR, BRIGHTNESS],
        [BRIGHTNESS, COLOR]
    ]

    # def __init__(self, request, client_address, server):
    #     BaseHTTPRequestHandler.__init__(self, request, client_address, server)
    #     # print("hub" + str(self.hubip))

    def init(self):
        if self.hubip is None:
            conf = configparser.ConfigParser()
            conf.read('tradfri.cfg')
            #print(conf)

            self.hubip = conf.get('tradfri', 'hubip')
            self.securityid = conf.get('tradfri', 'securityid')
            self.api = api_factory(self.hubip, self.securityid)
            self.gateway = Gateway()

            groups_command = self.gateway.get_groups()
            groups_commands = self.api(groups_command)
            groups = self.api(*groups_commands)
            self.groups = dict((g.name, g) for g in groups)
            print(str(self.groups))

    def add_zone(self, zone_ids, inverted, new_zone):
        if inverted:
            zone_ids.remove(self.ZONE_ALIAS_MAP[new_zone])
        else:
            zone_ids.add(self.ZONE_ALIAS_MAP[new_zone])
        return zone_ids

    def _parse_request(self):
        #print("hub2" + self.hubip)
        self.init()

        parsed_req = urlparse(self.path)
        args = parse_qs(parsed_req.query)
        if self.headers.get('content-type', '') \
            == 'application/x-www-form-urlencoded':
                body = self.rfile.read(int(self.headers.get('content-length')))
                args = parse_qs(body)

        args = dict((k, v[0]) for k, v in args.items())
        return (parsed_req.path, args)

    def isvalid(self, cmd, format):
        for i in range(len(format)):
            part_type = format[i]
            part = cmd[i]
            for acceptable_value in self.COMMAND_PART_TYPE_TO_VALUES[part_type]:
                if part.lower() == acceptable_value.lower():
                    break
            else:
                print("invalid: " + str(cmd) + " against " + str(format))
                return False
        print("valid: " + str(cmd) + " against " + str(format))
        return True

    def run_command(self, zone_ids, cmd, format):
        print("cmd:" + str(cmd))
        print("format:" + str(format))

        # zones = list(self.ZONES)
        # if zone_ is not None:
        #     zones = [zone_]
        print("zone_ids: " + str(zone_ids))

        for i in range(len(format)):
            part_type = format[i]
            part = cmd[i].lower()
            #zone_ids = set(self.ZONE_ALIAS_MAP[zone] for zone in zones)
            #print("zone ids: " + str(zone_ids))
            #for zone in zones:
            for zone_id in zone_ids:
                #zone_id = self.ZONE_ALIAS_MAP[zone]
                if part_type == self.SWITCH:
                    # print('performing now')
                    # print('hub ip is ' + str(type(self.hubip)))
                    # print('key is ' + str(type(self.securityid)))
                    # print('zone id is ' + str(type(zone_id)))
                    # print('part is ' + str(type(part)))
                    self.api(self.groups[zone_id].set_state(1 if part == 'on' else 0))
                    # print('done')
                elif part_type == self.COLOR:
                    # need to do it per light...
                    for devcmd in self.groups[zone_id].members():
                        dev = self.api(devcmd)
                        print(str(dev) + ": " + str(dev.has_light_control))
                        if not dev.has_light_control:
                            continue
                        self.api(dev.light_control.set_hex_color(self.COLOR_TO_HEX_MAP[part]))
                    # self.groups[zone_id].set_hex_color(self.COLOR_TO_HEX_MAP[part])
                elif part_type == self.BRIGHTNESS:
                    rawval = int(float(part) * 2.55)
                    self.api(self.groups[zone_id].set_dimmer(rawval))
                    if rawval > 0:
                        self.api(self.groups[zone_id].set_state(1))
                        #sleep(0.2)
                #sleep(0.2)

        return self.SUCCESS

    def process(self, input):
        command = input.lower().split(' ')
        # print(str(command))
        zone_ids = set()
        inverted = False

        if len(command) == 0:
            return self.BAD_REQUEST

        if command[0] == 'except': # magic "invert" keyword
            zone_ids = set(self.ZONE_ALIAS_MAP.values())
            inverted = True
            command = command[1:]

        if len(command) >= 3 and command[0] + ' ' + command[1] in self.ZONES: # hacky support for two-word zone names
            #zones.append(command[0] + ' ' + command[1])
            self.add_zone(zone_ids, inverted, command[0] + ' ' + command[1])
            command = command[2:]

        if command[0] in self.ZONES:
            #zones.append(command[0])
            self.add_zone(zone_ids, inverted, command[0])
            command = command[1:]

        if len(command) == 0:
            return self.BAD_REQUEST
        
        if len(zone_ids) == 0:
            zone_ids = set(self.ZONE_ALIAS_MAP.values())

        for format in self.FORMATS:
            if len(format) == len(command) and self.isvalid(command, format):
                return self.run_command(zone_ids, command, format)
        return self.BAD_REQUEST

    # def do_POST(self):
    #     path, args = self._parse_request()
    #     self.do('POST', path, args)

    def do_GET(self):
        path, args = self._parse_request()
        self.do('GET', path, args)

    def do(self, method, path, args):
        if args.get('key') != RequestHandler.key or 'command' not in args:
            self.send_error(400, 'Bad Request')
            return

        retval = self.process(args['command'].strip())

        if retval == self.SUCCESS:
            self.send_response(200)
            self.end_headers()
        elif retval == self.BAD_REQUEST:
            self.send_error(400, 'Bad request')
        else:
            self.send_error(500, 'Trigger command failed')

def run(host, port, key):
    RequestHandler.key = key


    server = HTTPServer((host, port), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.stderr.write('Usage: %s <host> <port> <key> ...\n' %
            sys.argv[0])
        sys.exit(-1)
    run(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    sys.exit(0)


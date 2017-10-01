#!/usr/bin/env python3
#
# Server wrapper from https://gist.github.com/senko/4491981

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from subprocess import call
from tradfri import tradfriActions
import configparser
import sys

class RequestHandler(BaseHTTPRequestHandler):
    key = None

    BAD_REQUEST = -1
    SUCCESS = 0

    # these values are not double-checked
    # if any mistakes are made here, things might blow up in your face
    COLOR = 'color'
    SWITCH = 'switch'
    BRIGHTNESS = 'brightness'
    COMMAND_PART_TYPE_TO_VALUES = {
        COLOR: ['warm', 'normal', 'cold'],
        SWITCH: ['on', 'off'],
        BRIGHTNESS: []
    }

    ZONES = ['living', 'bathroom', 'bedroom']
    ZONE_ALIAS_MAP = {
        'living': 164818,
        'bedroom': 152118,
        'bathroom': 189890
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

    hubip = None
    securityid = None

    # def __init__(self, request, client_address, server):
    #     BaseHTTPRequestHandler.__init__(self, request, client_address, server)
    #     # print("hub" + str(self.hubip))


    def _parse_request(self):
        # print("hub2" + self.hubip)
        if self.hubip is None:
            conf = configparser.ConfigParser()
            conf.read('tradfri.cfg')

            self.hubip = conf.get('tradfri', 'hubip')
            self.securityid = conf.get('tradfri', 'securityid')


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
                if part == acceptable_value:
                    break
            else:
                # print("invalid: " + str(cmd) + " against " + str(format))
                return False
        # print("valid: " + str(cmd) + " against " + str(format))
        return True

    def run_command(self, zone_, cmd, format):
        print("cmd:" + str(cmd))
        print("format:" + str(format))

        zones = list(self.ZONES)
        if zone_ is not None:
            zones = [zone_]
        print("zones: " + str(zones))

        for i in range(len(format)):
            part_type = format[i]
            part = cmd[i]
            for zone in zones:
                zone_id = self.ZONE_ALIAS_MAP[zone]
                if part_type == self.SWITCH:
                    print('performing now')
                    print('hub ip is ' + str(type(self.hubip)))
                    print('key is ' + str(type(self.securityid)))
                    print('zone id is ' + str(type(zone_id)))
                    print('part is ' + str(type(part)))
                    print(tradfriActions.tradfri_power_group('192.168.1.53', 'IyP8N5zrhIGQgbqm', 164818, 'on'))
                    print('done')
                elif part_type == self.COLOR:
                    tradfriActions.tradfri_color_group(self.hubip, self.securityid, zone_id, part)
                elif part_type == self.BRIGHTNESS:
                    tradfriActions.tradfri_dim_group(self.hubip, self.securityid, zone_id, part)

        return self.SUCCESS

    def process(self, input):
        command = input.split(' ')
        # print(str(command))
        zone = None
        if len(command) == 0:
            return self.BAD_REQUEST
        if command[0] in self.ZONES:
            zone = command[0]
            command = command[1:]
        if len(command) == 0:
            return self.BAD_REQUEST
        
        for format in self.FORMATS:
            if len(format) == len(command) and self.isvalid(command, format):
                return self.run_command(zone, command, format)
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


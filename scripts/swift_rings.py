#!/usr/bin/env python
from __future__ import print_function
from optparse import OptionParser
from os.path import exists
from swift.cli.ringbuilder import main as rb_main

import sys
import threading
import pickle
import yaml

USAGE = "usage: %prog -s <swift setup yaml>"

DEFAULT_PART_POWER = 10
DEFAULT_REPL = 3
DEFAULT_MIN_PART_HOURS = 1
DEFAULT_HOST_MOUNTPOINT = '/srv/drive/'
DEFAULT_HOST_DRIVE = '/sdb'
DEFAULT_HOST_ZONE = 0
DEFAULT_HOST_WEIGHT = 1
DEFAULT_ACCOUNT_PORT = 6002
DEFAULT_CONTAINER_PORT = 6001
DEFAULT_OBJECT_PORT = 6000
DEFAULT_SECTION_PORT = {
    'account': DEFAULT_ACCOUNT_PORT,
    'container': DEFAULT_CONTAINER_PORT,
    'object': DEFAULT_OBJECT_PORT,
}

class RingValidationError(Exception):
    pass

def create_buildfile(build_file, part_power, repl, min_part_hours,
                     update=False, data=None):
    if update:
        # build file exists, so lets just update the existing build file
        if not data:
            data = get_build_file_data(build_file)
            if data is None:
                data = {}

        if repl != data.get('replicas') and not validate:
            run_and_wait(rb_main, ["swift-ring-builder", build_file,
                                   "set_replicas", repl])
        if min_part_hours != data.get('min_part_hours') and not validate:
            run_and_wait(rb_main, ["swift-ring-builder", build_file,
                                   "set_min_part_hours", min_part_hours])
        if part_power != data.get('part_power'):
            raise RingValidationError('Part power cannot be changed! '
                                      'you must rebuild the ring if you need '
                                      'to change it.\nRing part power: %s '
                                      'Inventory part power: %s'
                                      % (data.get('part_power'), part_power))
    else:
        run_and_wait(rb_main, ["swift-ring-builder", build_file, "create",
                     part_power, repl, min_part_hours])


def add_host_to_ring(build_file, host):
    host_str = ""
    if host.get('region') is not None:
        host_str += 'r%(region)d' % host
    host_str += "z%d" % (host.get('zone', DEFAULT_HOST_ZONE))
    ip = host.get('swift_ip', host['host'])
    host_str += "-%s:%d" % (ip, host['port'])
    if host.get('repl_port') or host.get('repl_ip'):
        r_ip = host.get('repl_ip', ip)
        r_port = host.get('repl_port', host['port'])
        host_str += "R%s:%d" % (r_ip, r_port)
    host_str += "/%(drive)s" % host

    weight = host.get('weight', DEFAULT_HOST_WEIGHT)
    run_and_wait(rb_main, ["swift-ring-builder", build_file, 'add',
                           host_str, str(weight)])


def run_and_wait(func, *args):
    t = threading.Thread(target=func, args=args)
    t.start()
    return t.join()


def has_section(conf, section):
    return True if conf.get(section) else False


def check_section(conf, section):
    if not has_section(conf, section):
        print("Section %s doesn't exist" % (section))
        sys.exit(2)

def get_build_file_data(build_file):
    build_file_data = None
    if exists(build_file):
        try:
            with open(build_file) as bf_stream:
                build_file_data = pickle.load(bf_stream)
        except Exception as ex:
            print("Error: failed to load build file '%s': %s" % (build_file,
                                                                 ex))
            build_file_data = None
    return build_file_data

def build_ring(section, conf, part_power, hosts):
    # Create the build file
    build_file = "%s.builder" % (section)
    build_file_data = get_build_file_data(build_file)
    update = build_file_data is not None

    repl = conf.get('repl_number', DEFAULT_REPL)
    min_part_hours = conf.get('min_part_hours',
                              DEFAULT_MIN_PART_HOURS)
    part_power = conf.get('part_power', part_power)
    create_buildfile(build_file, part_power, repl, min_part_hours, update,
                     data=build_file_data)

    # Add the hosts
    if not hosts:
        print("No hosts/drives assigned to the %s ring" % section)
        sys.exit(3)

    section_key = section.split('-')[0]
    service_port = conf.get('port', DEFAULT_SECTION_PORT[section_key])
    for host in conf['hosts']:
        port = host.get('port', service_port)
        if 'name' in host:
            if host['name'] not in hosts:
                print("Host %(name) reference not found." % host)
                sys.exit(3)
            host = hosts[host['name']]
            host['port'] = port
            add_host_to_ring(build_file, host)
        else:
            for drive in host['drives']:
                tmp_dict = host.copy()
                tmp_dict['drive'] = drive['name']
                tmp_dict.update(drive)
                del tmp_dict['name']
                if not tmp_dict.get('drive'):
                    tmp_dict['drive'] = DEFAULT_HOST_DRIVE
                tmp_dict['port'] = port
                add_host_to_ring(build_file, tmp_dict)

    # Rebalance ring
    run_and_wait(rb_main, ["swift-ring-builder", build_file, "rebalance"])
    # rb_main(("swift-ring-builder", build_file, "rebalance"))


def main(setup):
    # load the yaml file
    try:
        with open(setup) as yaml_stream:
            _swift = yaml.load(yaml_stream)
    except Exception as ex:
        print("Failed to load yaml string %s" % (ex))
        return 1

    _hosts = {}

    if _swift.get("hosts"):
        for host in _swift['hosts']:
            for drive in host['drives']:
                tmp_dict = host.copy()
                tmp_dict['drive'] = drive['name']
                tmp_dict.update(drive)
                del tmp_dict['name']
                if not tmp_dict.get('drive'):
                    tmp_dict['drive'] = DEFAULT_HOST_DRIVE
                key = "%(host)s/%(drive)s" % tmp_dict
                if key in _hosts:
                    print("%(host)s already definined" % host)
                    return 1
                _hosts[key] = tmp_dict

    check_section(_swift, 'swift')
    part_power = _swift['swift'].get('part_power', DEFAULT_PART_POWER)

    # Create account ring
    check_section(_swift, 'account')
    build_ring('account', _swift['account'], part_power, _hosts)

    # Create container ring
    check_section(_swift, 'container')
    build_ring('container', _swift['container'], part_power, _hosts)

    # Create object rings (storage policies)
    check_section(_swift, 'storage_policies')
    check_section(_swift['storage_policies'], 'policies')
    indexes = set()
    for sp in _swift['storage_policies']['policies']:
        if sp['index'] in indexes:
            print("Storage Policy index %d already in use" % (sp['index']))
            return 4
        if sp['index'] == 0:
            buildfilename = 'object'
        else:
            buildfilename = 'object-%d' % (sp['index'])
        indexes.add(sp['index'])
        if 'port' not in sp:
            sp['port'] = _swift['storage_policies'].get('port',
                                                        DEFAULT_OBJECT_PORT)
        build_ring(buildfilename, sp, part_power, _hosts)

if __name__ == "__main__":
    parser = OptionParser(USAGE)
    parser.add_option("-s", "--setup", dest="setup",
                      help="Specify the swift setup file.", metavar="FILE",
                      default="/etc/swift/swift_inventory.yml")

    options, args = parser.parse_args(sys.argv[1:])
    if options.setup and not exists(options.setup):
        print("Swift setup file not found or doesn't exist")
        parser.print_help()
        sys.exit(1)

    sys.exit(main(options.setup))

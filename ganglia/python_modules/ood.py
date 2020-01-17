from __future__ import division
import copy
import glob
import logging
import logging.handlers
from lxml import etree
import optparse
import psutil
import requests
import socket
import subprocess
import sys
import os
import time
import yaml

DESCRIPTION_SKELETON = {
    'name': 'XXX',
    'time_max': 60,
    'value_type': 'float', # (string, uint, float, double)
    'format': '%f', #String formatting ('%s', '%d','%f')
    'slope': 'both',
    'description': 'XXX',
    'units': 'XXX',
    'groups': 'OOD'
}
METRIC_PREFIX = 'ood_'

METRICS = [
    {'name': 'active_puns', 'description': 'Active PUNs', 'units': 'puns', 'value_type': 'uint', 'format': '%d'},
    {'name': 'rack_apps', 'description': 'Number of Rack Apps', 'units': 'apps', 'value_type': 'uint', 'format': '%d'},
    {'name': 'node_apps', 'description': 'Number of NodeJS Apps', 'units': 'apps', 'value_type': 'uint', 'format': '%d'},
    {'name': 'max_pun_cpu_time_user', 'description': 'Max user CPU time of a PUN', 'units': 'seconds'},
    {'name': 'avg_pun_cpu_time_user', 'description': 'Average user CPU time of a PUN', 'units': 'seconds'},
    {'name': 'max_pun_cpu_time_system', 'description': 'Max system CPU time of a PUN', 'units': 'seconds'},
    {'name': 'avg_pun_cpu_time_system', 'description': 'Average system CPU time of a PUN', 'units': 'seconds'},
    {'name': 'max_pun_cpu_percent', 'description': 'Max CPU percent used by a PUN', 'units': 'percent'},
    {'name': 'avg_pun_cpu_percent', 'description': 'Average CPU percent used by a PUN', 'units': 'percent'},
    {'name': 'max_pun_memory_rss', 'description': 'Max Memory RSS used by PUN', 'units': 'bytes'},
    {'name': 'avg_pun_memory_rss', 'description': 'Average Memory RSS used by PUN', 'units': 'bytes'},
    {'name': 'max_pun_memory_vms', 'description': 'Max Virtual Memory used by PUN', 'units': 'bytes'},
    {'name': 'avg_pun_memory_vms', 'description': 'Average Virtual Memory used by PUN', 'units': 'bytes'},
    {'name': 'max_pun_memory_percent', 'description': 'Max Memory percent used by PUN', 'units': 'percent'},
    {'name': 'avg_pun_memory_percent', 'description': 'Average Memory percent used by PUN', 'units': 'percent'},
    {'name': 'websocket_connections', 'description': 'Number of Websocket Connections', 'units': 'connections', 'value_type': 'uint', 'format': '%d'},
    {'name': 'unique_websocket_clients', 'description': 'Number of unique Websocket Clients', 'units': 'clients', 'value_type': 'uint', 'format': '%d'},
    {'name': 'client_connections', 'description': 'Number of client connections', 'units': 'connections', 'value_type': 'uint', 'format': '%d'},
    {'name': 'unique_client_connections', 'description': 'Number of unique client connections', 'units': 'connections', 'value_type': 'uint', 'format': '%d'},
]

log = None

class OOD(object):

    def __init__(self, min_poll_seconds):
        self.metrics = {}
        self.now_ts = -1
        self.last_ts = -1
        self.min_poll_seconds = int(min_poll_seconds)
        self.fqdn = socket.getfqdn()

    def should_update(self):
        return (self.now_ts == -1 or time.time() - self.now_ts  > self.min_poll_seconds)

    def servername(self):
        ood_portal = {}
        with open('/etc/ood/config/ood_portal.yml', 'r') as f:
            ood_portal = yaml.load(f)
        servername = ood_portal.get('servername', self.fqdn)
        port = ood_portal.get('port', '80')
        _servername = "%s:%s" % (servername, port)
        return _servername

    def get_value(self, name):
        if self.should_update():
            log.debug("UPDATING")
            self.last_ts = self.now_ts
            active_puns = self.get_nginx_stage_metrics()
            self.get_process_metrics(active_puns)
            self.get_apache_status_metrics()
            self.now_ts = int(time.time())
        n = name.split(METRIC_PREFIX)[-1]
        value = self.metrics[n]
        return value

    def get_nginx_stage_metrics(self):
        cmd = ['sudo', '/opt/ood/nginx_stage/sbin/nginx_stage', 'nginx_list']
        log.debug("Executing: %s" % ' '.join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        exit_code = proc.returncode
        if exit_code != 0:
            log.error('Exit code %s != 0' % exit_code)
            log.error('STDOUT: %s' % out)
            log.error('STDERR: %s' % err)
            return None
        log.debug('STDOUT: %s' % out)
        active_puns = []
        for line in out.splitlines():
            l = line.strip()
            active_puns.append(l)
        self.metrics['active_puns'] = len(active_puns)
        return active_puns

    def get_process_metrics(self, active_puns):
        pun_procs = {
            'pun_cpu_time_user': [0.0],
            'pun_cpu_time_system': [0.0],
            'pun_cpu_percent': [0.0],
            'pun_memory_rss': [0.0],
            'pun_memory_vms': [0.0],
            'pun_memory_percent': [0.0],
        }
        self.metrics['rack_apps'] = 0
        self.metrics['node_apps'] = 0
        psutil_version = psutil.version_info
        if psutil_version[0] >= 2:
            attrs = ['name','cmdline','username','cpu_percent','cpu_times','memory_info','memory_percent']
        else:
            attrs = ['name','cmdline','username','get_cpu_percent','get_cpu_times','get_memory_info','get_memory_percent']
        for proc in psutil.process_iter():
            p = proc.as_dict(attrs=attrs)
            log.debug(p)
            if p['username'] not in active_puns:
                continue
            cmd = ' '.join(p['cmdline'])
            if 'rack-loader.rb' in cmd:
                self.metrics['rack_apps'] += 1
            if 'Passenger NodeApp' in cmd:
                self.metrics['node_apps'] += 1
            pun_procs['pun_cpu_time_user'].append(p['cpu_times'].user)
            pun_procs['pun_cpu_time_system'].append(p['cpu_times'].system)
            pun_procs['pun_cpu_percent'].append(p['cpu_percent'])
            pun_procs['pun_memory_rss'].append(p['memory_info'].rss)
            pun_procs['pun_memory_vms'].append(p['memory_info'].vms)
            pun_procs['pun_memory_percent'].append(p['memory_percent'])
        for k,v in pun_procs.iteritems():
            max_value = max(v)
            avg_value = sum(v)/len(v)
            self.metrics['max_' + k] = max_value
            self.metrics['avg_' + k] = avg_value

    def get_apache_status_metrics(self):
        servername = self.servername()
        if ':443' in servername:
            url = "https://%s/server-status" % servername
        else:
            url = "http://%s/server-status" % servername
        page = requests.get(url)
        connections_table = None
        tables = etree.HTML(page.content).xpath("//table")
        for table in tables:
            rows = iter(table)
            headers = [col.text for col in next(rows)]
            if headers[0] == "Srv":
                log.debug("TABLE=%s", table)
                connections_table = table
                break
        if connections_table is None:
            log.warning("Unable to find connections table")
            return
        rows = iter(connections_table)
        headers = [col.text for col in next(rows)]
        log.debug("HEADERS: %s", headers)
        connections = []
        for row in rows:
            values = [col.text for col in row]
            log.debug("ROW: %s", values)
            connection = dict(zip(headers, values))
            connections.append(connection)
        log.debug(connections)
        self.metrics['websocket_connections'] = 0
        unique_websocket_clients = []
        self.metrics['client_connections'] = 0
        unique_client_connections = []
        for c in connections:
            request = c.get('Request', None)
            client = c.get('Client', None)
            if request is None or client is None:
                continue
            # Filter out connections not belonging to OOD
            if ('/node/' not in request and
                    '/rnode/' not in request and
                    '/pun/' not in request and
                    '/nginx/' not in request and
                    '/oidc' not in request and
                    '/discover' not in request and
                    '/register' not in request):
                log.debug("SKIP Request: %s", request)
                continue
            if '/node/' in request or '/rnode/' in request or 'websockify' in request:
                self.metrics['websocket_connections'] += 1
                if client not in unique_websocket_clients:
                    unique_websocket_clients.append(client)
            if client not in [self.fqdn, 'localhost', '127.0.0.1']:
                self.metrics['client_connections'] += 1
                if client not in unique_client_connections:
                    unique_client_connections.append(client)
        self.metrics['unique_websocket_clients'] = len(unique_websocket_clients)
        self.metrics['unique_client_connections'] = len(unique_client_connections)

def metric_init(params):
    descriptors = []
    if log is None:
        setup_logging('syslog', params['syslog_facility'], params['log_level'])
    ood = OOD(params['min_poll_seconds'])
    for metric in METRICS:
        d = copy.copy(DESCRIPTION_SKELETON)
        d.update(metric)
        d['name'] = METRIC_PREFIX + d['name']
        d['call_back'] = ood.get_value
        log.debug(d)
        descriptors.append(d)

    return descriptors


def metric_cleanup():
    '''Clean up the metric module.'''
    pass

def setup_logging(handlers, facility, level):
    global log

    log = logging.getLogger('gmond_python_ood')
    formatter = logging.Formatter('%(name)s: %(levelname)s: %(message)s')
    if handlers in ['syslog', 'both']:
        sh = logging.handlers.SysLogHandler(address='/dev/log', facility=facility)
        sh.setFormatter(formatter)
        log.addHandler(sh)
    if handlers in ['stdout', 'both']:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        log.addHandler(ch)
    lmap = {
        'CRITICAL': logging.CRITICAL,
        'ERROR': logging.ERROR,
        'WARNING': logging.WARNING,
        'INFO': logging.INFO,
        'DEBUG': logging.DEBUG,
        'NOTSET': logging.NOTSET
        }
    log.setLevel(lmap[level])

#This code is for debugging and unit testing
if __name__ == '__main__':
    log_level_choices = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']
    log_choices = ['stdout', 'syslog', 'both']
    parser = optparse.OptionParser()
    parser.add_option('--log',
                      action='store', dest='log', default='stdout', choices=log_choices,
                      help='log to stdout and/or syslog. Valid: %s. Default: %s' % (', '.join(log_choices), 'stdout'))
    parser.add_option('--log-level',
                      action='store', dest='log_level', default='WARNING',
                      choices=log_level_choices,
                      help='log to stdout and/or syslog. Valid: %s.  Default: %s' % (', '.join(log_level_choices), 'WARNING'))
    parser.add_option('--log-facility',
                      action='store', dest='log_facility', default='user',
                      help='facility to use when using syslog. Default: %s' % 'user')
    (opts, args) = parser.parse_args(sys.argv[1:])
    setup_logging(opts.log, opts.log_facility, opts.log_level)
    params = {
        'min_poll_seconds': 30,
    }
    descriptors = metric_init(params)
    while True:
        for d in descriptors:
            v = d['call_back'](d['name'])
            if d['value_type'] == 'float':
                print 'value for %s is %f' % (d['name'], v)
            else:
                print 'value for %s is %d' % (d['name'], v)
        print '----------------------------'
        time.sleep(20)

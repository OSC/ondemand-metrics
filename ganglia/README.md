# Open OnDemand gmond python module

## Metrics

* `ood_active_puns` - Number of active PUNs (from `nginx_stage nginx_list`)
* `ood_rack_apps` - Number of running Rack apps
* `ood_node_apps` - Number of running Node apps
* `ood_websocket_connections` - Web socket connections reported by Apache mod_status
* `ood_unique_websocket_clients` - Web socket connections report by Apache mod_status unique by client
* `ood_client_connections` - Number of client connections reported by Apache mod_status
* `ood_unique_client_connections` - Number of unique client connects reported by Apache mod_status
* `ood_max_pun_cpu_time_user` - Max PUN user CPU time
* `ood_avg_pun_cpu_time_user` - Average PUN user CPU time
* `ood_max_pun_cpu_time_system` - Max PUN system CPU time
* `ood_avg_pun_cpu_time_system` - Average PUN system CPU time
* `ood_max_pun_cpu_percent` - Max PUN CPU percent (*)
* `ood_avg_pun_cpu_percent` - Average PUN CPU percent (*)
* `ood_max_pun_memory_rss` - Max PUN RSS
* `ood_avg_pun_memory_rss` - Average PUN RSS
* `ood_max_pun_memory_vms` - Max PUN virtual memory
* `ood_avg_pun_memory_vms` - Average PUN virtual memory
* `ood_max_pun_memory_percent` - Max PUN memory percent
* `ood_avg_pun_memory_percent` - Average PUN memory percent

(*) - these metrics are currently always returning 0.

## Setup

Install dependencies (requires EPEL repo):

```
yum -y install python2-psutil
```

Ensure the user running `gmond` can execute `/opt/ood/nginx_stage/sbin/nginx_stage nginx_list`.  The following sudo config assumes `gmond` is running as `nobody`.

```
Defaults:nobody !syslog
Defaults:nobody !requiretty
nobody ALL=(ALL) NOPASSWD:/opt/ood/nginx_stage/sbin/nginx_stage nginx_list
```

Must also ensure Apache `mod_status` is loaded and configured.  The below example should have `SERVERNAME` replaced with OnDemand configured `servername` defined in `/etc/ood/config/ood_portal.yml`.

/opt/rh/httpd24/root/etc/httpd/conf.modules.d/status.conf:
```
LoadModule status_module modules/mod_status.so
<Location /server-status>
    SetHandler server-status
    Require ip 127.0.0.1 ::1
    Require host SERVERNAME
</Location>
ExtendedStatus On

<IfModule mod_proxy.c>
    # Show Proxy LoadBalancer status in mod_status
    ProxyStatus On
</IfModule>
```

The server name used to query mod_status is read from `/etc/ood/config/ood_portal.yml` so ensure the user running `gmond` can read this file.

## Install plugin

Copy the plugin and config to necessary locations and restart gmond.

```
cp conf.d/ood.pyconf /etc/ganglia/conf.d/ood.pyconf
echo 'include ("/etc/ganglia/conf.d/ood.pyconf")' >> /etc/ganglia/conf.d/modpython.conf
cp python_modules/ood.py /usr/lib64/ganglia/python_modules/ood.py
systemctl restart gmond
```

Example of testing the plugin:

```
# python /usr/lib64/ganglia/python_modules/ood.py
value for ood_active_puns is 43
value for ood_rack_apps is 0
value for ood_node_apps is 16
value for ood_max_pun_cpu_time_user is 25.960000
value for ood_avg_pun_cpu_time_user is 1.640479
value for ood_max_pun_cpu_time_system is 122.860000
value for ood_avg_pun_cpu_time_system is 3.203457
value for ood_max_pun_cpu_percent is 0.000000
value for ood_avg_pun_cpu_percent is 0.000000
value for ood_max_pun_memory_rss is 105934848.000000
value for ood_avg_pun_memory_rss is 24611905.361702
value for ood_max_pun_memory_vms is 3539759104.000000
value for ood_avg_pun_memory_vms is 1039310085.446808
value for ood_max_pun_memory_percent is 0.156851
value for ood_avg_pun_memory_percent is 0.036441
value for ood_websocket_connections is 16
value for ood_unique_websocket_clients is 15
value for ood_client_connections is 79
value for ood_unique_client_connections is 49
----------------------------

```

## Install Ganglia graphs

These example commands would be run on the server that has the Ganglia web interface:

```
cp graph.d/ood*.json /usr/share/ganglia/graph.d/
```
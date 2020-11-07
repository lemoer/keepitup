#!/usr/bin/env python3

from main import *

session = get_session()
influx = get_influx()
nodeset = NodeSet()

influx_keep_time = datetime.timedelta(minutes=5)

nodeset.update_from_db(session)
nodeset.load_from_influx(influx, delta=influx_keep_time)

now = datetime.datetime.now()

for n in nodeset.nodes:
    print("|------------------------------------------------")
    print('|    name: ' + n.name)
    print("|  nodeid: " + n.nodeid)
    print("|      ip: " + n.ip)
    print("|   state: " + n.state)
    print("|------------------------------------------------")
    for p in n.pings:
        delta = (now - p[0]).total_seconds()
        print("| {:3.0f}s ago, {:.1f} ms".format(delta, p[1]*1000))

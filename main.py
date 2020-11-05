from multiping import MultiPing
from influxdb import InfluxDBClient
from dateutil.parser import parse as parse_time
import numpy as np
import datetime
import pprint
import time
from config import *

class Node:
    __all__ = []

    def __init__(self, name, nodeid, ip):
        self.name = name
        self.ip = ip
        self.nodeid = nodeid

        # two column array containing (time, rtt, committed)
        # -> rtt = NaN means ping was lost
        self.pings = np.empty((0,3))

        Node.__all__.append(self)

    @classmethod
    def send_all(self):
        send_time = datetime.datetime.now()

        ips = [node.ip for node in Node.__all__]
        mp = MultiPing(ips)

        mp.send()

        responses, no_responses = mp.receive(1)

        for node in Node.__all__:
            rtt = np.NaN

            if node.ip in responses:
                rtt = responses[node.ip]

            node.pings = np.vstack((node.pings, [send_time, rtt, 0]))

    @classmethod
    def gen_measurements_all(self):
        measurements = []
        for node in Node.__all__:
            measurements += node.gen_measurements()
        return measurements

    def gen_measurements(self):
        """ Generate InfluxDB Measurements for the yet uncommitted
        measurements and mark them as committed. """
        idx = np.where(self.pings[:,2] == 0)[0]

        measurements = []
        for i in idx:
            ping = self.pings[i, :]

            if np.isnan(ping[1]):
                fields = { "lost": 1 }
            else:
                fields = { "rtt": ping[1] }

            measurements.append({
                "measurement": "pingtester_ping",
                "tags": {
                    "name": self.name,
                    "nodeid": self.nodeid
                },
                "time": ping[0],
                "fields": fields
            })

        # mark them as committed
        self.pings[idx, 2] = 1

        return measurements

    @classmethod
    def load_from_influx_all(cls, influx_results):
        for node in Node.__all__:
            node.load_from_influx(influx_results)

    def load_from_influx(self, influx_results):
        if np.size(a.pings, 0) > 0:
            max_send_time = max(a.pings[:,0])
        else:
            max_send_time = None

        for r in influx_results:
            if r['nodeid'] != self.nodeid:
                continue

            send_time = parse_time(r['time'], ignoretz=True)

            # this row is most likely already loaded
            if max_send_time and send_time < max_send_time:
                continue

            if r['lost'] == 1:
                rtt = np.NaN
            else:
                rtt = r['rtt']

            self.pings = np.vstack((self.pings, [send_time, rtt, 1]))

    @classmethod
    def flush_cache_all(cls, delta=datetime.timedelta(seconds=0)):
        for node in Node.__all__:
            node.flush_cache(delta)

    def flush_cache(self, delta=datetime.timedelta(seconds=0)):
        now = datetime.datetime.now()

        idx = self.pings[:,0] < now - delta

        self.pings = np.delete(self.pings, idx, 0)


b = Node("fial", "1337", "8.8.8.1")
a = Node("google", "12213123", "8.8.8.8")

client = InfluxDBClient(INFLUX_HOST, INFLUX_PORT, INFLUX_USER, INFLUX_PASS, INFLUX_DATABASE)

test = client.query("SELECT * FROM pingtester_ping;")

Node.load_from_influx_all(list(test)[0])

Node.send_all()
Node.send_all()

client.write_points(Node.gen_measurements_all())

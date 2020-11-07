#!/usr/bin/env python3

from multiping import MultiPing
from influxdb import InfluxDBClient
from dateutil.parser import parse as parse_time
import numpy as np
import sys
import time
import pprint
import secrets
import datetime
import requests
import smtplib, ssl

from sqlalchemy import create_engine, func, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Sequence, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker,relationship

from config import *
import mail_templates

Base = declarative_base()

engine = create_engine('sqlite:///foo.db')

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    email = Column(String(50), unique=True)
    email_confirmed = Column(Boolean, default=False)
    email_token = Column(String(64), default=lambda: secrets.token_urlsafe(64))
    created_at = Column(DateTime, default=func.now())
    nodes = relationship("Node", back_populates="user")

    def __repr__(self):
        return "<User(email='%s', confirmed='%s')>" % (
                                self.email, str(self.email_confirmed))

    @classmethod
    def find_by_email(cls, session, email):
        return session.query(User).filter(User.email == email).one_or_none()

    def try_confirm(self, session, token):
        tokens_match = secrets.compare_digest(self.email_token, token)

        if not self.email_confirmed and tokens_match:
            self.email_confirmed = True
            session.add(self)
            session.commit()

        return tokens_match

    def send_confirm_mail(self, url):
        url = url + "?email=" + self.email + "&token=" + self.email_token
        mail = mail_templates.CONFIRM.format(self=self, SMTP_FROM=SMTP_FROM, url=url)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            if SMTP_USE_STARTTLS:
                context = ssl.create_default_context()
                server.starttls(context=context)
            server.sendmail(SMTP_FROM, self.email, mail)


User.metadata.create_all(engine)

Session = sessionmaker()
Session.configure(bind=engine)
session = Session()

class NodesJSONCache:

    def __init__(self):
        self.nodes = []

    def update(self):
        res = requests.get(NODES_JSON_URL)

        if not res.ok:
            print("warning: NodesJSONCache could not download " + NODES_JSON_URL + "!", file=sys.stderr)
            return

        nodes = []
        try:
            for node in res.json()['nodes']:
                nodeinfo = node['nodeinfo']
                addresses = nodeinfo['network']['addresses']
                if len(addresses) > 0:
                    address = addresses[0]
                else:
                    address = None
                
                n = Node(nodeinfo['hostname'], nodeinfo['node_id'], address)
                nodes += [n]
        except KeyError:
            print("warning: NodesJSONCache detected wrong format for " + NODES_JSON_URL + "!", file=sys.stderr)
            return

        self.nodes = nodes

    def find_by_nodeid(self, nodeid):
        for node in self.nodes:
            if node.nodeid == nodeid:
                return node

    def update_db_node(self, session, node):
        other = self.find_by_nodeid(node.nodeid)

        # node does not exist in nodes.json anymore, so we can not
        # update it.
        if not other:
            return

        node.ip = other.ip
        node.name = other.name

        session.add(node)
        session.commit()


class NodeSet:

    def __init__(self):
        self.nodes = []

    def update_from_db(self, session, filter_user=None):
        q = session.query(Node)
        if filter_user is not None:
            q = q.filter(Node.user == filter_user)

        self.nodes = q.all()

    def ping_all(self, timeout=1):
        self.ping_sliced(timeout=timeout)

    def ping_sliced(self, start=0, step=1, timeout=1):
        assert(start < step)

        sliced_nodes = self.nodes[start::step]
        if len(sliced_nodes) == 0:
            return

        send_time = datetime.datetime.now()

        ips = [node.ip for node in sliced_nodes]
        mp = MultiPing(ips)

        mp.send()

        responses, no_responses = mp.receive(timeout)

        for node in sliced_nodes: 
            rtt = np.NaN

            if node.ip in responses:
                rtt = responses[node.ip]

            node.pings = np.vstack((node.pings, [send_time, rtt, 0]))

    def load_from_influx(self, influx, delta=datetime.timedelta(days=40*365)):
        time = datetime.datetime.now() - delta
        res = influx.query("SELECT * FROM pingtester_ping WHERE time > $time;",
                bind_params=dict(time=time.isoformat()+"Z"))

        for node in self.nodes:
            node.parse_from_influx(res)

    def _gen_measurements_all(self):
        measurements = []
        for node in self.nodes:
            measurements += node.gen_measurements()
        return measurements

    def flush_cache_all(self, delta=datetime.timedelta(seconds=0)):
        for node in self.nodes:
            node.flush_cache(delta)

    def save_to_influx(self, influx):
        measurements = self._gen_measurements_all()
        influx.write_points(measurements)


class Node(Base):
    __tablename__ = 'nodes'

    id = Column(Integer, Sequence('node_id_seq'), primary_key=True)
    name = Column(String(64))
    nodeid = Column(String(32))
    ip = Column(String(64))
    state = Column(String(16))
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="nodes")

    def __init__(self, name, nodeid, ip):
        self.name = name
        self.nodeid = nodeid
        self.ip = ip
        self.state = "ok"

        # two column array containing (time, rtt, committed)
        # -> rtt = NaN means ping was lost
        self.pings = np.empty((0,3))

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

    def load_from_influx(self, influx, delta=datetime.timedelta(days=40*365)):
        time = datetime.datetime.now() - delta
        res = influx.query("SELECT * FROM pingtester_ping WHERE nodeid=$nodeid and time > $time;",
                bind_params=dict(nodeid=self.nodeid, time=time.isoformat()+"Z"))

        self.parse_from_influx(res)

    def parse_from_influx(self, influx_result):
        if np.size(self.pings, 0) > 0:
            max_send_time = max(self.pings[:,0])
        else:
            max_send_time = None

        for r in influx_result.get_points(tags={"nodeid": self.nodeid}):
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

    def flush_cache(self, delta=datetime.timedelta(seconds=0)):
        now = datetime.datetime.now()

        idx = self.pings[:,0] < now - delta

        self.pings = np.delete(self.pings, idx, 0)

    def _count_pings_total_and_lost(self, delta_minutes):
        idx = np.where(self.pings[:,0] > datetime.datetime.now() - datetime.timedelta(minutes=delta_minutes))
        pings = self.pings[idx,1]

        return (np.size(pings,1), np.sum(np.isnan(np.double(pings))))

    def _abstract_check(self, session, new_state, condition):
        # do not fire state change again, if we are already in a state
        if self.state == new_state:
            return False

        total, lost = self._count_pings_total_and_lost(delta_minutes=5)

        # if there are less than 5 ping records in the last 5 minutes, then
        # there is not enough confidence to raise state changes
        if total < 5:
            return False

        # condition for state change
        if not condition(total, lost):
            return False

        self.state = new_state
        session.add(self)
        session.commit()
        return True

    def check_alarm(self, session):
        return self._abstract_check(
            session,
            'alarm',
            lambda total, lost: lost / total > 0.9
        )

    def check_resolved(self, session):
        return self._abstract_check(
            session,
            'ok',
            lambda total, lost: lost / total < 0.3
        )

@event.listens_for(Node, 'load')
def on_load(instance, context):
    instance.pings = np.empty((0,3))

cache = NodesJSONCache()
db = NodeSet()
client = InfluxDBClient(INFLUX_HOST, INFLUX_PORT, INFLUX_USER, INFLUX_PASS, INFLUX_DATABASE)
#db = NodeDB(client)
#b = Node("fial", "1337", "8.8.8.1")
Node.metadata.create_all(engine)
#a = Node("google", "12213123", "8.8.8.8")
#
#
#
#Node.#
#Node.send_all()
#Node.send_all()
#
#client.write_points(Node.gen_measurements_all())
db.update_from_db(session, User.find_by_email(session, "me@irrelefant.net"))
db.load_from_influx(client)
print(db.nodes[0].pings)

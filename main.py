#!/usr/bin/env python3

from multiping import MultiPing
from influxdb import InfluxDBClient
from dateutil.parser import parse as parse_time
import numpy as np
import sys
import time
import pytz
import pprint
import secrets
import datetime
import requests
import smtplib, ssl
from email.utils import make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.charset import Charset, QP

from sqlalchemy import create_engine, func, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Sequence, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker,relationship,column_property
from sqlalchemy.sql import case

from config import *
import mail_templates

SQLITE_URI = 'sqlite:///foo.db'

Base = declarative_base()

if not APP_URL.endswith('/'):
    APP_URL += '/'

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    email = Column(String(50), unique=True)
    email_confirmed = Column(Boolean, default=False)
    email_token = Column(String(64), default=lambda: secrets.token_urlsafe(64))
    created_at = Column(DateTime, default=func.now())
    subscriptions = relationship("Subscription", back_populates="user")

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
        mail_template = mail_templates.CONFIRM

        self.send_mail(mail_template, url=url)

    def send_mail(self, mail_template, in_reply_to = None, **kwargs):
        msgid = make_msgid()

        # Default encoding mode set to Quoted Printable. Acts globally!
        #Charset.add_charset('utf-8', Charset.QP, Charset.QP, 'utf-8')

        subject = mail_template['subject'].format(**kwargs)
        message = mail_template['message'].format(**kwargs)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = str(Header(subject, 'utf-8'))
        msg['From'] = str(Header(SMTP_FROM, 'utf-8'))
        msg['To'] = str(Header(self.email, 'utf-8'))
        msg['Message-ID'] = msgid
        msg['Reply-To'] = SMTP_REPLY_TO_EMAIL
        msg['Date'] = datetime.datetime.now(pytz.utc).strftime("%a, %e %b %Y %T %z")

        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to

        # add message
        charset = Charset('utf-8')
        # QP = quoted printable; this is better readable instead of base64, when
        # the mail is read in plaintext!
        charset.body_encoding = QP
        message_part = MIMEText(message.encode('utf-8'), 'plain', charset)
        msg.attach(message_part)

        if DEBUG:
            with open("/tmp/keepitup_mails.log", "a") as f:
                f.write(mail + "\n")
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                if SMTP_USE_STARTTLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)

                server.sendmail(SMTP_FROM, self.email, msg.as_string())

        return msgid

    @property
    def subscribed_nodes(self):
        return [subscription.node for subscription in self.subscriptions]


class NodesJSONCache:

    def __init__(self):
        self.nodes = []

    def update(self, nodeset=None):
        res = requests.get(NODES_JSON_URL)

        if not res.ok:
            print("warning: NodesJSONCache could not download " + NODES_JSON_URL + "!", file=sys.stderr)
            return

        nodes = []
        try:
            for node in res.json()['nodes']:
                nodeinfo = node['nodeinfo']

                if nodeset:
                    db_node = nodeset.find_by_nodeid(nodeinfo['node_id'])
                    if db_node:
                        nodes += [db_node]
                        continue

                addresses = nodeinfo['network']['addresses']
                if addresses and len(addresses) > 0:
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

    def update_db_node(self, node):
        other = self.find_by_nodeid(node.nodeid)

        # node does not exist in nodes.json anymore, so we can not
        # update it.
        if not other:
            return

        node.ip = other.ip
        node.name = other.name


class Subscription(Base):
    __tablename__ = 'subscriptions'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True, nullable=False)
    node_id = Column(Integer, ForeignKey('nodes.id'), primary_key=True, nullable=False)
    send_notifications = Column(Boolean, default=True)
    user = relationship("User", back_populates="subscriptions")
    node = relationship("Node", back_populates="subscriptions")


class NodeSet:

    def __init__(self):
        self.nodes = []

    def update_from_db(self, session, filter_user=None):
        # force reload from db
        session.expire_all()

        q = session.query(Node)
        if filter_user is not None:
            # TODO: update here
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

    def find_by_nodeid(self, nodeid):
        for node in self.nodes:
            if node.nodeid == nodeid:
                return node


class Alarm(Base):
    __tablename__ = 'alarms'

    id = Column(Integer, Sequence('alarm_id_seq'), primary_key=True)
    node_id = Column(Integer, ForeignKey('nodes.id'))
    node = relationship("Node", back_populates="alarms")
    alarm_at = Column(DateTime, default=func.now())
    alarm_mail_msgid = Column(String(995), default=None)
    resolved_at = Column(DateTime, default=None)
    is_resolved = column_property(case(
        [(resolved_at == None, False)], else_=True))
    state = column_property(case(value=is_resolved, whens={
        True: 'ok',
        False: 'alarm'
    }))

    @property
    def duration_str(self):
        if not self.is_resolved:
            return "ongoing"

        delta = self.resolved_at - self.alarm_at

        if delta.total_seconds() > 24*60*60:
            return "%d days" % (delta.total_seconds() / 24 / 60 / 60)

        if delta.total_seconds() > 60*60:
            return "%d hrs" % (delta.total_seconds() / 60 / 60)

        if delta.total_seconds() > 60:
            return "%d min" % (delta.total_seconds() / 60)

        return "%d s" % delta.total_seconds()

    def send_notification_mails(self, session):
        node = self.node
        url = APP_URL + 'node/' + self.node.nodeid

        for subscription in node.subscriptions:
            if not subscription.send_notifications:
                continue

            user = subscription.user

            if self.is_resolved:
                mail_template = mail_templates.RESOLVED

                user.send_mail(mail_template, in_reply_to=self.alarm_mail_msgid, node=node, url=url)
            else:
                mail_template = mail_templates.ALARM

                self.alarm_mail_msgid = user.send_mail(mail_template, node=node, url=url)

                session.add(self)
                session.commit()


class Node(Base):
    __tablename__ = 'nodes'

    id = Column(Integer, Sequence('node_id_seq'), primary_key=True)
    name = Column(String(64))
    nodeid = Column(String(32), unique=True)
    ip = Column(String(64), nullable=False)
    state = Column(String(16))
    is_waiting = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    subscriptions = relationship("Subscription", back_populates="node")
    alarms = relationship("Alarm", back_populates="node", order_by="desc(Alarm.id)")

    def __init__(self, name, nodeid, ip):
        self.name = name
        self.nodeid = nodeid
        self.ip = ip
        self.state = "new"
        self.is_waiting = True

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
            if max_send_time and send_time <= max_send_time:
                continue

            if r['lost'] == 1:
                rtt = np.NaN
            else:
                rtt = r['rtt']

            self.pings = np.vstack((self.pings, [send_time, rtt, 1]))

    def flush_cache(self, delta=datetime.timedelta(seconds=0)):
        now = datetime.datetime.now()

        idx = np.where(self.pings[:,0] < now - delta)

        self.pings = np.delete(self.pings, idx, 0)

    def _count_pings_total_and_lost(self, delta_minutes):
        idx = np.where(self.pings[:,0] > datetime.datetime.now() - datetime.timedelta(minutes=delta_minutes))
        pings = self.pings[idx,1]

        return (np.size(pings,1), np.sum(np.isnan(np.double(pings))))

    def _switch_state(self, session, allowed_new_states):
        old_state = self.state
        total, lost = self._count_pings_total_and_lost(delta_minutes=60)

        if lost / total < 0.3:
            new_state = 'ok'
        elif lost / total > 0.9:
            new_state = 'problem'
        else:
            new_state = old_state

        if new_state not in allowed_new_states:
            new_state = old_state

        if new_state != old_state:
            self.state = new_state
            session.add(self)
            session.commit()

        return old_state, new_state

    def _update_waiting(self, session):
        """ This function calculates and updates the watiing status. New nodes
        could lose their first packet and would directly end up in problem
        state even if their loss rate is e.g. just 1%. Therefore we want at
        least 5 ping packets in the last 5 minutes. If for any reason hosts are
        not pinged by the worker anymore, they should fall back to the waiting
        constitution within 1 minute. """
        total_1min, _ = self._count_pings_total_and_lost(delta_minutes=1)
        total_5min, _ = self._count_pings_total_and_lost(delta_minutes=5)
        self.is_waiting = total_1min < 1 or total_5min < 5
        session.add(self)
        session.commit()

    def check(self, session, allowed_new_states=['ok','problem','waiting', 'new']):
        """ Checks for state changes. Returns an Alarm object, if an alarm
        has just been created, or an alarm has just been resolved. This means
        it only returns an Alarm object if a state change happened. """

        self._update_waiting(session)
        if self.is_waiting:
            # switching state is only allowed when node is not waiting
            return None

        old_state, new_state = self._switch_state(session, allowed_new_states)
        alarm = None

        if old_state == 'ok' and new_state == 'problem':
            alarm = Alarm(node=self)

        if old_state == 'new' and new_state == 'problem':
            alarm = Alarm(node=self)

        if old_state == 'problem' and new_state == 'ok':
            alarm = self.latest_alarm(session)
            alarm.resolved_at = func.now()

        if alarm:
            session.add(alarm)
            session.commit()
            alarm.send_notification_mails(session)

        return alarm

    def latest_alarm(self, session):
        return session.query(Alarm).\
            filter(Alarm.node_id == self.id).\
            order_by(Alarm.id.desc()).\
            limit(1).one_or_none()

    @property
    def subscribed_users(self):
        return [subscription.user for subscription in self.subscriptions]

    @property
    def is_in_db(self):
        # nodes in db have an id, others don't
        return bool(self.id)

    def get_subscription_by_user(self, session, user):
        if user is None:
            return None
        return session.query(Subscription).\
            filter(Subscription.node == self).\
            filter(Subscription.user == user).\
            one_or_none()

    @property
    def constitution(self):
        if self.is_waiting:
            return 'waiting'
        else:
            return self.state


@event.listens_for(Node, 'load')
def on_load(instance, context):
    instance.pings = np.empty((0,3))


def get_session():
    engine = create_engine(SQLITE_URI)

    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def get_influx():
    if INFLUX_HOST:
        return InfluxDBClient(INFLUX_HOST, INFLUX_PORT, INFLUX_USER, INFLUX_PASS, INFLUX_DATABASE)


def init_db():
    engine = create_engine(SQLITE_URI)

    classes = [Node, User, Alarm, Subscription]

    for cls in classes:
        cls.metadata.create_all(engine)


if __name__ == '__main__':
    influx = get_influx()
    db = get_session()

    nodeset = NodeSet()
    nodeset.update_from_db(db)
#User.metadata.create_all(engine)

#cache = NodesJSONCache()
#db = NodeSet()
#client =
#db = NodeDB(client)
#b = Node("fial", "1337", "8.8.8.1")
#Node.metadata.create_all(engine)
#a = Node("google", "12213123", "8.8.8.8")
#
#
#
#Node.#
#Node.send_all()
#Node.send_all()
#
#client.write_points(Node.gen_measurements_all())
#db.update_from_db(session, User.find_by_email(session, "me@irrelefant.net"))
#db.load_from_influx(client)
#print(db.nodes[0].pings)

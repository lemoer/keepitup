#!/usr/bin/env python3

from main import *
import time

session = get_session()
nodeset = NodeSet()

nodeset.update_from_db(session)

print("ping_worker.py, " + str(len(nodeset.nodes)) + " nodes loaded.")

try:
    while True:
        nodeset.update_from_db(session)

        # TODO: Add updating last_seen attribute from nodes.json here...

        for n in nodeset.nodes:
            alarm = n.check(session)
            if alarm is None:
                continue

            if alarm.is_resolved:
                print("node " + n.name + ": resolved")
            else:
                print("node " + n.name + ": alarm")


except KeyboardInterrupt:
    print("CTRL + C pressed. Exiting.")

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

        # Update last_seen_at from nodes.json...
        nodes_json_cache = NodesJSONCache()
        nodes_json_cache.update()

        for node in nodeset.nodes:
            nodes_json_cache.update_db_node(node)
            session.add(node)

        session.commit()

        for n in nodeset.nodes:
            alarm = n.check(session)
            if alarm is None:
                continue

            if alarm.is_resolved:
                print("node " + n.name + ": resolved")
            else:
                print("node " + n.name + ": alarm")

        time.sleep(60)


except KeyboardInterrupt:
    print("CTRL + C pressed. Exiting.")

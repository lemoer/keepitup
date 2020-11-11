#!/usr/bin/env python3

from main import *
import sys
import time

session = get_session()
nodeset = NodeSet()
nodes_json_cache = NodesJSONCache()

if '--timeit' in sys.argv:
	t = time.time()

nodes_json_cache.update()
nodeset.update_from_db(session)

for node in nodeset.nodes:
	nodes_json_cache.update_db_node(node)
	session.add(node)

session.commit()

if '--timeit' in sys.argv:
	print("Duration: %.2f s" % (time.time() - t))

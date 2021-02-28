#!/usr/bin/env python3

from main import *

session = get_session()
nodeset = NodeSet()

nodeset.update_from_db(session)

now = datetime.datetime.now()

for n in nodeset.nodes:
    print("|------------------------------------------------")
    print('|    name: ' + n.name)
    print("|  nodeid: " + n.nodeid)
    print("|   state: " + n.state)
    print("|------------------------------------------------")

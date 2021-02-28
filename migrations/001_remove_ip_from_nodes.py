#!/usr/bin/python3

from sqlalchemy import create_engine, func, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Sequence, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker,relationship,column_property
from sqlalchemy.sql import case

import sys
from os.path import dirname
sys.path.append(dirname(dirname(__file__)))

from main import *

# As DBVersion is introduced in this migration, we need to ensure, that the
# DBVersion table exists:
init_db()

db = get_session()

if DBVersion.get(db) > 0:
    print(__file__ + ": This migration is already applied. (ok)")
    exit(0)

# SQLite does not support ALTER TABLE ... DROP COLUMN... Therefore we need to
# rename the table, create a new table, migrate data and delete the old table...

db.execute('ALTER TABLE `nodes` RENAME TO `nodes_old`')

# recreate new table "nodes"
init_db()

# migrate data
db.execute('INSERT INTO nodes SELECT id,name,nodeid,state,is_waiting,user_id FROM nodes_old;')

db.execute('DROP TABLE `nodes_old`')

DBVersion.set(db, 1)

db.commit()

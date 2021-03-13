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
db.execute("""
CREATE TABLE nodes (
	id INTEGER NOT NULL,
	name VARCHAR(64),
	nodeid VARCHAR(32),
	state VARCHAR(16),
	is_waiting BOOLEAN,
	user_id INTEGER,
	PRIMARY KEY (id),
	UNIQUE (nodeid),
	CHECK (is_waiting IN (0, 1)),
	FOREIGN KEY(user_id) REFERENCES users (id)
);
""")

# migrate data
db.execute('INSERT INTO nodes SELECT id,name,nodeid,state,is_waiting,user_id FROM nodes_old;')

db.execute('DROP TABLE `nodes_old`')

DBVersion.set(db, 1)

db.commit()

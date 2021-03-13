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

db = get_session()

if DBVersion.get(db) < 1:
    print(__file__ + ": Error, please apply the first migration script first. (failed)")
    exit(1)

if DBVersion.get(db) > 1:
    print(__file__ + ": This migration is already applied. (ok)")
    exit(0)

db.execute('ALTER TABLE nodes ADD COLUMN last_seen_at DATETIME')
db.execute('ALTER TABLE nodes ADD COLUMN last_updated_at DATETIME')

DBVersion.set(db, 2)

db.commit()

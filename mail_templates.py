#!/usr/bin/env python3

CONFIRM = """From: {SMTP_FROM}
To: {user.email}
Subject: Confirm your email for KeepItUp! :)

Hi there,

you need to confirm your email with this token:

{url}

If you have not registered yourself for keepitup,
please kindly ignore this mail.

Kind regards,
lemoer
"""

ALARM = """From: {SMTP_FROM}
To: {user.email}
Subject: [KeepItUp] alarm: {node.name} is unreachable via ping

Hi there,

the node {node.name} is unreachable.

Link to node: {url}

Kind regards,
lemoer
"""

RESOLVED = """From: {SMTP_FROM}
To: {user.email}
Subject: [KeepItUp] resolved: {node.name} is unreachable via ping

Hi there,

the node {node.name} is now reachable again.

Link to node: {url}

Kind regards,
lemoer
"""

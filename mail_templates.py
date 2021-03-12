#!/usr/bin/env python3

CONFIRM = dict(
    subject="Confirm your email for KeepItUp! :)",
    message="""Hi there,

you need to confirm your email with this token:

{url}

Please keep this mail or token, as you can always
log into your account with this token again. There
is no separate password.

If you have not registered yourself for keepitup,
please kindly ignore this mail.

Kind regards,
lemoer
""")

ALARM = dict(
    subject="[KeepItUp] alarm: {node.name} is unreachable",
    message="""Hi there,

the node {node.name} is unreachable.

Link to node: {url}

Kind regards,
lemoer
""")

RESOLVED = dict(
    subject="[KeepItUp] resolved: {node.name} is reachable again",
    message="""Hi there,

the node {node.name} is now reachable again.

Link to node: {url}

Kind regards,
lemoer
"""
)

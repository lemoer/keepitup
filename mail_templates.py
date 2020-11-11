#!/usr/bin/env python3

CONFIRM = """{HEAD}
Subject: Confirm your email for KeepItUp! :)

Hi there,

you need to confirm your email with this token:

{url}

Please keep this mail or token, as you can always
log into your account with this token again. There
is no separate password.

If you have not registered yourself for keepitup,
please kindly ignore this mail.

Kind regards,
lemoer
"""

ALARM = """{HEAD}
Subject: [KeepItUp] alarm: {node.name} is unreachable

Hi there,

the node {node.name} is unreachable.

Link to node: {url}

Kind regards,
lemoer
"""

RESOLVED = """{HEAD}
Subject: [KeepItUp] resolved: {node.name} is reachable again

Hi there,

the node {node.name} is now reachable again.

Link to node: {url}

Kind regards,
lemoer
"""

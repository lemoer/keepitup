#!/usr/bin/env python3

CONFIRM = """
From: {SMTP_FROM}
To: {self.email}
Subject: Confirm your email for pingtester! :)

Hi there,

you need to confirm your email with this token:

{url}

If you have not registered yourself for pingtester,
please kindly ignore this mail.

Kind regards,
lemoer
"""


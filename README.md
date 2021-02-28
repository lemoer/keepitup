# KeepItUp

## New Concept (Notes)

Nodes have:
- `last_seen` attribute: timestamp of last answer to respondd multicasts (updates minutely)
- `last_updated` attribute: timestamp of last update from nodes.json

Node states:
- `ok`: `(now() - last_seen) < 60min` and `(now() - last_updated) < 5 min`
- `problem`: `(now() - last_seen) >= 60min` and `(now() - last_updated) < 5 min`
- `unknown`: `(now() - last_updated) > 5 min`

## Debian Dependencies

``` shell
apt install python3 python3-venv composer
```

## Install

``` shell
cd /opt
git clone https://github.com/lemoer/keepitup
cd keepitup
cp config.py.example config.py
# edit your config file now
bash setup.sh --systemwide
systemctl start keepitup.target
systemctl start keepitup-update-nodes.service
```

## Translations

There is a shell command to help with translation workflows:

``` shell
(venv) lemoer@orange ~/d/f/g/keepitup (main)> ./translate.sh
This small script helps in doing the translation workflows.

Suppose you have added new _('...') or gettext() calls to your *.py or templates/:

    ./translate.sh update
    # edit translations/de/LC_MESSAGES/messages.po
    ./translate.sh compile
```

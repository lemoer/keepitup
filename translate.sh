#!/bin/sh

if [ "$#" -lt 1 ]; then
	echo This small script helps in doing the translation workflows.
	echo
	echo "Suppose you have added new _('...') or gettext() calls to your *.py or templates/:"
	echo
	echo "    $0 update"
	echo "    # edit translations/de/LC_MESSAGES/messages.po"
	echo "    $0 compile"
	exit 0
fi

if [ -z "$VIRTUAL_ENV" ]; then
	echo ERROR: Please activate the venv first
	exit 1
fi

cd "$(dirname "$0")"

case "$1" in
  update)   pybabel extract -F babel.cfg -o messages.pot . && pybabel update --no-fuzzy-matching -i messages.pot -d translations -l en -l de ;;
  compile)   pybabel compile -d translations/ ;;
  *) echo "ERROR: command $1 not found."; exit 1;;
esac

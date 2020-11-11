#!/bin/bash

set -e

SYSTEMD=/etc/systemd/system/
DIR=$(realpath $(dirname "$0"))
SYSTEM_USER=keepitup

cd $DIR

python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
(cd static; composer install)

# init db
venv/bin/python -c 'from main import *; init_db();'

if [ "$1" == '--systemwide' ]; then
	if getent passwd ${SYSTEM_USER} > /dev/null 2>&1; then
		echo Info: User ${SYSTEM_USER} already exists.
	else
		sudo useradd -d "$DIR" -r ${SYSTEM_USER}
		echo User ${SYSTEM_USER} already created.
	fi

	for f in $DIR/dist/*.{service,target}; do
		sudo cp "$f" "$SYSTEMD"
		sudo sed -i "s\\%DIR%\\$DIR\\g" "$SYSTEMD"/$(basename "$f")
		sudo sed -i "s\\%SYSTEM_USER%\\${SYSTEM_USER}\\g" "$SYSTEMD"/$(basename "$f")
	done
	# Only enable the services, but not the target.
	for f in $DIR/dist/*.service; do
		sudo systemctl enable $(basename "$f")
	done

	sudo systemctl daemon-reload

	chown -R ${SYSTEM_USER} "$DIR" || /bin/true
fi

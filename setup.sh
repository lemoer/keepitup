#!/bin/bash

set -e

SYSTEMD=/etc/systemd/system/
DIR=$(realpath $(dirname "$0"))
SYSTEM_USER=lemoer

cd $DIR

python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
(cd static; composer install)
./translate.sh compile

# init db
venv/bin/python -c 'from main import *; init_db();'

if [ "$1" == '--systemwide' ]; then
	if getent passwd ${SYSTEM_USER} > /dev/null 2>&1; then
		echo Info: User ${SYSTEM_USER} already exists.
	else
		sudo useradd -d "$DIR" -r ${SYSTEM_USER}
		echo User ${SYSTEM_USER} already created.
	fi

	for f in $DIR/dist/*.{service,target,timer}; do
		sudo cp "$f" "$SYSTEMD"
		sudo sed -i "s\\%DIR%\\$DIR\\g" "$SYSTEMD"/$(basename "$f")
		sudo sed -i "s\\%SYSTEM_USER%\\${SYSTEM_USER}\\g" "$SYSTEMD"/$(basename "$f")
	done

	# remove legacy stuff
	if [ -f "$SYSTEMD/keepitup-update-nodes.timer" ]; then
		echo "Removing legacy systemd unit keepitup-update-nodes.service."
		sudo rm "$SYSTEMD/keepitup-update-nodes.timer"
		sudo rm "$SYSTEMD/keepitup-update-nodes.service"
		sudo systemctl disable keepitup-update-nodes.timer
		sudo systemctl stop keepitup-update-nodes.timer
	fi

	sudo systemctl enable keepitup-worker.service
	sudo systemctl enable keepitup-webserver.service
	sudo systemctl enable keepitup.target

	sudo systemctl daemon-reload

	chown -R ${SYSTEM_USER} "$DIR" || /bin/true
fi

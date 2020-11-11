# KeepItUp

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
systemctl enable keepitup.target
systemctl start keepitup.target
```

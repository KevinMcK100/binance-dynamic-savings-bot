#!/bin/bash

### UPDATE TO ROOT DIRECTORY OF YOUR SCRIPT ###
INSTALL_DIR=~/binance-dynamic-savings-bot/binance-dynamic-savings-bot/

CURRENT_DIR=$(pwd)

# Add user to path and assign user on service
UserBot="$USER"
PATH=$PATH:/home/${UserBot}/.local/bin;export $PATH

# Pull latest code from git repo
cd ${INSTALL_DIR}
git pull origin master

# Install dependencies in virtual environment
cd ${INSTALL_DIR}/..
if [ ! -d venv ]; then
    python3 -m venv venv
fi
# Activate virtual environment
. venv/bin/activate
cd ${INSTALL_DIR}

# Upgrade pip
pip install --upgrade pip
# Install pip-tools to compile dependencies
python -m pip install pip-tools
# Compile dependencies and update requirements.txt
python -m piptools compile --upgrade requirements.in
# Install dependencies
pip3 install -r requirements.txt

cat <<EOF >binance-dynamic-savings-bot.service
[Unit]
Description=Binance Dynamic Savings Bot Service
After=multi-user.target
[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Restart=always
ExecStart=${INSTALL_DIR}/../venv/bin/python3 -u -m binance_dynamic_savings_bot
User=${UserBot}
[Install]
WantedBy=multi-user.target
EOF
sudo mv binance-dynamic-savings-bot.service /etc/systemd/system/binance-dynamic-savings-bot.service

sudo systemctl daemon-reload
sudo systemctl enable binance-dynamic-savings-bot.service
sudo systemctl start binance-dynamic-savings-bot.service

cd ${CURRENT_DIR}

#!/bin/bash
# Removes what setup.sh added (run as root by the IoT Node uninstall command).
rm -f "${IOT_NODE_HOME:?}/.config/autostart/inventory-sign.desktop"

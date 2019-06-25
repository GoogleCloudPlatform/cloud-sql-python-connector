#!/bin/bash

apt update
apt upgrade

apt install software-properties-common

add-apt-repository ppa:deadsnakes/ppa

apt install python3.7

#!/bin/bash

apt update
apt install software-properties-common

add-apt-repository ppa:deadsnakes/ppa

apt install python3.7

# ava

testing variuous chat bot setups for AVA

inital one uses chatgpt api and azure speech sdk , with either remote or local whisper for speech to text

tested piper but its very slow locally even on an RTX A6000 ADA


# web
 
 web version using flask

# cmdline

 python version

# chat-cpp

 cpp version


# python notes

 (3.10 failed with auralis) TTS  numpy/networkx incompatible versions, third re-setup on 3.11.

 sudo apt install software-properties-common -y
 
 sudo add-apt-repository ppa:deadsnakes/ppa
 
 sudo apt install python3.11
 
 sudo apt-get install python3.11-venv
 
 python3.10 -m venv tts
 
 source tts/bin/activate

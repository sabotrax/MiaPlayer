# INSTALL

Raspberry Pi OS will be assumed for the rest of this document.

## Additional packages

Install the required software packages. 
```
sudo apt-get install git mpd nano python3 python3-pip python3-venv tmux
```

## Download the player

Clone the player to the directory you wish it to be running in.

- ``` cd /home/pi ```
- ``` git clone https://github.com/sabotrax/MiaPlayer.git ```

## Python

Create the virtual environment and install the modules.

- ``` cd MiaPlayer ```
- ``` python3 -m venv . ```
- ``` source bin/activate ```
- ``` pip3 install -r requirements.txt ```
- ``` echo "source ~/MiaPlayer/bin/activate" >> .bashrc ```

## Startup

Cron is starting tmux which is then starting the player.  
The player is running as the root user.

- ``` sudo crontab -e ``` and add ``` @reboot /usr/bin/tmux ```
- ``` sudo nano /root/.tmux.conf ``` and add
  ```
  new-session -d -s MIAPLAYER
  send-keys -t PLAYER "/usr/bin/bash" C-m
  send-keys -t PLAYER "cd /home/pi/Miaplayer" C-m
  send-keys -t PLAYER "source bin/activate" C-m
  send-keys -t PLAYER "python3 player.py" C-m
  ```

## Shutdown

When the player is halted, either by the press of the on/off button or by command, systemd will execute the helper script.  
Install the script:

- ``` sudo cp helper/miaplayer.service /etc/systemd/system ```
- ``` sudo systemctl daemon-reload ```
- ``` sudo systemctl enable miaplayer.service ```

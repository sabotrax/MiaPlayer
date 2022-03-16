# MiaPlayer

MiaPlayer is an audio player controlled by RFID tokens.

**Documentation is work in progress**

It's made of a Raspberry Pi Zero W, a RFID card reader, an amplifier,
a speaker, a power bank, some Python code and a 3D printed case.  
The cards and other physical controls are interfacing mostly with MPD,
which is doing the playback, running on Linux.  
Being a souped-up MPD, music has to be copied to the player in order to be played.  
The names of music titles or albums have to be written to RFID cards/fobs.
This can be done with the player itself.

All documents necessary to build the player are provided here.

## Requirements

Be comfortable installing Raspberry Pi OS, configuring WLAN,
using SSH, the command line, a soldering iron and crimping tool.
Also 3D design and printing. You'll have to partly redesign the case
because I used a power bank which is no longer available.

## Bill of materials

- 1 Raspberry Pi Zero W
- 1 RC522 RFID module
- 1 adafruit NeoPixel Stick 8 x RGB
- 1 HiFiBerry MiniAmp
- 1 Visaton FRS 8 M speaker
- 1 KY-040 rotary encoder module
- 4 push buttons, see DIMENSIONS
- Any power bank fitting inside the frame, see DIMENSIONS
- 1 USB-A to Micro USB (power bank output to Raspberry Zero input)
- A set of jumper wire cables, all female, about 15 to 20 cm length
- A 30 cm length of speaker wire 1,5 mm²
- **TBD** A set of M25 and M3 screws, nuts and standoffs
- **TBD** grams of filament

## Assembly

**WIP** See ASSEMBLY.

## Installation

**TBD** See INSTALL.

## Usage

### RFID cards/fobs

RFID cards are being used to select titles and add them to the playlist, trigger actions like slumber mode or change the configuration.

The following strings are recognized as instructions by the player after being written on a card:

Text: toggle_pause  
Role: Play/pause.

Text: toggle_clr_plist  
Role: Always clear the playlist before adding titles or attach them to the existing list.

Text: toggle_party_mode  
Role: Titles are kept in the playlist after playback or are removed from it.

Text: shutdown_in_45  
Role: Slumber mode. Shutdown the player after 45 minutes (possible values 1-99). Turns off the LED strip.

Text: set_max_volume  
Role: Set/Reset the maximum volume. To set the volume limit, attach the card, set the desired volume and attach the card again. To remove the limit, attach the card twice without changing the volume.

Text: t:title  
Role: Adds a title to the playlist (ID3 tag of the title).

Text: a:album  
Role: Adds an album to the playlist (ID3 tag of the album).

### Buttons

On the top of the assembled player from left to right:

#### Backward button
- Short press: Move backward one title in the playlist.
- Double short press: Seek backward inside the title for a quarter of the duration. Does not cross song boundaries.
- Long press: Move backward to the previous album. XXwasbeikeinemanderenalbum?
- Short press followed by a long one: Set the bookmark to the currently played title and album.

#### Playlist button
- Short press: Remove the currently played song from the playlist.
- Double short press: Remove the currently played album from the playlist.
- Long press: Clear the playlist.

#### Forward button
- Short press: Move forward on title in the playlist.
- Double short press: Seek forward inside the title for a quarter of the duration. Does not cross song boundaries.
- Long press: Move forward to the next album. XXwasbeisieheoben?
- Short press followed by a long one: Recall the bookmark and start playing 15 seconds before the set timestamp. Adding the album to the playlist if necessary.

#### Volume dial
- Turn: Change the volume.
- Press: Play/pause.

#### On/Off button
- Positioned down and right at the front of the frame.

### LED display

The LED strip is conveying different information:

#### Startup

- A green animation starting from the inner LEDs playing outwards.

The rest is a scanning animation starting from the left going right and back. The only differ in color.

#### Acknowledgement

- A green animation.

#### Errors

- File not found/MPD connection lost/hardware module crash: A red animation.
- Tag/card format error: A blue animation.

#### Playlist

The number of songs in the playlist is represented by LEDs color-coded as roman numerals.

- Red LED = 10
- Blue LED = 5
- Green LED = 1

Example: 4 LEDS of RRBL = 26  
The maximum number the 8 pixel wide strip can display using this representation is 48.

The LEDs are turned off when slumber mode is activated.

### Data transfer

Audio data has to be transferred to the player before it can be played.
This can be done by simply copying data to /var/lib/mpd/music on the SD card
or setting up Samba, NFS or scp for remote access.
My preferred method is using SyncThing. It's a directory synchronization tool
that's also working over the Internet. I have it setup so that a copy of the music
directory on my computer is paired with the music directory on the player.
See https://docs.syncthing.net/index.html

### Configuration

The player is configurable by changing options either inside config.ini or player.py itself.
Options inside the configuration file are dynamic and will be overwritten by the player.

## Contributing
I appreciate contributions. Feel free to contact me.

## License
Distributed under the New BSD License, see LICENSE.txt.

### Project status
This is version 1.0 of the player. There are improvements to be made and also new features to be added (some more reasonable than others), but not any time soon.

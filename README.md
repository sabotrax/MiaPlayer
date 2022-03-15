# MiaPlayer

MiaPlayer is an audio player controlled by RFID tokens.

It's made of a Raspberry Pi Zero W, a RFID card reader, an amplifier,  
a speaker, a power bank, some Python code and a 3D printed case.  
The cards and other physical controls are interfacing mostly with MPD,  
which is doing the playback, running on Linux.  
Being a souped-up MPD, music has to be copied to the player in order  
to be played.  
The names of music titles or albums have to be written to RFID tags/cards.  
This can be done with the player itself.

All documents necessary to build the player are provided here.

## Requirements

Be comfortable installing Raspberry Pi OS, configuring WLAN,
using SSH, apt, the command line, a soldering iron and crimping tool.
Also 3D design and printing. You'll have to partly redesign the case
because I used a power bank which is no longer available.

## Bill of materials

- Raspberry Pi Zero W
- RC522 RFID module
- adafruit NeoPixel Stick 8 x RGB
- HiFiBerry MiniAmp
- Visaton FRS 8 M speaker
- KY-040 rotary encoder module
- 4 push buttons, see DIMENSIONS
- Any power bank fitting inside the frame, see DIMENSIONS
- USB-A to Micro USB (power bank output to Raspberry Zero input)
- Jumper wire cables, all female, about 15 to 20 cm length
- Speaker wire 1,5 mm², about 30 cm length
- XXgenauer A set of M25 and M3 screws, nuts and standoffs
- XXgramm_filament

## Assembly

See ASSEMBLY.

## Installation

See INSTALL.

## Usage

### RFID tags/cards

RFID tags or cards are being used to add titles to the playlist, trigger actions like slumber mode or change the configuration.

The following text is recognized by the player after beeing written on a tag or card:

Text: toggle_pause
Role: Play/pause.

Text: toggle_clr_plist
Role: Attach titles to the playlist or clear it first.

Text: toggle_party_mode
Role: Titles are kept in the playlist or are removed after playback.

Text: shutdown_in_45
Role: Slumber mode. Shutdown the player after 45 minutes (range 1-99). Turns off the LED strip.

Text: set_max_volume
Role: Sets/Reset the maximum volume. To set the volume limit, attach the card, set the desired volume and attach the card again. To remove the limit, attach the card twice without changing the volume.

Text: t:title
Role: Adds a title to the playlist (case sensitive, copied out of the ID3 tag).

Text: a:album
Role: Adds an album to the playlist (same as above).

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
- Short press followed by a long one: Start playing from the bookmark. Adding the album to the playlist if necessary.

#### Volume dial
- Turn: Change the volume.
- Press: Play/pause.

#### On/Off button
- Positioned down and right at the front of the frame.

### LED display

The LED strip is conveying different information:

#### Acknowledgement

- A green light running from left to right and back.

#### Errors

- File not found/MPD connection/hardware modules: A red light running from left to right and back.
- Tag/card format error: A blue light running from left to right and back.

#### Playlist

The number of songs in the playlist is represented by color-coded roman numerals.  
The maximum number the 8 pixel wide strip can display using this representation is 48.

- Red LED = 10
- Blue LED = 5
- Green LED = 1

Example: 4 LEDS of RRBL = 26

The LEDs are turned off when slumber mode is activated.

### Data transfer

Audio data has to be transferred to the player before it can be played.  
This can be done by simply copying data to /var/lib/mpd/music on the SD card  
or setting up Samba, NFS or scp for remote access.  
My preferred method is using SyncThing. It's a directory synchronization tool  
that's also working over the Internet. I have it setup so that a copy of the music  
directory on my computer is paired with the music directory on the player.  
See https://docs.syncthing.net/index.html

## Contributing
I appreciate contributions. Feel free to contact me.

## License
Distributed under the New BSD License, see LICENSE.txt.

### Project status
This is version 1.0 of the player. There are improvements to be made and also new features to be added (some more reasonable than others), but not any time soon.

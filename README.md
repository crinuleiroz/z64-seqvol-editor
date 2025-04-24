# Zelda64 Seqvol Editor
Edits the master volume of a Zelda64 sequence file, and optionally changes conditional jump messages to non-conditional jump messages.

## 🔧 How to Use
To use the script, use the following command in your terminal:
```
python <script_name.py> [-h] [file] [volume] [-j] [-g GAME]
```

### Terminal Arguments
| Argument | Description |
| --- | --- |
| `script_name` | The name of the script on your PC |
| `-h` | Displays the help message |
| `file` | The name of the `.ootrs`, `.mmrs`, `.seq`, `.aseq`, or `.zseq` file. |
| `volume` | The new volume value for the ASEQ Master Volume message. Value must be between 0 and 255 (decimal or hex). |
| `-j` | Tells the script to change conditional jump messages into non-conditional jump messages. |
| `-g GAME` | Determines the instruction set the script will use for a sequence file. |

> [!CAUTION]
> Script and file names containing spaces must be put into quotations. You can drag and drop both the script and the file you want to edit onto your terminal's window to add their path's as arguments instead of typing them out.

#### Terminal Help Message
The output of the help message is below:
```
usage: [>_] python Zelda64_Seqvol_Editor.v2025-02-24.py [-h] [file] [volume] [-j] [-g GAME]

This script allows a user to change a Zelda64 music file's master volume.

positional arguments:
  file             filename of the file to edit (must have one of the following extensions: .seq, .zseq, .aseq)
  volume           value to change all master volume messages to (must be a value between 0 and 255, or 0x00 and 0xFF)

options:
  -h, --help       show this help message and exit
  -j, --fix-jumps  use this arg to also fix any conditional jumps that may break sequences in rando
  -g, --game GAME  determines the instruction set the sequence was created to use
```

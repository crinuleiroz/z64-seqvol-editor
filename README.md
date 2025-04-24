# Zelda64 Seqvol Editor
Edits the master volume of a Zelda64 sequence file, and optionally changes conditional jump messages to non-conditional jump messages.

## 🔧 How to Use
To use the script, use the following command in your terminal:
```
python <script_name.py> [-h] [file] [volume] [-j] [-g GAME]
```

### 📥 Terminal Arguments
| Argument | Description |
| --- | --- |
| `-h` | Displays the help message in the terminal. |
| `file` | The `.ootrs`, `.mmrs`, `.seq`, `.aseq`, or `.zseq` file to be edited. |
| `volume` | New master volume value (0 to 255 in decimal or hex). |
| `-j` | Converts conditional jump messages into non-conditional ones. |
| `-g GAME` | Specifies the instruction set to use during sequence parsing. |

> [!CAUTION]
> If your script or file names contain spaces, they must be enclosed in quotes.

> [!TIP]
> You can drag and drop files onto the terminal window to automatically insert their paths (enclosed in quotes).

### ❓ Terminal Help Message
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

# Python script to parse the sequence header of a Zelda64 binary sequence file
# to modify the sequence volume and optionally fix potentially broken jump messages

CURRENT_VERSION = '2025.02.05'

#------------------#
# IMPORTS          #
#------------------#
import os, sys, argparse, math, datetime, time
import shutil
import zipfile
from enum import Enum, auto
from typing import Final, Tuple
import struct
import threading

# datetime is imported to create a unique name for the modified file
# shutil and zipfile are imported to handle packed music files
# struct is imported to handle sequence instruction reading
# threading is imported to add a nice animation while processes are happening

#------------------------#
# CONSTANTS              #
#------------------------#

# Create ANSI formatting for terminal messages
# ANSI COLORS: https://talyian.github.io/ansicolors/
# TERMINAL TEXT COLORS
RED        : Final = '\x1b[31m'
PINK_218   : Final = '\x1b[38;5;218m'
PINK_204   : Final = '\x1b[38;5;204m'
YELLOW     : Final = '\x1b[33m'
YELLOW_229 : Final = '\x1b[38;5;229m'
CYAN       : Final = '\x1b[36m'
BLUE_39    : Final = '\x1b[38;5;39m'
GRAY_245   : Final = '\x1b[38;5;245m'
GRAY_248   : Final = '\x1b[38;5;248m'
GREEN_79   : Final = '\x1b[38;5;79m'

# TERMINAL TEXT STYLES
BOLD      : Final = '\x1b[1m'
ITALIC    : Final = '\x1b[3m'
UNDERLINE : Final = '\x1b[4m'
STRIKE    : Final = '\x1b[9m'
RESET     : Final = '\x1b[0m' # Resets all text styles and colors

# TERMINAL CLEANERS
PL  : Final = '\x1b[F' # Move cursor to previous line
CL  : Final = '\x1b[K' # Clear line

# Spinner frames for the parsing spinner
SPINNER_FRAMES: Final = [
  "⢀⠀", "⡀⠀", "⠄⠀", "⢂⠀", "⡂⠀", "⠅⠀", "⢃⠀", "⡃⠀", "⠍⠀", "⢋⠀",
  "⡋⠀", "⠍⠁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩",
  "⠈⢙", "⠈⡙", "⢈⠩", "⡀⢙", "⠄⡙", "⢂⠩", "⡂⢘", "⠅⡘", "⢃⠨", "⡃⢐",
  "⠍⡐", "⢋⠠", "⡋⢀", "⠍⡁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙",
  "⠉⠙", "⠉⠩", "⠈⢙", "⠈⡙", "⠈⠩", "⠀⢙", "⠀⡙", "⠀⠩", "⠀⢘", "⠀⡘",
  "⠀⠨", "⠀⢐", "⠀⡐", "⠀⠠", "⠀⢀", "⠀⡀",
]

FILE_EXT : Final = [
  # Standalone sequences
  '.seq',   '.aseq',   '.zseq',
  # Packed Music Files
  '.ootrs', '.mmrs',
]

class SeqVersion(Enum):
  OOT = auto()
  MM  = auto()

GAME_VERSION : Final = (SeqVersion.OOT, SeqVersion.MM)

# Output messages
SEQ_HEADER_OUTPUT : list[str] = []

# These lists are to store addresses in case of duplicate message identifiers,
# because the parser can not handle storing them all to new variables
# Master Volume (SysEx) Addresses
MSTR_VOL_ADDR : list[int] = []

# ABS Jump Addresses
JUMP_ADDR     : list[int] = []
EQJUMP_ADDR   : list[int] = []
LTJUMP_ADDR   : list[int] = []
GTEQJUMP_ADDR : list[int] = []

# REL Jump Addresses
RJUMP_ADDR    : list[int] = []
REQJUMP_ADDR  : list[int] = []
RLTJUMP_ADDR  : list[int] = []

#------------------------#
# FUNCTIONS              #
#------------------------#
def START_THREAD(thread : threading.Thread, msg_type : str, start_msg : str, end_msg: str) -> None:
  """
  Creates a thread to indicate that a process is ongoing.

  Arguments:
      Thread: The thread to be started
      str: The header of the message
      str: The message to display while the thread is active
      str: The message to display when the process completes

  Returns:
      None
  """

  thread.start()
  i = 0

  print(msg_type)
  while thread.is_alive():
    print(f'  {GREEN_79}{SPINNER_FRAMES[i]}{RESET}', start_msg, end='\r', flush=True)
    i = (i + 1) % len(SPINNER_FRAMES)
    time.sleep(0.045)

  thread.join()
  print(f'{CL}', end_msg)

def SEQ_PARSE_OUTPUT(list):
  """
  Creates a formatted message string for printing sequence messages to console.

  Arguments:
      int: Address of the message
      int: Message identifier
      int: Message arguments (*args)

  Returns:
      str: String to print to console
  """

  start = f'''
{YELLOW}[SEQ HEADER COMMANDS]{RESET}:
  {BOLD}{GREEN_79}[  START SEQ SECTION  ]{RESET}
  {ITALIC}{BLUE_39}COMMAND         @ADDR: DATA{RESET}'''
  end = f'''  {BOLD}{RED}[   END SEQ SECTION   ]{RESET}'''

  print(start)
  for entry in list:
    print(entry)
    time.sleep(0.025)
  print(end)

def GET_MSG_STRING(addr : int, msg : int, *args : int) -> str:
  """
  Creates a formatted message string for printing sequence messages to console.

  Arguments:
      int: Address of the message
      int: Message identifier
      int: Message arguments (*args)

  Returns:
      str: String to print to console
  """

  hex_args = []

  if 0x1000 <= addr:
    hex_addr = f'@{hex(addr)[2:]}'
  elif 0x100 <= addr <= 0xFFF:
    hex_addr = f'@0{hex(addr)[2:]}'
  elif 0x10 <= addr <= 0xFF:
    hex_addr = f'@00{hex(addr)[2:]}'
  else:
    hex_addr = f'@000{hex(addr)[2:]}'

  if msg < 0x10:
    hex_msg = f'0{hex(msg)[2:]}'
  else:
    hex_msg = f'{hex(msg)[2:]}'

  for arg in args:
    x = f'{hex(arg)[2:]}'
    hex_args.append(x)

  if len(args) < 1:
    return f'{hex_addr}: {hex_msg}'.upper()
  elif len(args) == 1:
    return f'{hex_addr}: {hex_msg} {hex_args[0]}'.upper()
  elif len(args) == 2:
    return f'{hex_addr}: {hex_msg} {hex_args[0]} {hex_args[1]}'.upper()

def SEEK_ADDR(seq: str, addr: int):
  """
  Seeks the byte at the specified address.

  Arguments:
      str: Opened file
      int: Address of byte to seek
  """

  seq.seek(addr)

def READ_MSG(seq : str, offset : int) -> list[int]:
  """
  Reads a sequence message with no args.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
  """

  SEEK_ADDR(seq, offset)

  data = struct.unpack('>1B', seq.read(1))

  msg = [
    data[0],
  ]

  return msg

def READ_ARGVAR(seq : str, offset : int, arglen: str) -> Tuple[list[int], int, int]:
  """
  Reads a sequence message with a variable argument length.

  Arguments:
      str: Opened file
      int: Offset to the message
      int: Length of the argument

  Returns:
      list[int]: Unpacked structure of bytes
      int: Number of positions to move
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr = seq.tell() + 1

  if arglen & 0x80:
    data = struct.unpack('>1B1H', seq.read(3))

    msg_var = [
      data[0], data[1],
    ]

    pos = 3

  else:
    data = struct.unpack('>2B', seq.read(2))

    msg_var = [
      data[0], data[1],
    ]

    pos = 2

  return msg_var, pos, arg_addr

def READ_U8(seq : str, offset : int) -> Tuple[list[int], int]:
  """
  Reads a sequence message with one u8 argument.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr = seq.tell() + 1

  data = struct.unpack('>2B', seq.read(2))

  msg_u8 = [
    data[0], data[1],
  ]

  return msg_u8, arg_addr

def READ_U8x2(seq : str, offset : int) -> Tuple[list[int], int, int]:
  """
  Reads a sequence message with two u8 arguments.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
      int: Argument address
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr1 = seq.tell() + 1
  arg_addr2 = seq.tell() + 2

  data = struct.unpack('>3B', seq.read(3))

  msg_u8 = [
    data[0], data[1], data[2],
  ]

  return msg_u8, arg_addr1, arg_addr2

def READ_U8_U16(seq : str, offset : int) -> Tuple[list[int], int, int]:
  """
  Reads a sequence message with one u8 argument and one u16 argument.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
      int: Argument address
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr1 = seq.tell() + 1
  arg_addr2 = seq.tell() + 2

  data = struct.unpack('>2B1H', seq.read(4))

  msg_u8_u16 = [
    data[0], data[1], data[2],
  ]

  return msg_u8_u16, arg_addr1, arg_addr2

def READ_U16(seq : str, offset : int) -> Tuple[list[int], int]:
  """
  Reads a sequence message with one u16 argument.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr = seq.tell() + 1

  data = struct.unpack('>1B1H', seq.read(3))

  msg_u16 = [
    data[0], data[1],
  ]

  return msg_u16, arg_addr

def READ_S16_U8(seq : str, offset: int) -> Tuple[list[int], int, int]:
  """
  Reads a sequence message with one s16 argument and one u8 argument.

  Arguments:
      str: Opened file
      int: Offset to the message

  Returns:
      list[int]: Unpacked structure of bytes
      int: Argument address
      int: Argument address
  """

  SEEK_ADDR(seq, offset)
  arg_addr1 = seq.tell() + 1
  arg_addr2 = seq.tell() + 3

  data = struct.unpack('>1B1H1B', seq.read(4))

  msg_s16_u8 = [
    data[0], data[1], data[2],
  ]

  return msg_s16_u8, arg_addr1, arg_addr2

def WRITE_BIN(seq: str, addr: int, value: int) -> None:
  """
  Writes the address and input value to the sequence binary.

  Arguments:
      str: Opened sequence file
      int: Sequence message address
      int: New sequence message value

  Returns:
      None
  """
  seq.seek(addr)
  seq.write(value)

def AUTO_SEQ_EDIT(seq: str) -> None:
  """
  Initiates the default sequence editing process.

  Arguments:
      str: Opened sequence file

  Returns:
      None
  """
  for addr in MSTR_VOL_ADDR:
    input_vol = ARG_PARSER.CHECK_INPUT(ARG_PARSER.value)
    WRITE_BIN(seq, addr, input_vol)
    if 0x1000 <= addr:
      hex_addr = f'@{hex(addr)[2:]}'.upper()
    elif 0x100 <= addr <= 0xFFF:
      hex_addr = f'@0{hex(addr)[2:]}'.upper()
    elif 0x10 <= addr <= 0xFF:
      hex_addr = f'@00{hex(addr)[2:]}'.upper()
    else:
      hex_addr = f'@000{hex(addr)[2:]}'.upper()
    vol_string = int.from_bytes(input_vol, byteorder="big", signed=False)
    print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  Master volume at {PINK_218}{hex_addr}{RESET} successfully changed to: {PINK_218}{vol_string}{RESET} ({PINK_218}0x{hex(vol_string)[2:].upper()}{RESET})')

def MANUAL_SEQ_EDIT(seq: str) -> None:
  """
  Initiates the manual sequence editing process.

  Arguments:
      str: Opened sequence file

  Returns:
      None
  """
  for addr in MSTR_VOL_ADDR:
    input_vol = ''
    message = f'''
{BOLD}{YELLOW}[MANUAL INPUT VALUE]{RESET}:
  Enter value (e.g. 64, 0x40, 50%): '''
    print(message, end='')
    while type(input_vol) is not bytes:
      manual_vol = input()

      # Allow the user to exit if they wish to
      if manual_vol == 'exit':
        SysMsg.EXIT_MSG()

      input_vol = ARG_PARSER.CONVERT_INPUT(manual_vol)

      if type(input_vol) is bytes:
        WRITE_BIN(seq, addr, input_vol)
        if 0x1000 <= addr:
          hex_addr = f'@{hex(addr)[2:]}'.upper()
        elif 0x100 <= addr <= 0xFFF:
          hex_addr = f'@0{hex(addr)[2:]}'.upper()
        elif 0x10 <= addr <= 0xFF:
          hex_addr = f'@00{hex(addr)[2:]}'.upper()
        else:
          hex_addr = f'@000{hex(addr)[2:]}'.upper()
        vol_string = int.from_bytes(input_vol, byteorder="big", signed=False)
        # Remove input and print success, keep the console clean
        print(f'{PL}{CL}{PL}{CL}{PL}{CL}', end='', flush=True)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  Master volume at {PINK_218}{hex_addr}{RESET} successfully changed to: {PINK_218}{vol_string}{RESET} ({PINK_218}0x{hex(vol_string)[2:].upper()}{RESET})')
      else:
        # Do not print a new message each time, keep the console clean
        manual_vol = print(f'{PL}{CL}{PL}{CL}{PL}{CL}', message, end='', flush=True)

def FIX_JUMP(seq: str, addr: int) -> None:
  """
  Changes the jump message at the specified address to 0xFB.

  Arguments:
      str: Opened sequence file
      int: Sequence message address

  Returns:
      None
  """
  seq.seek(addr)
  b = b'\xFB' # Change to jump if not already jump
  seq.write(b)

def FIX_RJUMP(seq: str, addr: int) -> None:
  """
  Changes the jump message at the specified address to 0xF4.

  Arguments:
      str: Opened sequence file
      int: Sequence message address

  Returns:
      None
  """
  seq.seek(addr)
  b = b'\xF4' # Change to rjump if not already rjump
  seq.write(b)

#------------------------#
# CLASSES                #
#------------------------#

# SYSTEM MESSAGES
class SysMsg:
  """ Holds functions for various system messages. """

  def FILE_OPEN_FAILURE(exception) -> None:
    """
    Error thrown when parsing a sequence file fails.
    """
    print(f'\n{BOLD}{RED}[ERROR]{RESET}:\n  Failed to open file! Exception: {exception}')
    sys.exit(1)

  def SEQ_PARSE_FAILURE(exception) -> None:
    """
    Error thrown when parsing a sequence file fails.
    """
    print(f'\n{BOLD}{RED}[ERROR]{RESET}:\n  Failed to parse sequence! Exception: {exception}')
    sys.exit(1)

  def EXIT_MSG() -> None:
    """
    Message printed when user chooses to exit the process.
    """
    print(f'\n{BOLD}{RED}[EXITING]{RESET}:\n  Closing sequence and exiting process...')
    sys.exit(1)

  def COMPLETE_MSG(fixed_jumps : bool) -> None:
    """
    Message printed when the process is completed successfully
    """
    if fixed_jumps:
      print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed successfully! Master volume messages were changed and jumps were fixed.')
    else:
      print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed successfully! Master volume messages were changed.')
    sys.exit()

  def INCOMPLETE_MSG(no_vol : bool, fixed_jumps : bool) -> None:
    """
    Message printed when the process is incompleted successfully
    """
    if no_vol and fixed_jumps:
      print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed sucessfully! There were no master volume messages, but jumps were fixed.')
    else:
      print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  But nothing was changed... the poor parsed sequence...')
    sys.exit()

  def ARCHIVE_PACKED() -> None:
    """
    Message printed when the archive gets repacked
    """
    print(f'\n{BOLD}{YELLOW}[ARCHIVE REPACKED]{RESET}:\n  A new {archive.ext} file has been created with your changes as {PINK_218}{os.path.basename(archive.new_archive)}{RESET}.')


# ARG PARSER
class ArgParser:
  """ Creates a parser to run through CLI arguments """

  # def __init__(self):
    # self.parser      = None
    # self.file        = None
    # self.value       = None
    # self.fix_jumps   = None
    # self.seq_version = None

  def check_file(types: list[str], filename: str) -> str:
    """
    Checks if the input filename's extension is .seq, .aseq, .zseq, .ootrs, or .mmrs.

    Returns:
        str: The filename arg value
    """
    ext = os.path.splitext(filename)[1]
    if ext not in types:
      ArgParser.parser.error('sequence filename must end with one of the following extensions: .seq, .zseq, .aseq')
    return filename

  def check_vol(value: str) -> int:
    """
    Checks if the input volume arg can be converted into an integer.

    Returns:
        int: The volume arg value
    """
    if value.endswith('%'):
      vol = float(value[:-1])
      if vol > 200 or vol < 0:
        ArgParser.parser.error('volume percentage must be between 0% and 200%')
      else:
        return vol
    elif type(int(value, 0)) is int:
      vol = int(value, 0)
      if vol > 0xFF or vol < 0x00:
        ArgParser.parser.error('volume value must be between 0 and 255 (or 0x00 and 0xFF)')
      else:
        return vol

  def CHECK_INPUT(self, value:str) -> bytes:
    """
    Converts the original input volume to a byte.

    Arguments:
        str: Input volume argument

    Returns:
        bytes: Input value
    """
    if isinstance(value, float):
      result = int(math.ceil(value/100 * 127)) # not perfect rounding... but better than nothing
      input_vol = result.to_bytes(1, byteorder='big', signed=False)
    else:
      input_vol = int(value).to_bytes(1, byteorder='big', signed=False)
    return input_vol

  def CONVERT_INPUT(self, manual_vol: str) -> bytes:
    """
    Converts the manual input volume to a byte.

    Arguments:
        str: Manual input volume

    Returns:
        bytes: Manual input volume converted to byte
    """
    try:
      if manual_vol.endswith('%'):
        percent = float(manual_vol[:-1]) # handle decimals
        percent = int(math.ceil(percent/100 * 127)) # not perfect... but better than nothing
        input_vol = percent.to_bytes(1, byteorder='big', signed=False)
      elif manual_vol.startswith('0x') or manual_vol.startswith('0X'):
        input_vol = int(manual_vol, 0).to_bytes(1, byteorder='big', signed=False)
      else:
        input_vol = int(manual_vol).to_bytes(1, byteorder='big', signed=False)
      return input_vol
    except:
      #raise ValueError
      pass

  def get_args(self) -> None:
    """
    Gets the arguments from the CLI.

    Returns:
        None
    """

    self.parser = argparse.ArgumentParser(
      formatter_class=argparse.RawDescriptionHelpFormatter,
      usage=f'{GRAY_248}[>_]{RESET} {YELLOW_229}python{RESET} {BLUE_39}{sys.argv[0]}{RESET} {GRAY_245}[-h]{RESET} {BLUE_39}[file] [volume]{RESET} {GRAY_245}[-j] [-g GAME]{RESET}',
      description='''This script allows a user to change a Zelda64 music file's master volume.''',
    )
    self.parser.add_argument(
      'file',
      type=lambda s:ArgParser.check_file(FILE_EXT,s),
      help='filename of the file to edit (must have one of the following extensions: .seq, .zseq, .aseq)',
    )
    self.parser.add_argument(
      'volume',
      type=ArgParser.check_vol,
      help='value to change all master volume messages to (must be a value between 0 and 255, or 0x00 and 0xFF)',
    )
    self.parser.add_argument(
      '-j',
      '--fix-jumps',
      action='store_true',
      help='use this arg to also fix any conditional jumps that may break sequences in rando',
      required=False,
    )
    self.parser.add_argument(
      '-g',
      '--game',
      type=str,
      help="determines the instruction set the sequence was created to use",
      required=False,
      default='MM',
    )
    self.args = self.parser.parse_args()

    self.file         = self.args.file
    self.value        = self.args.volume
    self.fix_jumps    = self.args.fix_jumps
    self.game_version = {
      'OOT': SeqVersion.OOT,
      'OoT': SeqVersion.OOT,
      'oot': SeqVersion.OOT,
      'MM' : SeqVersion.MM,
      'mm' : SeqVersion.MM,
    }.get(self.args.game, None)

  def __str__(self) -> str:
    return f'Parsed Arguments = (file={self.file}, volume={self.value}, fix_jumps={self.fix_jumps}, game_version={self.game_version})'

# ARCHIVE HANDLER
class ArchiveHandler:
  """ Handle packing and unpacking archived files """

  # def __init__(self):
  #   self.filename    : str = ''
  #   self.ext         : str = ''
  #   self.new_archive : str = ''

  def unpack_archive(self) -> str:
    """
    Unpacks an .ootrs or .mmrs music file to a temp directory.

    Returns:
        str: Sequence file
    """

    # Give some extra time for the animation to play...
    time.sleep(1.5)

    # Thread would not work with an arg, so dupe here
    filepath = os.path.abspath(ARG_PARSER.file)

    basefolder = os.path.dirname(os.path.realpath(__file__))
    tempfolder = basefolder + '/temp'

    # Get the filename and extension of the file for later
    filename : str = os.path.splitext(ARG_PARSER.file)[0]
    ext      : str = os.path.splitext(ARG_PARSER.file)[1]

    # If there is already temp files, delete them
    if os.path.isdir(tempfolder):
      shutil.rmtree(tempfolder)

    if os.path.isdir(filename + '.zip'):
      os.remove(filename + '.zip')

    if os.path.isdir(filename + ext):
      os.remove(filename + ext)

    # Open the archive file and extract to the temp directory
    with zipfile.ZipFile(filepath, 'r') as zip_archive:
      zip_archive.extractall(tempfolder)

    self.seq_file: str = None # Init the seq_file string

    # Get the sequence file path
    for f in os.listdir(tempfolder):
      if f.endswith('.seq') or f.endswith('.aseq') or f.endswith('.zseq'):
        if self.seq_file is None:
          self.seq_file = f'{tempfolder}/{f}'
        else:
          # If there is more than one sequence, throw an exception
          raise Exception('Multiple sequence files detected! This should not happen, is it a sequence stuffed .mmrs file?')

    return self.seq_file

  def repack_archive(self):
    """
    Packs a temp directory into an .ootrs or .mmrs file.

    Returns:
        None
    """
    basefolder = os.path.dirname(os.path.realpath(__file__))
    tempfolder = basefolder + '/temp'

    # Get the filename and extension of the file for later
    self.filename : str = os.path.splitext(ARG_PARSER.file)[0]
    self.ext      : str = os.path.splitext(ARG_PARSER.file)[1]

    shutil.make_archive(self.filename, 'zip', tempfolder)

    # Create the new name for the archive using the current time, then move it to the final folder
    # Then wait 1 second so that the time will always be different in case of a new file
    self.new_archive = str(self.filename + f'.{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}' + self.ext)
    os.rename(self.filename + '.zip', f'{basefolder}/{self.new_archive}')
    time.sleep(1) # wait 1 second to continue, just in case

    # Remove the temp directory, we are done with it now
    if os.path.isdir(tempfolder):
      shutil.rmtree(tempfolder)

# SEQUENCE PARSER
class SeqParser:
  """ Parse Zelda64 binary sequence files """

  def __init__(self):
    self.pos = 0

  def OPEN_SEQUENCE(self, seq: str) -> str:
    """
    Tries to open the specified file, if it cannot be opened throws an error.

    Arguments:
        str: File to open

    Returns:
        str: Opened file
    """
    try:
      self.data = open(seq, 'r+b')
      return self.data
    except:
      print(f'{BOLD}{RED}[ERROR]{RESET}:\n  File could not be opened!')
      sys.exit(1)

  # There is definitely a better way to handle parsing, maybe a dataclass and a for loop?
  # Maybe a dict with the msg address, and a tuple with the values?
  # However, the data also needs to be edited... so maybe the simplest way is the best way... even if it takes more code...
  # I also want the output to be printed to the terminal...
  #
  # With how long this is, the class should be a separate file tbh... but single files are nice...
  def PARSE_SEQ(self, seq: str, version: SeqVersion) -> None:
    """
    Parses the SEQ section of a binary Zelda64 sequence file.

    Arguments:
        str: Opened sequence file to parse
        SeqVersion: Version of the sequence player

    Returns:
        None
    """

    pos = self.pos
    byte = seq.read(1)

    # Give some time for the thread animation to actually play... because parsing does not take long at all
    time.sleep(2.5)

    while (byte := seq.read(1)):
      SEEK_ADDR(seq, pos)
      byte = seq.read(1)

      # CONTROL FLOW
      # 0xFF: END
      if byte == b'\xFF':
        self.s_end_addr = seq.tell() - 1
        self.s_end = READ_MSG(seq, self.s_end_addr)

        self.s_end_msg = self.s_end[0]

        msg_string = GET_MSG_STRING(self.s_end_addr, self.s_end_msg)
        msg_string = f'  end             {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        break

      # 0xFE: Delay 1 Frame
      elif byte == b'\xFE':
        self.delay1_addr = seq.tell() - 1
        self.delay1 = READ_MSG(seq, self.delay1_addr)

        self.delay1_msg = self.delay1[0]

        msg_string = GET_MSG_STRING(self.delay1_addr, self.delay1_msg)
        msg_string = f'  delay1          {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0xFD: Delay n Frame(s)
      elif byte == b'\xFD':
        self.s_delay_addr = seq.tell() - 1
        self.s_delay_arglen   = int.from_bytes(seq.read(1), byteorder='big', signed=False)
        self.s_delay, n, self.s_delay_arg_addr = READ_ARGVAR(seq, self.s_delay_addr, self.s_delay_arglen)

        self.s_delay_msg = self.s_delay[0]
        self.s_delay_arg = self.s_delay[1]

        msg_string = GET_MSG_STRING(self.s_delay_addr, self.s_delay_msg, self.s_delay_arg)
        msg_string = f'  delay           {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += n

      # 0xFC: Call
      elif byte == b'\xFC':
        self.s_call_addr = seq.tell() - 1
        self.s_call, self.s_call_arg_addr = READ_U16(seq, self.s_call_addr)

        self.s_call_msg = self.s_call[0]
        self.s_call_arg = self.s_call[1]

        msg_string = GET_MSG_STRING(self.s_call_addr, self.s_call_msg, self.s_call_arg)
        msg_string = f'  call            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xFB: Jump Absolute
      elif byte == b'\xFB':
        self.s_jump_addr = seq.tell() - 1
        self.s_jump, self.s_jump_arg_addr = READ_U16(seq, self.s_jump_addr)

        self.s_jump_msg = self.s_jump[0]
        self.s_jump_arg = self.s_jump[1]

        msg_string = GET_MSG_STRING(self.s_jump_addr, self.s_jump_msg, self.s_jump_arg)
        msg_string = f'  jump            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xFA: Jump if Equal
      elif byte == b'\xFA':
        self.s_eqjump_addr = seq.tell() - 1
        self.s_eqjump, self.s_eqjump_arg_addr = READ_U16(seq, self.s_eqjump_addr)

        self.s_eqjump_msg = self.s_eqjump[0]
        self.s_eqjump_arg = self.s_eqjump[1]

        msg_string = GET_MSG_STRING(self.s_eqjump_addr, self.s_eqjump_msg, self.s_eqjump_arg)
        msg_string = f'{YELLOW}  eqjump          {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        EQJUMP_ADDR.append(self.s_eqjump_addr)
        pos += 3

      # 0xF9: Jump if Less Than
      elif byte == b'\xF9':
        self.s_ltjump_addr = seq.tell() - 1
        self.s_ltjump, self.s_ltjump_arg_addr = READ_U16(seq, self.s_ltjump_addr)

        self.s_ltjump_msg = self.s_ltjump[0]
        self.s_ltjump_arg = self.s_ltjump[1]

        msg_string = GET_MSG_STRING(self.s_ltjump_addr, self.s_ltjump_msg, self.s_ltjump_arg)
        msg_string = f'{YELLOW}  ltjump          {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        LTJUMP_ADDR.append(self.s_ltjump_addr)
        pos += 3

      # 0xF8: Loop
      elif byte == b'\xF8':
        self.s_loop_addr = seq.tell() - 1
        self.s_loop, self.loop_arg_addr = READ_U8(seq, self.s_loop_addr)

        self.s_loop_msg = self.s_loop[0]
        self.s_loop_arg = self.s_loop[1]

        msg_string = GET_MSG_STRING(self.s_loop_addr, self.s_loop_msg, self.s_loop_arg)
        msg_string = f'  loop            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xF7: Loop End
      elif byte == b'\xF7':
        self.s_loopend_addr = seq.tell() - 1
        self.s_loopend = READ_MSG(seq, self.s_loopend_addr)

        self.s_loopend_msg = self.s_loopend[0]

        msg_string = GET_MSG_STRING(self.s_loopend_addr, self.s_loopend_msg)
        msg_string = f'  loopend         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0xF6: Loop Break
      elif byte == b'\xF6':
        self.s_loopbreak_addr = seq.tell() - 1
        self.s_loopbreak = READ_MSG(seq, self.s_loopbreak_addr)

        self.s_loopbreak_msg = self.s_loopbreak[0]

        msg_string = GET_MSG_STRING(self.s_loopbreak_addr, self.s_loopbreak_msg)
        msg_string = f'  loopbreak       {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0xF5: Jump if Greater Than or Equal
      elif byte == b'\xF5':
        self.s_gteqjump_addr = seq.tell() - 1
        self.s_gteqjump, self.s_gteqjump_arg_addr = READ_U16(seq, self.s_gteqjump_addr)

        self.s_gteqjump_msg = self.s_gteqjump[0]
        self.s_gteqjump_arg = self.s_gteqjump[1]

        msg_string = GET_MSG_STRING(self.s_gteqjump_addr, self.s_gteqjump_msg, self.s_gteqjump_arg)
        msg_string = f'{YELLOW}  gteqjump        {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        GTEQJUMP_ADDR.append(self.s_gteqjump_addr)
        pos += 3

      # 0xF4: Jump Relative
      elif byte == b'\xF4':
        self.s_rjump_addr = seq.tell() - 1
        self.s_rjump, self.s_rjump_arg_addr = READ_U8(seq, self.s_rjump_addr)

        self.s_rjump_msg = self.s_rjump[0]
        self.s_rjump_arg = self.s_rjump[1]

        msg_string = GET_MSG_STRING(self.s_rjump_addr, self.s_rjump_msg, self.s_rjump_arg)
        msg_string = f'  rjump           {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xF3: Jump Relative if Equal
      elif byte == b'\xF3':
        self.s_reqjump_addr = seq.tell() - 1
        self.s_reqjump, self.s_reqjump_arg_addr = READ_U8(seq, self.s_reqjump_addr)

        self.s_reqjump_msg = self.s_reqjump[0]
        self.s_reqjump_arg = self.s_reqjump[1]

        msg_string = GET_MSG_STRING(self.s_reqjump_addr, self.s_reqjump_msg, self.s_reqjump_arg)
        msg_string = f'{YELLOW}  reqjump         {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        REQJUMP_ADDR.append(self.s_reqjump_addr)
        pos += 2

      # 0xF2: Jump Relative if Less Than
      elif byte == b'\xF2':
        self.s_rltjump_addr = seq.tell() - 1
        self.s_rltjump, self.s_rltjump_arg_addr = READ_U8(seq, self.s_rltjump_addr)

        self.s_rltjump_msg = self.s_rltjump[0]
        self.s_rltjump_arg = self.s_rltjump[1]

        msg_string = GET_MSG_STRING(self.s_rltjump_addr, self.s_rltjump_msg, self.s_rltjump_arg)
        msg_string = f'{YELLOW}  rltjump         {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        RLTJUMP_ADDR.append(self.s_rltjump_addr)
        pos += 2

      # NON-ARGBIT COMMANDS
      # 0xF1: Reserve Notes
      elif byte == b'\xF1':
        self.s_reservenotes_addr = seq.tell() - 1
        self.s_reservenotes, self.s_reservenotes_arg_addr = READ_U8(seq, self.s_reservenotes_addr)

        self.s_reservenotes_msg = self.s_reservenotes[0]
        self.s_reservenotes_arg = self.s_reservenotes[1]

        msg_string = GET_MSG_STRING(self.s_reservenotes_addr, self.s_reservenotes_msg, self.s_reservenotes_arg)
        msg_string = f'  reservenotes    {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xF0: Release Notes
      elif byte == b'\xF0':
        self.s_releasenotes_addr = seq.tell() - 1
        self.s_releasenotes, self.s_releasenotes_arg_addr = READ_U8(seq, self.s_releasenotes_addr)

        self.s_releasenotes_msg = self.s_releasenotes[0]
        self.s_releasenotes_arg = self.s_releasenotes[1]

        msg_string = GET_MSG_STRING(self.s_releasenotes_addr, self.s_releasenotes_msg, self.s_releasenotes_arg)
        msg_string = f'  releasenotes    {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xEF: Print 3 Bytes
      elif byte == b'\xEF':
        self.s_print3_addr = seq.tell() - 1
        self.s_print3, self.s_print3_arg_addr1, self.s_print3_arg_addr2 = READ_S16_U8(seq, self.s_print3_addr)

        self.s_print3_msg = self.s_print3[0]
        self.s_print3_arg1 = self.s_print3[1]
        self.s_print3_arg2 = self.s_print3[2]

        msg_string = GET_MSG_STRING(self.s_print3_addr, self.s_print3_msg, self.s_print3_arg1, self.s_print3_arg2)
        msg_string = f'  print3          {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 4

      # 0xDF: Transpose
      elif byte == b'\xDF':
        self.s_transpose_addr = seq.tell() - 1
        self.s_transpose, self.s_transpose_arg_addr = READ_U8(seq, self.s_transpose_addr)

        self.s_transpose_msg = self.s_transpose[0]
        self.s_transpose_arg = self.s_transpose[1]

        msg_string = GET_MSG_STRING(self.s_transpose_addr, self.s_transpose_msg, self.s_transpose_arg)
        msg_string = f'  transpose       {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xDE: Relative Transpose
      elif byte == b'\xDE':
        self.s_rtranspose_addr = seq.tell() - 1
        self.s_rtranspose, self.s_rtranspose_arg_addr = READ_U8(seq, self.s_rtranspose_addr)

        self.s_rtranspose_msg = self.s_rtranspose[0]
        self.s_rtranspose_arg = self.s_rtranspose[1]

        msg_string = GET_MSG_STRING(self.s_rtranspose_addr, self.s_rtranspose_msg, self.s_rtranspose_arg)
        msg_string = f'  rtranspose      {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xDD: Tempo
      elif byte == b'\xDD':
        self.s_tempo_addr = seq.tell() - 1
        self.s_tempo, self.s_tempo_arg_addr = READ_U8(seq, self.s_tempo_addr)

        self.s_tempo_msg = self.s_tempo[0]
        self.s_tempo_arg = self.s_tempo[1]

        msg_string = GET_MSG_STRING(self.s_tempo_addr, self.s_tempo_msg, self.s_tempo_arg)
        msg_string = f'  tempo           {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xDC: Add Tempo
      elif byte == b'\xDC':
        self.s_addtempo_addr = seq.tell() - 1
        self.s_addtempo, self.s_addtempo_arg_addr = READ_U8(seq, self.s_addtempo_addr)

        self.s_addtempo_msg = self.s_addtempo[0]
        self.s_addtempo_arg = self.s_addtempo[1]

        msg_string = GET_MSG_STRING(self.s_addtempo_addr, self.s_addtempo_msg, self.s_addtempo_arg)
        msg_string = f'  addtempo        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xDB: Master Volume (SysEx)
      elif byte == b'\xDB':
        self.s_mstrvol_addr = seq.tell() - 1
        self.s_mstrvol, self.s_mstrvol_arg_addr = READ_U8(seq, self.s_mstrvol_addr)

        self.s_mstrvol_msg = self.s_mstrvol[0]
        self.s_mstrvol_arg = self.s_mstrvol[1]

        msg_string = GET_MSG_STRING(self.s_mstrvol_addr, self.s_mstrvol_msg, self.s_mstrvol_arg)
        msg_string = f'{PINK_218}  mstrvol         {msg_string}{RESET}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        MSTR_VOL_ADDR.append(self.s_mstrvol_arg_addr)
        pos += 2

      # 0xDA: Volume Fade
      elif byte == b'\xDA':
        self.s_fade_addr = seq.tell() - 1
        self.s_fade, self.fade_arg_addr1, self.s_fade_arg_addr2 = READ_U8_U16(seq, self.s_fade_addr)

        self.s_fade_msg = self.s_fade[0]
        self.s_fade_arg1 = self.s_fade[1]
        self.s_fade_arg2 = self.s_fade[2]

        msg_string = GET_MSG_STRING(self.s_fade_addr, self.s_fade_arg1, self.s_fade_arg2)
        msg_string = f'  fade            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xD9: Master Expression
      elif byte == b'\xD9':
        self.s_mstrexpression_addr = seq.tell() - 1
        self.s_mstrexpression, self.s_mstrexpression_arg_addr = READ_U8(seq, self.s_mstrexpression_addr)

        self.s_mstrexpression_msg = self.s_mstrexpression[0]
        self.s_mstrexpression_arg = self.s_mstrexpression[1]

        msg_string = GET_MSG_STRING(self.s_mstrexpression_addr, self.s_mstrexpression_msg, self.s_mstrexpression_arg)
        msg_string = f'  mstrexpression  {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xD7: Enable Channel
      elif byte == b'\xD7':
        self.s_enablechan_addr = seq.tell() - 1
        self.s_enablechan, self.s_enablechan_arg_addr = READ_U16(seq, self.s_enablechan_addr)

        self.s_enablechan_msg = self.s_enablechan[0]
        self.s_enablechan_arg = self.s_enablechan[1]

        msg_string = GET_MSG_STRING(self.s_enablechan_addr, self.s_enablechan_msg, self.s_enablechan_arg)
        msg_string = f'  enablechan      {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xD6: Disable Channel
      elif byte == b'\xD6':
        self.s_disablechan_addr = seq.tell() - 1
        self.s_disablechan, self.s_disablechan_arg_addr = READ_U16(seq, self.s_disablechan_addr)

        self.s_disablechan_msg = self.s_disablechan[0]
        self.s_disablechan_arg = self.s_disablechan[1]

        msg_string = GET_MSG_STRING(self.s_disablechan_addr, self.s_disablechan_msg, self.s_disablechan_arg)
        msg_string = f'  disablechan     {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xD5: Mute Scale
      elif byte == b'\xD5':
        self.s_mutescale_addr = seq.tell() - 1
        self.s_mutescale, self.s_mutescale_arg_addr = READ_U8(seq, self.s_mutescale_addr)

        self.s_mutescale_msg = self.s_mutescale[0]
        self.s_mutescale_arg = self.s_mutescale[1]

        msg_string = GET_MSG_STRING(self.s_mutescale_addr, self.s_mutescale_msg, self.s_mutescale_arg)
        msg_string = f'  mutescale       {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xD4: Mute Sequence
      elif byte == b'\xD4':
        self.s_mute_addr = seq.tell() - 1
        self.s_mute = READ_MSG(seq, self.s_mute_addr)

        self.s_mute_msg = self.s_mute[0]

        msg_string = GET_MSG_STRING(self.s_mute_addr, self.s_mute_msg)
        msg_string = f'  mute            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0xD3: Mute Behavior
      elif byte == b'\xD3':
        self.s_mutebhv_addr = seq.tell() - 1
        self.s_mutebhv, self.s_mutebhv_arg_addr = READ_U8(seq, self.s_mutebhv_addr)

        self.s_mutebhv_msg = self.s_mutebhv[0]
        self.s_mutebhv_arg = self.s_mutebhv[1]

        msg_string = GET_MSG_STRING(self.s_mutebhv_addr, self.s_mutebhv_msg, self.s_mutebhv_arg)
        msg_string = f'  mutebhv         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xD2: Load Short Velocity Table
      elif byte == b'\xD2':
        self.s_loadshortvel_addr = seq.tell() - 1
        self.s_loadshortvel, self.s_loadshortvel_arg_addr = READ_U16(seq, self.s_loadshortvel_addr)

        self.s_loadshortvel_msg = self.s_loadshortvel[0]
        self.s_loadshortvel_arg = self.s_loadshortvel[1]

        msg_string = GET_MSG_STRING(self.s_loadshortvel_addr, self.s_loadshortvel_msg, self.s_loadshortvel_arg)
        msg_string = f'  loadshortvel    {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xD1: Load Short Gate Table
      elif byte == b'\xD1':
        self.loadshortgate_addr = seq.tell() - 1
        self.loadshortgate, self.loadshortgate_arg_addr = READ_U16(seq, self.loadshortgate_addr)

        self.loadshortgate_msg = self.loadshortgate[0]
        self.loadshortgate_arg = self.loadshortgate[1]

        msg_string = GET_MSG_STRING(self.loadshortgate_addr, self.loadshortgate_msg, self.loadshortgate_arg)
        msg_string = f'  loadshortgate   {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xD0:
      elif byte == b'\xD0':
        self.s_notealloc_addr = seq.tell() - 1
        self.s_notealloc, self.s_notealloc_arg_addr = READ_U8(seq, self.s_notealloc_addr)

        self.s_notealloc_msg = self.s_notealloc[0]
        self.s_notealloc_arg = self.s_notealloc[1]

        msg_string = GET_MSG_STRING(self.s_notealloc_addr, self.s_notealloc_msg, self.s_notealloc_arg)
        msg_string = f'  notealloc       {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xCE:
      elif byte == b'\xCE':
        self.s_rand_addr = seq.tell() - 1
        self.s_rand, self.s_rand_arg_addr = READ_U8(seq, self.s_rand_addr)

        self.s_rand_msg = self.s_rand[0]
        self.s_rand_arg = self.s_rand[1]

        msg_string = GET_MSG_STRING(self.s_rand_addr, self.s_rand_msg, self.s_rand_arg)
        msg_string = f'  rand            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xCD:
      elif byte == b'\xCD':
        self.s_dyncall_addr = seq.tell() - 1
        self.s_dyncall, self.s_dyncall_arg_addr = READ_U16(seq, self.s_dyncall_addr)

        self.s_dyncall_msg = self.s_dyncall[0]
        self.s_dyncall_arg = self.s_dyncall[1]

        msg_string = GET_MSG_STRING(self.s_dyncall_addr, self.s_dyncall_msg, self.s_dyncall_arg)
        msg_string = f'  dyncall         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xCC:
      elif byte == b'\xCC':
        self.s_load_addr = seq.tell() - 1
        self.s_load, self.s_load_arg_addr = READ_U8(seq, self.s_load_addr)

        self.s_load_msg = self.s_load[0]
        self.s_load_arg = self.s_load[1]

        msg_string = GET_MSG_STRING(self.s_load_addr, self.s_load_msg, self.s_load_arg)
        msg_string = f'  load            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xC9: Bitwise Operator &
      elif byte == b'\xC9':
        self.s_and_addr = seq.tell() - 1
        self.s_and, self.s_and_arg_addr = READ_U8(seq, self.s_and_addr)

        self.s_and_msg = self.s_and[0]
        self.s_and_arg = self.s_and[1]

        msg_string = GET_MSG_STRING(self.s_and_addr, self.s_and_msg, self.s_and_arg)
        msg_string = f'  and             {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xC8
      elif byte == b'\xC8':
        self.s_sub_addr = seq.tell() - 1
        self.s_sub, self.s_sub_arg_addr = READ_U8(seq, self.s_sub_addr)

        self.s_sub_msg = self.s_sub[0]
        self.s_sub_arg = self.s_sub[1]

        msg_string = GET_MSG_STRING(self.s_sub_addr, self.s_sub_msg, self.s_sub_arg)
        msg_string = f'  sub             {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 2

      # 0xC7:
      elif byte == b'\xC7':
        self.s_storeseq_addr = seq.tell() - 1
        self.s_storeseq, self.s_storeseq_arg_addr1, self.s_storeseq_arg_addr2 = READ_U8_U16(seq, self.s_storeseq_addr)

        self.s_storeseq_msg = self.s_storeseq[0]
        self.s_storeseq_arg1 = self.s_storeseq[1]
        self.s_storeseq_arg2 = self.s_storeseq[2]

        msg_string = GET_MSG_STRING(self.s_storeseq_addr, self.s_storeseq_msg, self.s_storeseq_arg1, self.s_storeseq_arg2)
        msg_string = f'  storeseq        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 4

      # 0xC6:
      elif byte == b'\xC6':
        self.s_stop_addr = seq.tell() - 1
        self.s_stop = READ_MSG(seq, self.s_stop_addr)

        self.s_stop_msg = self.s_stop[0]

        msg_string = GET_MSG_STRING(self.s_stop_addr, self.s_stop_msg)
        msg_string = f'  stop            {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0xC5: Script Counter
      elif byte == b'\xC5':
        self.s_scriptctr_addr = seq.tell() - 1
        self.s_scriptctr, self.s_scriptctr_arg_addr = READ_U16(seq, self.s_scriptctr_addr)

        self.s_scriptctr_msg = self.s_scriptctr[0]
        self.s_scriptctr_arg = self.s_scriptctr[1]

        msg_string = GET_MSG_STRING(self.s_scriptctr_addr, self.s_scriptctr_msg, self.s_scriptctr_arg)
        msg_string = f'  scriptctr        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xC4: Call Sequence
      elif byte == b'\xC4':
        self.s_callseq_addr = seq.tell() - 1
        self.s_callseq, self.s_callseq_arg_addr1, self.s_callseq_arg_addr2 = READ_U8x2(seq, self.s_callseq_addr)

        self.s_callseq_msg = self.s_callseq[0]
        self.s_callseq_arg1 = self.s_callseq[1]
        self.s_callseq_arg2 = self.s_callseq[2]

        msg_string = GET_MSG_STRING(self.s_callseq_addr, self.s_callseq_msg, self.s_callseq_arg1, self.s_callseq_arg2)
        msg_string = f'  callseq         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # MM Only Command
      # 0xC3: mutechan
      elif byte == b'\xC3' and version == SeqVersion.MM:
        self.s_mutechan_addr = seq.tell() - 1
        self.s_mutechan, self.s_mutechan_arg_addr = READ_U16(seq, self.s_mutechan_addr)

        self.s_mutechan_msg = self.s_mutechan[0]
        self.s_mutechan_arg = self.s_mutechan[1]

        msg_string = GET_MSG_STRING(self.s_mutechan_addr, self.s_mutechan_msg, self.s_mutechan_arg)
        msg_string = f'  mutechan         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # MM Only Command
      # 0xC2: unk
      elif byte == b'\xC2' and version == SeqVersion.MM:
        msg_string = f'  unk_msg           @???? ?? ?? ??'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # ARGBITS MESSAGES
      # 0x00 to 0x0F: Test Channel
      elif b'\x00' <= byte <= b'\x0F':
        self.s_testchan_addr = seq.tell() - 1
        self.s_testchan = READ_MSG(seq, self.s_testchan_addr)

        self.s_testchan_msg = self.s_testchan[0]

        msg_string = GET_MSG_STRING(self.s_testchan_addr, self.s_testchan_msg)
        msg_string = f'  testchan        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0x40 to 0x4F: Stop Channel
      elif b'\x40' <= byte <= b'\x4F':
        self.s_stopchan_addr = seq.tell() - 1
        self.s_stopchan = READ_MSG(seq, self.s_stopchan_addr)

        self.s_stopchan_msg = self.s_stopchan[0]

        msg_string = GET_MSG_STRING(self.s_stopchan_addr, self.s_stopchan_msg)
        msg_string = f'  stopchan        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0x50 to 0x5F: Sub IO
      elif b'\x50' <= byte <= b'\x5F':
        self.s_subio_addr = seq.tell() - 1
        self.s_subio = READ_MSG(seq, self.s_subio_addr)

        self.s_subio_msg = self.s_subio[0]

        msg_string = GET_MSG_STRING(self.s_subio_addr, self.s_subio_msg)
        msg_string = f'  subio           {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0x60 to 0x6F: Load Resource
      elif b'\x60' <= byte <= b'\x6F':
        self.s_loadres_addr = seq.tell() - 1
        self.s_loadres, self.s_loadres_arg_addr1, self.s_loadres_arg_addr2 = READ_U8x2(seq, self.s_loadres_addr)

        self.s_loadres_msg = self.s_loadres[0]
        self.s_loadres_arg1 = self.s_loadres[1]
        self.s_loadres_arg2 = self.s_loadres[2]

        msg_string = GET_MSG_STRING(self.s_loadres_addr, self.s_loadres_msg, self.s_loadres_arg1, self.s_loadres_arg2)
        msg_string = f'  loadres         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0x70 to 0x7F: Store IO
      elif b'\x70' <= byte <= b'\x7F':
        self.s_storeio_addr = seq.tell() - 1
        self.s_storeio = READ_MSG(seq, self.s_storeio_addr)

        self.s_storeio_msg = self.s_storeio[0]

        msg_string = GET_MSG_STRING(self.s_storeio_addr, self.s_storeio_msg)
        msg_string = f'  storeio         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0x80 to 0x8F: Load IO
      elif b'\x80' <= byte <= b'\x8F':
        self.s_loadio_addr = seq.tell() - 1
        self.s_loadio = READ_MSG(seq, self.s_loadio_addr)

        self.s_loadio_msg = self.s_loadio[0]

        msg_string = GET_MSG_STRING(self.s_loadio_addr, self.s_loadio_msg)
        msg_string = f'  loadio          {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 1

      # 0x90 to 0x9F: Load Channel Absolute
      elif b'\x90' <= byte <= b'\x9F':
        self.s_loadchan_addr = seq.tell() - 1
        self.s_loadchan, self.s_loadchan_arg_addr = READ_U16(seq, self.s_loadchan_addr)

        self.s_loadchan_msg = self.s_loadchan[0]
        self.s_loadchan_arg = self.s_loadchan[1]

        msg_string = GET_MSG_STRING(self.s_loadchan_addr, self.s_loadchan_msg, self.s_loadchan_arg)
        msg_string = f'  loadchan        {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0xA0 to 0xAF: Load Channel Relative
      elif b'\xA0' <= byte <= b'\xAF':
        self.s_rloadchan_addr = seq.tell() - 1
        self.s_rloadchan, self.s_rloadchan_arg_addr = READ_U16(seq, self.s_rloadchan_addr)

        self.s_rloadchan_msg = self.s_rloadchan[0]
        self.s_rloadchan_arg = self.s_rloadchan[1]

        msg_string = GET_MSG_STRING(self.s_rloadchan_addr, self.s_rloadchan_msg, self.s_rloadchan_arg)
        msg_string = f'  rloadchan       {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 3

      # 0x00 to 0x0F: Load Sequence
      elif b'\xB0' <= byte <= b'\xBF':
        self.s_loadseq_addr = seq.tell() - 1
        self.s_loadseq, self.s_loadseq_arg_addr1, self.s_loadseq_arg_addr2 = READ_U8_U16(seq, self.s_loadseq_addr)

        self.s_loadseq_msg = self.s_loadseq[0]
        self.s_loadseq_arg1 = self.s_loadseq[1]
        self.s_loadseq_arg2 = self.s_loadseq[2]

        msg_string = GET_MSG_STRING(self.s_loadseq_addr, self.s_loadseq_msg, self.s_loadseq_arg1, self.s_loadseq_arg2)
        msg_string = f'  loadseq         {msg_string}'

        SEQ_HEADER_OUTPUT.append(msg_string)
        pos += 4

      else:
        pos += 1

  # unused lol
  def PARSE_CHAN(seq: str, version: SeqVersion) -> None:
    """
    Parses the CHAN section of a binary Zelda64 sequence file.

    Arguments:
        str: Opened sequence file to parse
        SeqVersion: Version of the sequence player

    Returns:
        None
    """
    raise NotImplementedError

  # unused lol
  def PARSE_LAYER(seq: str, version: SeqVersion) -> None:
    """
    Parses the LAYER section of a binary Zelda64 sequence file.

    Arguments:
        str: Opened sequence file to parse
        SeqVersion: Version of the sequence player

    Returns:
        None
    """
    raise NotImplementedError

# Public Static Void Main ;p
def main() -> None:
  """ The main function of the module """
  global no_vol, fixed_jumps

  #------------------------#
  # SEQUENCE PARSING SETUP #
  #------------------------#
  sequence = SeqParser()

  try:
    if archive.seq_file:
      seq = sequence.OPEN_SEQUENCE(archive.seq_file)
    else:
      seq = sequence.OPEN_SEQUENCE(seq_file)
  except Exception as e:
    SysMsg.FILE_OPEN_FAILURE(e)
  try:
    msg_type = f'{BOLD}{YELLOW}[PARSING SEQUENCE]{RESET}:'
    start_msg = 'Parsing SEQ section of sequence file to find messages...'
    end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[PARSING COMPLETED]{RESET}:\n  Parsing completed, listing messages in the SEQ section.'

    # Create and start the thread
    parser_thread = threading.Thread(target=sequence.PARSE_SEQ, args=(sequence.data, ARG_PARSER.game_version))
    START_THREAD(parser_thread, msg_type, start_msg, end_msg)

    # Output the commands found in the sequence section
    SEQ_PARSE_OUTPUT(SEQ_HEADER_OUTPUT)
    #print(f'\n{BOLD}{YELLOW}[PARSING COMPLETED]{RESET}:\n  Parsing of sequence section completed.')
  except Exception as e:
    SysMsg.SEQ_PARSE_FAILURE(e)

  #------------------------#
  # WRITE TO BIN           #
  #------------------------#
  if len(MSTR_VOL_ADDR) > 1:
    answer: str = ''
    print(f'''
{CYAN}[INFO]{RESET}:
  Multiple master volume messages have been found in the sequence.
  Do you wish to modify master volume messages automatically or manually?

  {ITALIC}Options: auto, manual, exit{RESET}
  Input: ''', end='')

    # Use a list instead of manually inputting options in the conditional
    options = [
      'auto', 'Auto', 'AUTO',
      'manual', 'Manual', 'MANUAL',
      'exit', 'Exit', 'EXIT',
    ]

    while answer not in options:
      answer = input()

      if answer in options[0:3]:
        AUTO_SEQ_EDIT(seq)
        break # Return from loop after function completes — DO NOT REMOVE!

      elif answer in options[3:6]:
        MANUAL_SEQ_EDIT(seq)
        break # Return from loop after function completes — DO NOT REMOVE!

      elif answer in options[6:8]:
        SysMsg.EXIT_MSG()

      else:
        # Do not print a new message each time, keep the console clean
        answer = print(f'{PL}{CL}  Input: ', end='', flush=True)

  elif MSTR_VOL_ADDR:
    AUTO_SEQ_EDIT(seq)

  else:
    print(f'\n{BOLD}{RED}[WARNING]{RESET}:\n  Could not find master volume message in SEQ...\n  This script cannot insert a master volume message, so the master volume cannot be changed.')
    no_vol = True

  if ARG_PARSER.fix_jumps:
    if len(EQJUMP_ADDR) > 0:
      for addr in EQJUMP_ADDR:
        FIX_JUMP(seq, addr)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  eqjump at {hex(addr)} successfully changed to: jump')
    if len(LTJUMP_ADDR) > 0:
      for addr in LTJUMP_ADDR:
        FIX_JUMP(seq, addr)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  ltjump at {hex(addr)} successfully changed to: jump')
    if len(GTEQJUMP_ADDR) > 0:
      for addr in GTEQJUMP_ADDR:
        FIX_JUMP(seq, addr)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  gteqjump at {hex(addr)} successfully changed to: jump')
    if len(REQJUMP_ADDR) > 0:
      for addr in REQJUMP_ADDR:
        FIX_JUMP(seq, addr)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  reqjump at {hex(addr)} successfully changed to: jump')
    if len(RLTJUMP_ADDR) > 0:
      for addr in RLTJUMP_ADDR:
        FIX_JUMP(seq, addr)
        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  rltjump at {hex(addr)} successfully changed to: jump')
    fixed_jumps = True

if __name__ == '__main__':
  #------------------------#
  # GLOBAL VARIABLES       #
  #------------------------#
  no_vol      = False
  fixed_jumps = False

  #------------------------#
  # ARGPARSER SETUP        #
  #------------------------#
  ARG_PARSER: ArgParser = ArgParser()
  ARG_PARSER.get_args()

  # Throw an error and exit if game version is incorrect
  if ARG_PARSER.game_version is None:
    print(f'{RED}[ERROR]{RESET}:\n  Game argument must be one of the following values: OOT, OoT, oot, MM, or mm.')
    sys.exit(1)

  # Get the full filepath of the input file
  filepath = os.path.abspath(ARG_PARSER.file)
  filename = os.path.basename(ARG_PARSER.file)

  # Initialize the archive handler and sequence path
  archive : ArchiveHandler = ArchiveHandler()
  archive.seq_file = None

  if filepath.endswith('.ootrs') or filepath.endswith('.mmrs'):
    # Fix game versions if the user did not use conditional argument,
    # the ext tells which version to expect instead
    if filepath.endswith('.ootrs') and ARG_PARSER.game_version != SeqVersion.OOT:
      ARG_PARSER.game_version = SeqVersion.OOT
    else:
      ARG_PARSER.game_version = SeqVersion.MM

    # Start the process
    msg_type = f'{BOLD}{YELLOW}[UNPACKING ARCHIVE]{RESET}:'
    start_msg = 'Unpacking the packed music files into a temp directory...'
    end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[ARCHIVE UNPACKED]{RESET}:'

    # Create and start the thread
    unpack_thread = threading.Thread(target=archive.unpack_archive)
    START_THREAD(unpack_thread, msg_type, start_msg, end_msg)
    print(f'  Music files in {PINK_218}{filename}{RESET} unpacked into temp directory, beginning parsing...\n')

    main()

    msg_type = f'\n{BOLD}{YELLOW}[PACKING ARCHIVE]{RESET}:'
    start_msg = 'Repacking extracted files and deleting temp directory...'
    end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[ARCHIVE REPACKED]{RESET}:'

    # Create and start the thread
    repack_thread = threading.Thread(target=archive.repack_archive)
    START_THREAD(repack_thread, msg_type, start_msg, end_msg)
    print(f'  A new {archive.ext} file has been created with your changes as {PINK_218}{os.path.basename(archive.new_archive)}{RESET}.')

  else:
    # The sequence is not in a temp directory, just use the filepath variable
    seq_file = filepath

    main()

  # Final system messages
  if not no_vol:
    SysMsg.COMPLETE_MSG(fixed_jumps)
  else:
    SysMsg.INCOMPLETE_MSG(no_vol, fixed_jumps)

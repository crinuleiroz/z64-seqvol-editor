# Python script to parse the sequence header of a Zelda64 binary sequence file
# to modify the sequence volume and optionally fix potentially broken jump messages

import argparse
import sys
import tempfile
import zipfile
import time
import datetime
import os
from dataclasses import dataclass
import threading
import struct
from typing import Final, Tuple, Callable, Optional, List
from enum import Enum, auto
import shutil
import math


CURRENT_VERSION = '2025.04.24'

# Create ANSI formatting for terminal messages
# ANSI COLORS: https://talyian.github.io/ansicolors/
# TERMINAL TEXT COLORS
RED: Final        = '\x1b[31m'
PINK_218: Final   = '\x1b[38;5;218m'
PINK_204: Final   = '\x1b[38;5;204m'
YELLOW: Final     = '\x1b[33m'
YELLOW_229: Final = '\x1b[38;5;229m'
CYAN: Final       = '\x1b[36m'
BLUE_39: Final    = '\x1b[38;5;39m'
GRAY_245: Final   = '\x1b[38;5;245m'
GRAY_248: Final   = '\x1b[38;5;248m'
GREEN_79: Final   = '\x1b[38;5;79m'

# TERMINAL TEXT STYLES
BOLD: Final      = '\x1b[1m'
ITALIC: Final    = '\x1b[3m'
UNDERLINE: Final = '\x1b[4m'
STRIKE: Final    = '\x1b[9m'
RESET: Final     = '\x1b[0m'  # Resets all text styles and colors

# TERMINAL CLEANERS
PL: Final = '\x1b[F'  # Move cursor to previous line
CL: Final = '\x1b[K'  # Clear line

# Spinner frames for the parsing spinner
SPINNER_FRAMES: Final = [
    "⢀⠀", "⡀⠀", "⠄⠀", "⢂⠀", "⡂⠀", "⠅⠀", "⢃⠀", "⡃⠀", "⠍⠀", "⢋⠀",
    "⡋⠀", "⠍⠁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩",
    "⠈⢙", "⠈⡙", "⢈⠩", "⡀⢙", "⠄⡙", "⢂⠩", "⡂⢘", "⠅⡘", "⢃⠨", "⡃⢐",
    "⠍⡐", "⢋⠠", "⡋⢀", "⠍⡁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙",
    "⠉⠙", "⠉⠩", "⠈⢙", "⠈⡙", "⠈⠩", "⠀⢙", "⠀⡙", "⠀⠩", "⠀⢘", "⠀⡘",
    "⠀⠨", "⠀⢐", "⠀⡐", "⠀⠠", "⠀⢀", "⠀⡀",
]

FILE_EXT: Final = [
    # Standalone sequences
    '.seq',   '.aseq',   '.zseq',
    # Packed Music Files
    '.ootrs', '.mmrs',
]


class SeqVersion(Enum):
    OOT = auto()
    MM = auto()


GAME_VERSION: Final = (SeqVersion.OOT, SeqVersion.MM)


@dataclass
class MessageData:
    arg_addr_1: Optional[int] = None
    arg_addr_2: Optional[int] = None
    msg_byte: int = 0xFF
    arg_1: Optional[Tuple[int, str]] = None
    arg_2: Optional[Tuple[int, str]] = None
    pos: int = 2


# Output messages
SEQ_HEADER_OUTPUT: list[str] = []

# Master Volume (SysEx) Addresses
MSTR_VOL_ADDR: list[int] = []

# ABS Jump Addresses
JUMP_ADDR: list[int] = []
EQJUMP_ADDR: list[int] = []
LTJUMP_ADDR: list[int] = []
GTEQJUMP_ADDR: list[int] = []

# REL Jump Addresses
RJUMP_ADDR: list[int] = []
REQJUMP_ADDR: list[int] = []
RLTJUMP_ADDR: list[int] = []


def start_thread(thread: threading.Thread, msg_type: str, start_msg: str, end_msg: str) -> None:
    """ Creates a thread to indicate that a process is ongoing """

    thread.start()
    i = 0

    print(msg_type)
    while thread.is_alive():
        print(f'  {GREEN_79}{SPINNER_FRAMES[i]}{RESET}', start_msg, end='\r', flush=True)
        i = (i + 1) % len(SPINNER_FRAMES)
        time.sleep(0.045)

    thread.join()
    print(f'{CL}', end_msg)


def seq_parse_output(list):
    """ Creates a formatted message string for printing sequence messages to console """

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


def format_addr(addr: int) -> str:
    return f'@{addr:04X}'[-5:]


def format_args(args: Tuple[Optional[Tuple[int, str]], ...]) -> str:
    return ' '.join(
        f'{val:04X}' if size in ('u16', 's16') else f'{val:02X}'
        for arg in args if arg is not None
        for val, size in [arg]
    )


def get_msg_string(addr: int, msg: int | None, *args: int) -> str:
    """ Creates a formatted message string for printing sequence messages to console """
    if msg is None:
        return '  unk_msg           @???? ?? ?? ??'

    hex_addr = format_addr(addr)
    hex_msg = f'{msg:02X}'
    hex_args = format_args(args)

    spacing = ' ' if hex_args else ''
    return f'{hex_addr}: {hex_msg}{spacing}{hex_args}'.upper()


def seek_addr(seq: str, addr: int):
    """ Seeks the byte at the specified address """

    seq.seek(addr)


def read_msg(seq: str, offset: int) -> Tuple[int]:
    """ Reads a sequence message with no args """

    seek_addr(seq, offset)

    data = struct.unpack('>1B', seq.read(1))

    return MessageData(msg_byte=data[0])


def read_argvar(seq: str, offset: int, arglen: str) -> Tuple[int, int, int]:
    """ Reads a sequence message with a variable argument length """

    seek_addr(seq, offset)
    arg_addr = seq.tell() + 1

    if arglen & 0x80:
        data = struct.unpack('>1B1H', seq.read(3))
        return MessageData(arg_addr_1=arg_addr, msg_byte=data[0], arg_1=(data[1], 'u16'), pos=3)

    else:
        data = struct.unpack('>2B', seq.read(2))
        return MessageData(arg_addr_1=arg_addr, msg_byte=data[0], arg_1=(data[1], 'u8'))


def read_u8(seq: str, offset: int) -> Tuple[int, int, int]:
    """ Reads a sequence message with one u8 argument """

    seek_addr(seq, offset)
    arg_addr = seq.tell() + 1

    data = struct.unpack('>2B', seq.read(2))

    return MessageData(arg_addr_1=arg_addr, msg_byte=data[0], arg_1=(data[1], 'u8'))


def read_u8x2(seq: str, offset: int) -> Tuple[int, int, int, int, int]:
    """ Reads a sequence message with two u8 arguments """

    seek_addr(seq, offset)
    arg_addr1 = seq.tell() + 1
    arg_addr2 = seq.tell() + 2

    data = struct.unpack('>3B', seq.read(3))

    return MessageData(arg_addr_1=arg_addr1, arg_addr_2=arg_addr2, msg_byte=data[0], arg_1=(data[1], 'u8'), arg_2=(data[2], 'u8'))


def read_u8_u16(seq: str, offset: int) -> Tuple[int, int, int, int, int]:
    """ Reads a sequence message with one u8 argument and one u16 argument """

    seek_addr(seq, offset)
    arg_addr1 = seq.tell() + 1
    arg_addr2 = seq.tell() + 2

    data = struct.unpack('>2B1H', seq.read(4))

    return MessageData(arg_addr_1=arg_addr1, arg_addr_2=arg_addr2, msg_byte=data[0], arg_1=(data[1], 'u8'), arg_2=(data[2], 'u16'))


def read_u16(seq: str, offset: int) -> Tuple[int, int, int]:
    """ Reads a sequence message with one u16 argument """

    seek_addr(seq, offset)
    arg_addr = seq.tell() + 1

    data = struct.unpack('>1B1H', seq.read(3))

    return MessageData(arg_addr_1=arg_addr, msg_byte=data[0], arg_1=(data[1], 'u16'))


def read_s16_u8(seq: str, offset: int) -> Tuple[int, int, int, int, int]:
    """ Reads a sequence message with one s16 argument and one u8 argument """

    seek_addr(seq, offset)
    arg_addr1 = seq.tell() + 1
    arg_addr2 = seq.tell() + 3

    data = struct.unpack('>1B1H1B', seq.read(4))

    return MessageData(arg_addr_1=arg_addr1, arg_addr_2=arg_addr2, msg_byte=data[0], arg_1=(data[1], 's16'), arg_2=(data[2], 'u8'))


def write_bin(seq: str, addr: int, value: int) -> None:
    """ Writes the address and input value to the sequence binary """
    seq.seek(addr)
    seq.write(value)


def auto_seq_edit(seq: str) -> None:
    """ Initiates the default sequence editing process """

    for addr in MSTR_VOL_ADDR:
        input_vol = ARG_PARSER.check_input(ARG_PARSER.value)
        write_bin(seq, addr, input_vol)

        hex_addr = format_addr(addr)
        vol_string = int.from_bytes(input_vol, byteorder="big", signed=False)

        print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  Master volume at {PINK_218}{hex_addr.upper()}{RESET} successfully changed to: {PINK_218}{vol_string}{RESET} ({PINK_218}0x{hex(vol_string)[2:].upper()}{RESET})')


def manual_seq_edit(seq: str) -> None:
    """ Initiates the manual sequence editing process """

    for addr in MSTR_VOL_ADDR:
        input_vol = ''
        message = f'''
{BOLD}{YELLOW}[MANUAL INPUT VALUE]{RESET}:
  Enter value (e.g. 64, 0x40, 50%): '''
        print(message, end='')
        while type(input_vol) is not bytes:
            manual_vol = input()

            if manual_vol == 'exit':
                SysMsg.exit_msg()

            input_vol = ARG_PARSER.convert_input(manual_vol)

            if type(input_vol) is bytes:
                write_bin(seq, addr, input_vol)

                hex_addr = format_addr(addr)
                vol_string = int.from_bytes(
                    input_vol, byteorder="big", signed=False)

                print(f'{PL}{CL}{PL}{CL}{PL}{CL}', end='', flush=True)
                print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  Master volume at {PINK_218}{hex_addr}{RESET} successfully changed to: {PINK_218}{vol_string}{RESET} ({PINK_218}0x{hex(vol_string)[2:].upper()}{RESET})')
            else:
                manual_vol = print(f'{PL}{CL}{PL}{CL}{PL}{CL}', message, end='', flush=True)


def fix_jump(seq: str, addr: int) -> None:
    """ Changes the jump message at the specified address to 0xFB """
    seq.seek(addr)
    b = b'\xFB'
    seq.write(b)


def fix_rjump(seq: str, addr: int) -> None:
    """ Changes the jump message at the specified address to 0xF4 """
    seq.seek(addr)
    b = b'\xF4'
    seq.write(b)


@dataclass
class SeqMessage:
    name: str
    read_func: Callable
    byte_size: int
    color: Optional[str] = None
    extra_output_list: Optional[List] = None
    version_check: Optional[SeqVersion] = None


SEQ_MESSAGES = {
    # CONTROL FLOW
    0xFF: SeqMessage("end", read_msg, 1),
    0xFE: SeqMessage("delay1", read_msg, 1),
    0xFD: SeqMessage("delay", read_argvar, None),
    0xFC: SeqMessage("call", read_u16, 3),
    0xFB: SeqMessage("jump", read_u16, 3),
    0xFA: SeqMessage("eqjump", read_u16, 3, YELLOW, EQJUMP_ADDR),
    0xF9: SeqMessage("ltjump", read_u16, 3, YELLOW, LTJUMP_ADDR),
    0xF8: SeqMessage("loop", read_u8, 2),
    0xF7: SeqMessage("loopend", read_msg, 1),
    0xF6: SeqMessage("loopbreak", read_msg, 1),
    0xF5: SeqMessage("gteqjump", read_u16, 3, YELLOW, GTEQJUMP_ADDR),
    0xF4: SeqMessage("rjump", read_u8, 2),
    0xF3: SeqMessage("reqjump", read_u8, 2, YELLOW, REQJUMP_ADDR),
    0xF2: SeqMessage("rltjump", read_u8, 2, YELLOW, RLTJUMP_ADDR),

    # NON-ARGBITS
    0xF1: SeqMessage("reservenotes", read_u8, 2),
    0xF0: SeqMessage("releasenotes", read_u8, 2),
    0xEF: SeqMessage("print3", read_s16_u8, 4),
    0xDF: SeqMessage("transpose", read_u8, 2),
    0xDE: SeqMessage("rtranspose", read_u8, 2),
    0xDD: SeqMessage("tempo", read_u8, 2),
    0xDC: SeqMessage("addtempo", read_u8, 2),
    0xDB: SeqMessage("mstrvol", read_u8, 2, PINK_218, MSTR_VOL_ADDR),
    0xDA: SeqMessage("fade", read_u8_u16, 4),
    0xD9: SeqMessage("mstrexpression", read_u8, 2),
    0xD7: SeqMessage("enablechan", read_u16, 3),
    0xD6: SeqMessage("disablechan", read_u16, 3),
    0xD5: SeqMessage("mutescale", read_u8, 2),
    0xD4: SeqMessage("mute", read_msg, 1),
    0xD3: SeqMessage("mutebhv", read_u8, 2),
    0xD2: SeqMessage("loadshortvel", read_u16, 3),
    0xD1: SeqMessage("loadshortgate", read_u16, 3),
    0xD0: SeqMessage("notealloc", read_u8, 2),
    0xCE: SeqMessage("rand", read_u8, 2),
    0xCD: SeqMessage("dyncall", read_u16, 3),
    0xCC: SeqMessage("load", read_u8, 2),
    0xC9: SeqMessage("and", read_u8, 2),
    0xC8: SeqMessage("sub", read_u8, 2),
    0xC7: SeqMessage("storeseq", read_u8_u16, 4),
    0xC6: SeqMessage("stop", read_msg, 1),
    0xC5: SeqMessage("scriptctr", read_u16, 3),
    0xC4: SeqMessage("callseq", read_u8x2, 3),
    0xC3: SeqMessage("mutechan", read_u16, 3, version_check=SeqVersion.MM),
    0xC2: SeqMessage("unk_msg", lambda seq, addr: (None,), 3, version_check=SeqVersion.MM),

    # ARGBITS
    **{i: SeqMessage("testchan", read_msg, 1) for i in range(0x00, 0x10)},
    **{i: SeqMessage("stopchan", read_msg, 1) for i in range(0x40, 0x50)},
    **{i: SeqMessage("subio", read_msg, 1) for i in range(0x50, 0x60)},
    **{i: SeqMessage("loadres", read_u8x2, 3) for i in range(0x60, 0x70)},
    **{i: SeqMessage("storeio", read_msg, 1) for i in range(0x70, 0x80)},
    **{i: SeqMessage("loadio", read_msg, 1) for i in range(0x80, 0x90)},
    **{i: SeqMessage("loadchan", read_u16, 3) for i in range(0x90, 0xA0)},
    **{i: SeqMessage("rloadchan", read_u16, 3) for i in range(0xA0, 0xB0)},
    **{i: SeqMessage("loadseq", read_u8_u16, 4) for i in range(0xB0, 0xC0)}
}


class SysMsg:
    """ Holds functions for various system messages """

    def file_open_failure(exception) -> None:
        """ Error thrown when parsing a sequence file fails """
        print(f'\n{BOLD}{RED}[ERROR]{RESET}:\n  Failed to open file! Exception: {exception}')
        sys.exit(1)

    def seq_parse_failure(exception) -> None:
        """ Error thrown when parsing a sequence file fails """
        print(f'\n{BOLD}{RED}[ERROR]{RESET}:\n  Failed to parse sequence! Exception: {exception}')
        sys.exit(1)

    def exit_msg() -> None:
        """ Message printed when user chooses to exit the process """
        print(f'\n{BOLD}{RED}[EXITING]{RESET}:\n  Closing sequence and exiting process...')
        sys.exit(1)

    def complete_msg(fixed_jumps: bool) -> None:
        """ Message printed when the process is completed successfully """
        if fixed_jumps:
            print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed successfully! Master volume messages were changed and jumps were fixed.')
        else:
            print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed successfully! Master volume messages were changed.')
        sys.exit()

    def incomplete_msg(no_vol: bool, fixed_jumps: bool) -> None:
        """ Message printed when the process is incompleted successfully """
        if no_vol and fixed_jumps:
            print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  Operation has completed sucessfully! There were no master volume messages, but jumps were fixed.')
        else:
            print(f'\n{BOLD}{GREEN_79}[COMPLETED]{RESET}:\n  But nothing was changed... the poor parsed sequence...')
        sys.exit()

    def archive_packed() -> None:
        """ Message printed when the archive gets repacked """
        print(f'\n{BOLD}{YELLOW}[ARCHIVE REPACKED]{RESET}:\n  A new {archive.ext} file has been created with your changes as {PINK_218}{os.path.basename(archive.new_archive)}{RESET}.')


class ArgParser:
    """ Creates a parser to run through CLI arguments """

    def check_file(types: list[str], filename: str) -> str:
        """ Checks if the input filename's extension is .seq, .aseq, .zseq, .ootrs, or .mmrs """
        ext = os.path.splitext(filename)[1]
        if ext not in types:
            ArgParser.parser.error('sequence filename must end with one of the following extensions: .seq, .zseq, .aseq')
        return filename

    def check_vol(value: str) -> int:
        """ Checks if the input volume arg can be converted into an integer """
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

    def check_input(self, value: str) -> bytes:
        """ Converts the original input volume to a byte """
        if isinstance(value, float):
            result = int(math.ceil(value/100 * 127))
            input_vol = result.to_bytes(1, byteorder='big', signed=False)
        else:
            input_vol = int(value).to_bytes(1, byteorder='big', signed=False)

        return input_vol

    def convert_input(self, manual_vol: str) -> bytes:
        """ Converts the manual input volume to a byte """
        try:
            if manual_vol.endswith('%'):
                percent = float(manual_vol[:-1])
                percent = int(math.ceil(percent/100 * 127))
                input_vol = percent.to_bytes(1, byteorder='big', signed=False)

            elif manual_vol.startswith('0x') or manual_vol.startswith('0X'):
                input_vol = int(manual_vol, 0).to_bytes(1, byteorder='big', signed=False)

            else:
                input_vol = int(manual_vol).to_bytes(1, byteorder='big', signed=False)

            return input_vol
        except:
            pass

    def get_args(self) -> None:
        """ Gets the arguments from the CLI """

        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage=f'{GRAY_248}[>_]{RESET} {YELLOW_229}python{RESET} {BLUE_39}{sys.argv[0]}{RESET} {GRAY_245}[-h]{RESET} {BLUE_39}[file] [volume]{RESET} {GRAY_245}[-j] [-g GAME]{RESET}',
            description='''This script allows a user to change a Zelda64 music file's master volume.''',
        )
        self.parser.add_argument(
            'file',
            type=lambda s: ArgParser.check_file(FILE_EXT, s),
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

        self.file = self.args.file
        self.value = self.args.volume
        self.fix_jumps = self.args.fix_jumps
        self.game_version = {
            'OOT': SeqVersion.OOT,
            'OoT': SeqVersion.OOT,
            'oot': SeqVersion.OOT,
            'MM': SeqVersion.MM,
            'mm': SeqVersion.MM,
        }.get(self.args.game, None)

    def __str__(self) -> str:
        return f'Parsed Arguments = (file={self.file}, volume={self.value}, fix_jumps={self.fix_jumps}, game_version={self.game_version})'


class ArchiveHandler:
    """ Handle packing and unpacking archived files """

    def unpack_archive(self, tempfolder) -> str:
        """ Unpacks an .ootrs or .mmrs music file to a temp directory """

        time.sleep(1.5)

        filepath = os.path.abspath(ARG_PARSER.file)

        with zipfile.ZipFile(filepath, 'r') as zip_archive:
            zip_archive.extractall(tempfolder)

        self.seq_file: str = None

        for f in os.listdir(tempfolder):
            if f.endswith('.seq') or f.endswith('.aseq') or f.endswith('.zseq'):
                if self.seq_file is None:
                    self.seq_file = f'{tempfolder}/{f}'
                else:
                    raise Exception('Multiple sequence files detected! This should not happen!')

        return self.seq_file

    def repack_archive(self, tempfolder):
        """ Packs a temp directory into an .ootrs or .mmrs file """
        basefolder = os.path.dirname(os.path.realpath(__file__))

        self.filename: str = os.path.splitext(ARG_PARSER.file)[0]
        self.ext: str = os.path.splitext(ARG_PARSER.file)[1]

        shutil.make_archive(self.filename, 'zip', tempfolder)

        self.new_archive = str(self.filename + f'.{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}' + self.ext)
        os.rename(self.filename + '.zip', f'{basefolder}/{self.new_archive}')


class SeqParser:
    """ Parse Zelda64 binary sequence files """

    def __init__(self):
        self.pos = 0

    def open_sequence(self, seq: str) -> str:
        """ Tries to open the specified file, if it cannot be opened throws an error """
        try:
            self.data = open(seq, 'r+b')
            return self.data
        except:
            print(f'{BOLD}{RED}[ERROR]{RESET}:\n  File could not be opened!')
            sys.exit(1)

    def parse_seq(self, seq: str, version: SeqVersion) -> None:
        """ Parses the SEQ section of a binary Zelda64 sequence file """

        pos = self.pos
        byte = seq.read(1)

        # Give some time for the thread animation to actually play... because parsing does not take long at all
        time.sleep(1.5)

        while (byte := seq.read(1)):
            pos = seq.tell() - 1
            opcode = byte[0]

            msg = SEQ_MESSAGES.get(opcode)
            if msg is None:
                continue

            if msg.version_check and msg.version_check != version:
                continue

            seq.seek(pos + 1)
            arglen = ord(seq.read(1))

            if msg.read_func == read_argvar:
                msg_data = msg.read_func(seq, pos, arglen)
            else:
                msg_data = msg.read_func(seq, pos)

            if msg_data.arg_2:
                msg_string = get_msg_string(pos, opcode, msg_data.arg_1, msg_data.arg_2)
            else:
                msg_string = get_msg_string(pos, opcode, msg_data.arg_1)

            color_prefix = f'{msg.color}  ' if msg.color else "  "
            msg_string = f'{color_prefix}{msg.name.ljust(16)}{msg_string}{RESET if msg.color else ""}'

            SEQ_HEADER_OUTPUT.append(msg_string)

            if msg.extra_output_list is not None:
                msg.extra_output_list.append(msg_data.arg_addr_1)
                if msg_data.arg_addr_2:
                    msg.extra_output_list.append(msg_data.arg_addr_2)

            if opcode == 0xFF:
                break
            else:
                pos += msg.byte_size if msg.byte_size is not None else msg_data.pos

    def parse_chan(seq: str, version: SeqVersion) -> None:
        """ Parses the CHAN section of a binary Zelda64 sequence file """
        raise NotImplementedError

    def parse_layer(seq: str, version: SeqVersion) -> None:
        """ Parses the LAYER section of a binary Zelda64 sequence file """
        raise NotImplementedError


def main() -> None:
    """ The main function of the module """
    global no_vol, fixed_jumps

    # ------------------------#
    # SEQUENCE PARSING SETUP #
    # ------------------------#
    sequence = SeqParser()

    try:
        if archive.seq_file:
            seq = sequence.open_sequence(archive.seq_file)
        else:
            seq = sequence.open_sequence(seq_file)
    except Exception as e:
        SysMsg.file_open_failure(e)
    try:
        msg_type = f'{BOLD}{YELLOW}[PARSING SEQUENCE]{RESET}:'
        start_msg = 'Parsing SEQ section of sequence file to find messages...'
        end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[PARSING COMPLETED]{RESET}:\n  Parsing completed, listing messages in the SEQ section.'

        # Create and start the thread
        parser_thread = threading.Thread(target=sequence.parse_seq, args=(
            sequence.data, ARG_PARSER.game_version))
        start_thread(parser_thread, msg_type, start_msg, end_msg)

        # Output the commands found in the sequence section
        seq_parse_output(SEQ_HEADER_OUTPUT)
        # print(f'\n{BOLD}{YELLOW}[PARSING COMPLETED]{RESET}:\n  Parsing of sequence section completed.')
    except Exception as e:
        SysMsg.seq_parse_failure(e)

    if len(MSTR_VOL_ADDR) > 1:
        answer: str = ''
        print(f'''
{CYAN}[INFO]{RESET}:
  Multiple master volume messages have been found in the sequence.
  Do you wish to modify master volume messages automatically or manually?

  {ITALIC}Options: auto, manual, exit{RESET}
  Input: ''', end='')

        options = [
            'auto', 'Auto', 'AUTO',
            'manual', 'Manual', 'MANUAL',
            'exit', 'Exit', 'EXIT',
        ]

        while answer not in options:
            answer = input()

            if answer in options[0:3]:
                auto_seq_edit(seq)
                break  # Return from loop after function completes — DO NOT REMOVE!
            elif answer in options[3:6]:
                manual_seq_edit(seq)
                break  # Return from loop after function completes — DO NOT REMOVE!
            elif answer in options[6:8]:
                SysMsg.exit_msg()
            else:
                answer = print(f'{PL}{CL}  Input: ', end='', flush=True)

    elif MSTR_VOL_ADDR:
        auto_seq_edit(seq)

    else:
        print(f'\n{BOLD}{RED}[WARNING]{RESET}:\n  Could not find master volume message in SEQ...\n  This script cannot insert a master volume message, so the master volume cannot be changed.')
        no_vol = True

    if ARG_PARSER.fix_jumps:
        jump_types = [
            ('eqjump', EQJUMP_ADDR, 'jump', fix_jump),
            ('ltjump', LTJUMP_ADDR, 'jump', fix_jump),
            ('gteqjump', GTEQJUMP_ADDR, 'jump', fix_jump),
            ('reqjump', REQJUMP_ADDR, 'rjump', fix_rjump),
            ('rltjump', RLTJUMP_ADDR, 'rjump', fix_rjump),
        ]

        for label, addr_list, jump_type, fix_func in jump_types:
            for addr in addr_list:
                fix_func(seq, addr)
                print(f'\n{BOLD}{GREEN_79}[SUCCESS]{RESET}:\n  {label} at {hex(addr)} successfully changed to: {jump_type}')

        fixed_jumps = True


if __name__ == '__main__':
    no_vol = False
    fixed_jumps = False

    ARG_PARSER: ArgParser = ArgParser()
    ARG_PARSER.get_args()

    if ARG_PARSER.game_version is None:
        print(f'{RED}[ERROR]{RESET}:\n  Game argument must be one of the following values: OOT, OoT, oot, MM, or mm.')
        sys.exit(1)

    filepath = os.path.abspath(ARG_PARSER.file)
    filename = os.path.basename(ARG_PARSER.file)

    archive: ArchiveHandler = ArchiveHandler()
    archive.seq_file = None

    try:
        if filepath.endswith('.ootrs') or filepath.endswith('.mmrs'):
            # Fix game versions if the user did not use conditional argument,
            # the ext tells which version to expect instead
            if filepath.endswith('.ootrs') and ARG_PARSER.game_version != SeqVersion.OOT:
                ARG_PARSER.game_version = SeqVersion.OOT
            else:
                ARG_PARSER.game_version = SeqVersion.MM

            msg_type = f'{BOLD}{YELLOW}[UNPACKING ARCHIVE]{RESET}:'
            start_msg = 'Unpacking the packed music files into a temp directory...'
            end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[ARCHIVE UNPACKED]{RESET}:'

            with tempfile.TemporaryDirectory() as tempfolder:
                unpack_thread = threading.Thread(
                    target=archive.unpack_archive, args=(tempfolder,))
                start_thread(unpack_thread, msg_type, start_msg, end_msg)
                print(f'  Music files in {PINK_218}{filename}{RESET} unpacked into temp directory, beginning parsing...\n')

                main()

                msg_type = f'\n{BOLD}{YELLOW}[PACKING ARCHIVE]{RESET}:'
                start_msg = 'Repacking extracted files and deleting temp directory...'
                end_msg = f'{PL}{CL}{BOLD}{GREEN_79}[ARCHIVE REPACKED]{RESET}:'

                repack_thread = threading.Thread(
                    target=archive.repack_archive, args=(tempfolder,))
                start_thread(repack_thread, msg_type, start_msg, end_msg)
                print(f'  A new {archive.ext} file has been created with your changes as {PINK_218}{os.path.basename(archive.new_archive)}{RESET}.')

        else:
            seq_file = filepath
            main()

        if not no_vol:
            SysMsg.complete_msg(fixed_jumps)
        else:
            SysMsg.incomplete_msg(no_vol, fixed_jumps)

    except Exception as e:
        print(f'ERROR: {e}')
        sys.exit(1)

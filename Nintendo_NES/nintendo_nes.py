import idc
import idaapi
import struct
import ctypes

ROM_SIGNATURE_OFFSET        = 0
ROM_SIGNATURE               = "NES\x1A"
ROM_FORMAT_NAME             = "Nintendo NES ROM"
ROM_SIGNATURE_LENGTH        = 4
HEADER_SIZE                 = 16

class NES_HEADER(ctypes.Structure):
    _fields_ = [("magic", ctypes.c_char * 4),
                ("nb_prg_page_16k", ctypes.c_ubyte),
                ("nb_chr_page_8k", ctypes.c_ubyte),
                ("rom_control_byte_0", ctypes.c_ubyte),
                ("rom_control_byte_1", ctypes.c_ubyte),
                ("nb_prg_page_8k", ctypes.c_ubyte),
                ("reserved", ctypes.c_char * 7)]
    def __str__(self):
        return '\n'.join(str(a) + " -> " + str(getattr(self, a)) for a, b in  self._fields_)

LEN_NES_HEADER = ctypes.sizeof(NES_HEADER)

RAM_START                   = 0x0
RAM_SIZE                    = 0x2000
IOREG_START                 = 0x2000
IOREG_SIZE                  = 0x2020
EXPROM_START                = 0x4020
EXPROM_SIZE                 = 0x1FE0
SRAM_START                  = 0x6000
SRAM_SIZE                   = 0x2000
TRAINER_START               = 0x7000
TRAINER_SIZE                = 0x0200
ROM_START                   = 0x8000
ROM_SIZE                    = 0x8000

PRG_PAGE_SIZE               = 0x4000
CHR_PAGE_SIZE               = 0x2000

MAPPER_NONE                 = 0
MAPPER_MMC1                 = 1
MAPPER_UxROM                = 2
MAPPER_CNROM                = 3
MAPPER_MMC3                 = 4
MAPPER_MMC5                 = 5
MAPPER_AxROM                = 7
MAPPER_MMC2                 = 9
MAPPER_MMC4                 = 10
MAPPER_COLOR_DREAMS         = 11
MAPPER_CPROM                = 13
MAPPER_BxROM                = 34
MAPPER_GNROM                = 66
MAPPER_CAMERICA             = 71
MAPPER_TLSROM               = 118
MAPPER_TQROM                = 119

def dwordAt(li, off):
    li.seek(off)
    s = li.read(4)
    if len(s) < 4:
        return 0
    return struct.unpack('<I', s)[0]

def zeromemory(ea, size):
    for i in xrange(0, size):
        idc.PatchByte(ea + i, 0)

def accept_file(li, n):
    # we support only one format per file
    if n > 0:
        return 0
    # check the signature
    li.seek(ROM_SIGNATURE_OFFSET)
    if li.read(ROM_SIGNATURE_LENGTH) == ROM_SIGNATURE:
        # accept the file
        return ROM_FORMAT_NAME
    # unrecognized format
    return 0

def load_prg_rom_bank(li, nheader, banknumber, va):
    offset = LEN_NES_HEADER
    if (nheader.rom_control_byte_0 & 0x04) != 0x00:
        offset = offset + TRAINER_SIZE
    offset = offset + (banknumber - 1) * PRG_PAGE_SIZE
    li.file2base(offset, va, va + PRG_PAGE_SIZE, 0)

def load_chr_rom_bank(li, nheader, banknumber, va):
    offset = LEN_NES_HEADER
    if (nheader.rom_control_byte_0 & 0x04) != 0x00:
        offset = offset + TRAINER_SIZE
    offset = offset + PRG_PAGE_SIZE * nheader.nb_prg_page_16k + (banknumber - 1) * CHR_PAGE_SIZE
    li.file2base(offset, va, va + CHR_PAGE_SIZE, 0)

def load_file(li, neflags, format):
    if format != ROM_FORMAT_NAME:
        Warning("Unknown format name: '%s'" % format)
        return 0
    idaapi.set_processor_type("M6502", SETPROC_ALL | SETPROC_FATAL)

    li.seek(0, idaapi.SEEK_END)
    size = li.tell()

    li.seek(0, idaapi.SEEK_SET)
    nheader = NES_HEADER.from_buffer_copy(li.read(LEN_NES_HEADER))

    # RAM SEGMENT
    idc.AddSeg(RAM_START, RAM_START + RAM_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
    idc.RenameSeg(RAM_START, "RAM")
    zeromemory(RAM_START, RAM_SIZE)

    # IOREG SEGMENT
    idc.AddSeg(IOREG_START, IOREG_START + IOREG_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
    idc.RenameSeg(IOREG_START, "IOREG")
    zeromemory(IOREG_START, IOREG_SIZE)

    # SRAM SEGMENT
    # bit 1 : Cartridge contains battery-backed PRG RAM ($6000-7FFF) or other persistent memory
    if (nheader.rom_control_byte_0 & 0x02) != 0x00:
        idc.AddSeg(SRAM_START, SRAM_START + SRAM_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
        idc.RenameSeg(SRAM_START, "SRAM")
        zeromemory(SRAM_START, SRAM_SIZE)

    # EXPROM SEGMENT
    idc.AddSeg(EXPROM_START, EXPROM_START + EXPROM_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
    idc.RenameSeg(EXPROM_START, "EXPROM")
    zeromemory(EXPROM_START, EXPROM_SIZE)

    # TRAINER SEGMENT
    # bit 2 : 512-byte trainer at $7000-$71FF (stored before PRG data)
    if (nheader.rom_control_byte_0 & 0x04) != 0x00:
        idc.AddSeg(TRAINER_START, TRAINER_START + TRAINER_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
        idc.RenameSeg(TRAINER_START, "TRAINER")
        zeromemory(TRAINER_START, TRAINER_SIZE)

    # ROM SEGMENT
    idc.AddSeg(ROM_START, ROM_START + ROM_SIZE, 0, 0, idaapi.saRelPara, idaapi.scPub)
    idc.RenameSeg(ROM_START, "ROM")
    idc.SetSegmentType(ROM_START, idc.SEG_CODE | idc.SEG_DATA)
    zeromemory(ROM_START, ROM_SIZE)

    describe_header_info(li)

    mapper_version = (((nheader.rom_control_byte_0 & 0xF0) >> 4) | (nheader.rom_control_byte_1 & 0xF0))
    if (mapper_version == MAPPER_NONE or
        mapper_version == MAPPER_MMC1 or
        mapper_version == MAPPER_UxROM or
        mapper_version == MAPPER_CNROM or
        mapper_version == MAPPER_MMC3 or
        mapper_version == MAPPER_MMC5 or
        mapper_version == MAPPER_CAMERIC or
        mapper_version == MAPPER_GNROM):
            offset = LEN_NES_HEADER
            if (nheader.rom_control_byte_0 & 0x04) != 0x00:
                offset = offset + TRAINER_SIZE
            offset = offset
            li.file2base(offset, ROM_START, ROM_START + PRG_PAGE_SIZE, 0)
            offset = LEN_NES_HEADER
            if (nheader.rom_control_byte_0 & 0x04) != 0x00:
                offset = offset + TRAINER_SIZE
            offset = offset + (nheader.nb_prg_page_16k - 1) * PRG_PAGE_SIZE
            li.file2base(offset, ROM_START + PRG_PAGE_SIZE, ROM_START + PRG_PAGE_SIZE + PRG_PAGE_SIZE, 0)
            offset = LEN_NES_HEADER
            if (nheader.rom_control_byte_0 & 0x04) != 0x00:
                offset = offset + TRAINER_SIZE
            offset = offset + PRG_PAGE_SIZE * nheader.nb_prg_page_16k
            li.file2base(offset, RAM_START, RAM_START + CHR_PAGE_SIZE, 0)
    elif (mapper_version == MAPPER_MMC2):
        Warning("Second case mapper")
    elif (mapper_version == MAPPER_AxROM or
        mapper_version == MAPPER_COLOR_DREAMS or
        mapper_version == MAPPER_BxROM):
        Warning("Third case mapper")
    else:
        Warning("Mapper %d is not supported" % mapper_version)

    naming()

    idaapi.add_entry(Word(0xFFFC), Word(0xFFFC), "start", 1)
    idaapi.cvar.inf.startIP = Word(0xFFFC)
    idaapi.cvar.inf.beginEA = Word(0xFFFC)
    return 1

def describe_header_info(li):
    li.seek(0, idaapi.SEEK_SET)
    idaapi.describe(0x00, True, "-------------------------------")
    idaapi.describe(0x00, True, "; ROM HEADER")
    idaapi.describe(0x00, True, "; Signature : %s" % li.read(4))
    idaapi.describe(0x00, True, "; Number of 16K PRG-ROM Pages : 0x%02X" % struct.unpack("<B", li.read(1))[0])
    idaapi.describe(0x00, True, "; Number of 8K CHR-ROM Pages : 0x%02X" % struct.unpack("<B", li.read(1))[0])
    idaapi.describe(0x00, True, "; Cartridge Type LSB : 0x%02X" % struct.unpack("<B", li.read(1))[0])
    idaapi.describe(0x00, True, "; Cartridge Type MSB : 0x%02X" % struct.unpack("<B", li.read(1))[0])
    idaapi.describe(0x00, True, "; Number of 8K RAM : 0x%02X" % struct.unpack("<B", li.read(1))[0])
    idaapi.describe(0x00, True, "-------------------------------")

def naming():
    MakeNameEx(0xFFFA, "NMI_vector", SN_NOCHECK | SN_NOWARN)
    MakeWord(0xFFFA)
    MakeNameEx(0xFFFC, "RESET_vector", SN_NOCHECK | SN_NOWARN)
    MakeWord(0xFFFC)
    MakeNameEx(0xFFFE, "IRQ_vector", SN_NOCHECK | SN_NOWARN)
    MakeWord(0xFFFE)
    MakeNameEx(0x2000, "PPU_Control_Register_1", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2000)
    MakeNameEx(0x2001, "PPU_Control_Register_2", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2001)
    MakeNameEx(0x2002, "PPU_Status_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2002)
    MakeNameEx(0x2003, "SPR-RAM_Address_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2003)
    MakeNameEx(0x2004, "SPR-RAM_Data_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2004)
    MakeNameEx(0x2005, "PPU_Background_Scrolling_Offset", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2005)
    MakeNameEx(0x2006, "VRAM_Address_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2006)
    MakeNameEx(0x2007, "VRAM_Read/Write_Data_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x2007)
    MakeNameEx(0x4000, "APU_Channel_1_(Rectangle)_Volume/Decay", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4000)
    MakeNameEx(0x4001, "APU_Channel_1_(Rectangle)_Sweep", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4001)
    MakeNameEx(0x4002, "APU_Channel_1_(Rectangle)_Frequency", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4002)
    MakeNameEx(0x4003, "APU_Channel_1_(Rectangle)_Length", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4003)
    MakeNameEx(0x4004, "APU_Channel_2_(Rectangle)_Volume/Decay", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4004)
    MakeNameEx(0x4005, "APU_Channel_2_(Rectangle)_Sweep", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4005)
    MakeNameEx(0x4006, "APU_Channel_2_(Rectangle)_Frequency", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4006)
    MakeNameEx(0x4007, "APU_Channel_2_(Rectangle)_Length", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4007)
    MakeNameEx(0x4008, "APU_Channel_3_(Triangle)_Linear_Counter", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4008)
    MakeNameEx(0x4009, "APU_Channel_3_(Triangle)_N/A", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4009)
    MakeNameEx(0x400A, "APU_Channel_3_(Triangle)_Frequency", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400A)
    MakeNameEx(0x400B, "APU_Channel_3_(Triangle)_Length", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400B)
    MakeNameEx(0x400C, "APU_Channel_4_(Noise)_Volume/Decay", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400C)
    MakeNameEx(0x400D, "APU_Channel_4_(Noise)_N/A", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400D)
    MakeNameEx(0x400E, "APU_Channel_4_(Noise)_Frequency", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400E)
    MakeNameEx(0x400F, "APU_Channel_4_(Noise)_Length", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x400F)
    MakeNameEx(0x4010, "APU_Channel_5_(DMC)_Play_mode_and_DMA_frequency", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4010)
    MakeNameEx(0x4011, "APU_Channel_5_(DMC)_Delta_counter_load_register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4011)
    MakeNameEx(0x4012, "APU_Channel_5_(DMC)_Address_load_register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4012)
    MakeNameEx(0x4013, "APU_Channel_5_(DMC)_Length_register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4013)
    MakeNameEx(0x4014, "SPR-RAM_DMA_Register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4014)
    MakeNameEx(0x4015, "DMC/IRQ/length_counter_status/channel_enable_register", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4015)
    MakeNameEx(0x4016, "Joypad_#1_(RW)", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4016)
    MakeNameEx(0x4017, "Joypad_#2/APU_SOFTCLK_(RW)", SN_NOCHECK | SN_NOWARN)
    MakeWord(0x4017)

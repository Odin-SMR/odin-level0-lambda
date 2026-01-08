import struct
from typing import Callable


SSB_PARAMS: dict[str, tuple[float, float, float, float]] = {
    "495": (61600.36, 104188.89, 0.0002977862, 313.0),
    "549": (57901.86, 109682.58, 0.0003117128, 313.0),
    "555": (60475.43, 116543.50, 0.0003021341, 308.0),
    "572": (58120.92, 115256.73, 0.0003128605, 314.0),
}


class Level0File:
    """A Python class to handle Odin level 0 files"""

    TypeError = "wrong file type"

    def __init__(self, filename: str) -> None:
        self.name = filename
        self.input = open(filename, "rb")
        _, stw, user = self.getHead()
        self.first = stw
        self.user = user
        sizeunit = 15 * struct.calcsize("H")
        if user == 0x732C:
            self.type = "SHK"
            self.tail = 4
            self.blocksize = 5 * sizeunit
        elif user == 0x73EC:
            self.type = "FBA"
            self.tail = 4
            self.blocksize = 1 * sizeunit
        elif (user & 0xFFF0) == 0x7360:
            self.type = "AOS"
            self.tail = 4
            self.blocksize = 8 * sizeunit
        elif (user & 0xFFF0) == 0x7380:
            self.type = "AC1"
            self.tail = 7
            self.blocksize = 5 * sizeunit
        elif (user & 0xFFF0) == 0x73B0:
            self.type = "AC2"
            self.tail = 7
            self.blocksize = 5 * sizeunit
        else:
            raise TypeError
        self.input.seek(-self.blocksize, 2)
        _, stw, user = self.getHead()
        self.last = stw
        self.input.seek(0, 0)

    def getHead(self) -> tuple[int, int, int]:
        data = self.input.read(struct.calcsize("H" * 4))
        head = struct.unpack("H" * 4, data)
        sync = head[0]
        stw = head[2] * 65536 + head[1]
        user = head[3]
        return sync, stw, user

    def getIndex(self) -> tuple[int, bool, str | None, int, int] | None:
        data = self.input.read(self.blocksize)
        if len(data) == self.blocksize:
            n = self.blocksize // 2
            words: tuple[int, ...] = struct.unpack("H" * n, data)
            self.sync = words[0]
            self.stw = words[2] * 65536 + words[1]
            self.user = words[3]
            index = words[-self.tail]
            valid = (index & 0x8000) != 0
            if valid:
                if index & 0x4000:
                    dis = "ASTR"
                else:
                    dis = "AERO"
            else:
                dis = None
            acdcmode = (index & 0x0F00) >> 8
            science = index & 0x00FF
            return self.stw, valid, dis, acdcmode, science
        return None

    def getBlock(self) -> list[int]:
        data = self.input.read(self.blocksize)
        if len(data) == self.blocksize:
            n = self.blocksize // 2
            words = list(struct.unpack("H" * n, data))
            self.sync = words[0]
            self.stw = words[2] * 65536 + words[1]
            self.user = words[3]
            words = words[4 : -self.tail]
        else:
            words = []
        return words

    def rewind(self) -> None:
        self.input.seek(0, 0)

    def __del__(self) -> None:
        # print("closing file", self.name)
        self.input.close


HKdata: dict[str, tuple[int, int, Callable[[int], float | int]]] = {
    "AOS laser temperature": (1, 0, lambda x: 0.01141 * x + 7.3),
    "AOS laser current": (1, 1, lambda x: 0.0388 * x),
    "AOS structure": (1, 2, lambda x: 0.01167 * x + 0.764),
    "AOS continuum": (1, 3, lambda x: (5.7718e-6 * x + 6.929e-3) * x - 2.1),
    "AOS processor": (1, 4, lambda x: 0.01637 * x - 6.54),
    "varactor 495": (17, 0, lambda x: 4.8 * 5.0 * x / 4095.0 - 12.0),
    "varactor 549": (18, 0, lambda x: 4.8 * 5.0 * x / 4095.0 - 12.0),
    "varactor 572": (25, 0, lambda x: 4.8 * 5.0 * x / 4095.0 - 12.0),
    "varactor 555": (26, 0, lambda x: 4.8 * 5.0 * x / 4095.0 - 12.0),
    "gunn 495": (17, 1, lambda x: 80.0 * 5.0 * x / 4095.0),
    "gunn 549": (18, 1, lambda x: 80.0 * 5.0 * x / 4095.0),
    "gunn 572": (25, 1, lambda x: 80.0 * 5.0 * x / 4095.0),
    "gunn 555": (26, 1, lambda x: 80.0 * 5.0 * x / 4095.0),
    "harmonic mixer 495": (17, 2, lambda x: 1.2195 * 5.0 * x / 4095.0),
    "harmonic mixer 549": (18, 2, lambda x: 1.2195 * 5.0 * x / 4095.0),
    "harmonic mixer 572": (25, 2, lambda x: 1.2195 * 5.0 * x / 4095.0),
    "harmonic mixer 555": (26, 2, lambda x: 1.2195 * 5.0 * x / 4095.0),
    "doubler 495": (17, 3, lambda x: -1.6129 * 5.0 * x / 4095.0),
    "doubler 549": (18, 3, lambda x: -1.6129 * 5.0 * x / 4095.0),
    "doubler 572": (25, 3, lambda x: -1.6129 * 5.0 * x / 4095.0),
    "doubler 555": (26, 3, lambda x: -1.6129 * 5.0 * x / 4095.0),
    "tripler 495": (17, 4, lambda x: -1.2195 * 5.0 * x / 4095.0),
    "tripler 549": (18, 4, lambda x: -1.2195 * 5.0 * x / 4095.0),
    "tripler 572": (25, 4, lambda x: -1.2195 * 5.0 * x / 4095.0),
    "tripler 555": (26, 4, lambda x: -1.2195 * 5.0 * x / 4095.0),
    "mixer current 495": (19, 0, lambda x: 5.0 * x / 4095.0 / 1.22),
    "mixer current 549": (19, 1, lambda x: 5.0 * x / 4095.0 / 1.22),
    "mixer current 572": (27, 0, lambda x: 5.0 * x / 4095.0 / 1.22),
    "mixer current 555": (27, 1, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 1 bias 495": (19, 2, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 1 bias 549": (19, 4, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 1 bias 572": (27, 2, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 1 bias 555": (27, 4, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 2 bias 495": (19, 3, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 2 bias 549": (19, 5, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 2 bias 572": (27, 3, lambda x: 5.0 * x / 4095.0 / 1.22),
    "HEMT 2 bias 555": (27, 5, lambda x: 5.0 * x / 4095.0 / 1.22),
    "warm IF A-side": (20, 0, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "warm IF B-side": (28, 0, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "hot load A-side": (20, 1, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "hot load B-side": (28, 1, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "image load A-side": (20, 2, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "image load B-side": (28, 2, lambda x: 20.0 * (5.0 * x / 4095.0 - 1.16)),
    "mixer A-side": (
        20,
        3,
        lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15,
    ),  # noqa: E501
    "mixer B-side": (
        28,
        3,
        lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15,
    ),  # noqa: E501
    "LNA A-side": (20, 4, lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15),
    "LNA B-side": (28, 4, lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15),
    "119GHz mixer A-side": (
        20,
        5,
        lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15,
    ),  # noqa: E501
    "119GHz mixer B-side": (
        28,
        5,
        lambda x: 70.0 * (5.0 * x / 4095.0 - 3.86) + 273.15,
    ),  # noqa: E501
    "HRO frequency 495": (21, 0, lambda x: x + 4000.0),
    "HRO frequency 549": (21, 2, lambda x: x + 4000.0),
    "HRO frequency 572": (29, 0, lambda x: x + 4000.0),
    "HRO frequency 555": (29, 2, lambda x: x + 4000.0),
    "PRO frequency 495": (21, 1, lambda x: x / 32.0 + 100.0),
    "PRO frequency 549": (21, 3, lambda x: x / 32.0 + 100.0),
    "PRO frequency 572": (29, 1, lambda x: x / 32.0 + 100.0),
    "PRO frequency 555": (29, 3, lambda x: x / 32.0 + 100.0),
    "LO mechanism A 495": (37, 0, lambda x: x),
    "LO mechanism A 549": (38, 0, lambda x: x),
    "LO mechanism A 572": (37, 2, lambda x: x),
    "LO mechanism A 555": (38, 2, lambda x: x),
    "LO mechanism B 495": (43, 0, lambda x: x),
    "LO mechanism B 549": (44, 0, lambda x: x),
    "LO mechanism B 572": (43, 2, lambda x: x),
    "LO mechanism B 555": (44, 2, lambda x: x),
    "SSB mechanism A 495": (35, 0, lambda x: x),
    "SSB mechanism A 549": (36, 0, lambda x: x),
    "SSB mechanism A 572": (35, 2, lambda x: x),
    "SSB mechanism A 555": (36, 2, lambda x: x),
    "SSB mechanism B 495": (41, 0, lambda x: x),
    "SSB mechanism B 549": (42, 0, lambda x: x),
    "SSB mechanism B 572": (41, 2, lambda x: x),
    "SSB mechanism B 555": (42, 2, lambda x: x),
    "119GHz voltage": (46, 4, lambda x: -56.0 + x * 112.0 / 4095.0),
    "119GHz current": (46, 12, lambda x: -1091.0 + x * 2178.0 / 4095.0),
    "ACDC1 sync": (47, -1, lambda x: (int(x) >> 8) & 0x000F),
    "ACDC2 sync": (48, -1, lambda x: (x >> 3) & 0x000F),
    "119GHz DRO": (
        13,
        1,
        lambda x: 944.035 - (0.8374 - (2.567e-4 - 2.74e-8 * x) * x) * x,
    ),  # noqa: E501
    "ACS availability": (49, 13, lambda x: x),
}


class SHKfile(Level0File):
    """A derived class to handle Odin level 0 SHK files"""

    def __init__(self, filename: str) -> None:
        # print("init SHK...)"
        Level0File.__init__(self, filename)
        if self.type != "SHK":
            raise TypeError

    def getHKword(
        self,
        which: int,
        sub: int = -1,
    ) -> tuple[list[int], list[int]]:
        self.rewind()
        stw = []
        data = []
        words = self.getBlock()
        while words:
            word = words[which]
            found = word != 0xFFFF
            if sub > -1:
                found = (word & 0x000F) == sub
                word = word >> 4
            if found:
                stw.append(self.stw)
                data.append(word)
            words = self.getBlock()
        return stw, data

    def getLOfreqs(self) -> tuple[
        list[int],
        list[float],
        list[float],
        list[int],
        list[float],
        list[float],
    ]:
        def sub(word: int) -> int:
            return word & 0x000F

        def freq(hro: int, pro: int, m: float) -> float:
            return ((4000.0 + hro) * m + pro / 32.0 + 100.0) * 6.0e6

        self.rewind()
        stw = []
        aside = []
        bside = []
        words = self.getBlock()
        while words:
            stw.append(self.stw)
            aside.append(int(words[21]))
            bside.append(int(words[29]))
            words = self.getBlock()

        i = 0
        STWa = []
        STWb = []
        LO495 = []
        LO549 = []
        LO555 = []
        LO572 = []
        while i < len(stw) - 3:
            if sub(aside[i]) == 0:
                STWa.append(stw[i])
                if sub(aside[i]) == 0 and sub(aside[i + 1]) == 1:
                    hro = aside[i] >> 4
                    pro = aside[i + 1] >> 4
                    LO495.append(freq(hro, pro, 17.0))
                else:
                    LO495.append(0.0)

                if sub(aside[i + 2]) == 2 and sub(aside[i + 3]) == 3:
                    hro = aside[i + 2] >> 4
                    pro = aside[i + 3] >> 4
                    LO549.append(freq(hro, pro, 19.0))
                else:
                    LO549.append(0.0)

            if sub(bside[i]) == 0:
                STWb.append(stw[i])
                if sub(bside[i]) == 0 and sub(bside[i + 1]) == 1:
                    hro = bside[i] >> 4
                    pro = bside[i + 1] >> 4
                    LO572.append(freq(hro, pro, 20.0))
                else:
                    LO572.append(0.0)

                # print(
                #     "%04x %04x %04x %04x"
                #     % (bside[i], bside[i+1], bside[i+2], bside[i+3])
                # )
                if sub(bside[i + 2]) == 2 and sub(bside[i + 3]) == 3:
                    hro = bside[i + 2] >> 4
                    pro = bside[i + 3] >> 4
                    LO555.append(freq(hro, pro, 19.0))
                    # print(LO555[-1])
                else:
                    LO555.append(0.0)
            i = i + 1

        return STWa, LO495, LO549, STWb, LO555, LO572

    def getSSBtunings(
        self,
    ) -> tuple[list[int], list[int], list[int], list[int], list[int]]:
        def sub(word: int) -> int:
            return word & 0x000F

        self.rewind()
        stw: list[int] = []
        aside: list[int] = []
        bside: list[int] = []
        which: list[str] = []
        words = self.getBlock()
        while words:
            stw.append(self.stw)
            if words[35] != 0xFFFF and words[36] != 0xFFFF:
                aside.append(words[35])
                bside.append(words[36])
                which.append("A")
            else:
                aside.append(words[41])
                bside.append(words[42])
                which.append("B")
            words = self.getBlock()

        i = 0
        STW: list[int] = []
        SSB495: list[int] = []
        SSB549: list[int] = []
        SSB555: list[int] = []
        SSB572: list[int] = []
        while i < len(stw) - 2:
            if (
                sub(aside[i]) == 0
                and sub(bside[i]) == 0
                and sub(aside[i + 2]) == 2
                and sub(bside[i + 2]) == 2
            ):
                STW.append(stw[i])
                if which[i] == "A":
                    SSB495.append(aside[i] >> 4)
                    SSB572.append(aside[i + 2] >> 4)
                    SSB549.append(bside[i] >> 4)
                    SSB555.append(bside[i + 2] >> 4)
                else:
                    SSB495.append(aside[i + 2] >> 4)
                    SSB572.append(aside[i] >> 4)
                    SSB549.append(bside[i + 2] >> 4)
                    SSB555.append(bside[i] >> 4)
                i = i + 2
            else:
                i = i + 1

        return STW, SSB495, SSB549, SSB555, SSB572


class FBAfile(Level0File):
    """A derived  class to handle Odin level 0 FBA files"""

    def __init__(self, filename: str) -> None:
        Level0File.__init__(self, filename)
        if self.type != "FBA":
            raise TypeError
        self.block0 = 0x73EC

    def getSpectrumHead(self) -> list[int] | None:
        words = self.getBlock()
        while words:
            if self.sync == 0x2BD3 and self.user == self.block0:
                return words
            words = self.getBlock()
        return None

    def Type(self, words: list[int]) -> str:
        phase = ["REF", "SK1", "CAL", "SK2"]
        mirror = words[5]
        if mirror == 0xFFFF:
            mirror = words[6]
            if mirror == 0xFFFF:
                mirror = 0
        mirror = (mirror >> 13) & 3
        type = phase[mirror]
        return type


class ACfile(Level0File):
    """A derived  class to handle Odin level 0 AC1 and AC2 files"""

    def __init__(self, filename: str) -> None:
        Level0File.__init__(self, filename)
        if self.type != "AC1" and self.type != "AC2":
            raise TypeError
        if self.type == "AC1":
            self.block0 = 0x7380
        elif self.type == "AC2":
            self.block0 = 0x73B0

    def getSpectrumHead(self) -> list[int] | None:
        words = self.getBlock()
        while words:
            if self.sync == 0x2BD3 and self.user == self.block0:
                return words
            words = self.getBlock()
        return None

    def Attenuation(self, words: list[int]) -> list[int]:
        att = [0] * 4
        for i in range(4):
            att[i] = words[37 + i]
            # if att[i] <= 95:
            #     print("(%08X) SSB[%d] attenuation at maximum" % (self.stw,i))
            # elif att[i] >= 145:
            #     print("(%08X) SSB[%d] attenuation at minimum" % (self.stw,i))
        return att

    def SSBfrequency(self, words: list[int]) -> list[int]:
        ssb = [0] * 4
        for i in range(4):
            ssb[i] = words[44 - i]
            # if ssb[i] < 3000 or ssb[i] > 5000:
            #     print("(%08X) SSB[%d] frequency out of range" % (self.stw,i))
        return ssb

    def Frontend(self, words: list[int]) -> str | None:
        frontend = ["549", "495", "572", "555", "SPL", "119"]
        input = words[36] >> 8 & 0x000F
        if input in range(1, 7):
            return frontend[input - 1]
        # print("(%08X) invalid input channel %d" % (self.stw, input))
        return None

    def Type(self, words: list[int]) -> str:
        rx = self.Frontend(words)
        chop = words[8]
        if chop == 0xAAAA:
            if rx == "495" or rx == "549":
                return "REF"
            elif rx == "555" or rx == "572" or rx == "119":
                return "SIG"
            elif rx == "SPL":
                if self.type == "AC1":
                    return "REF"
                return "SIG"
        else:
            if rx == "495" or rx == "549":
                return "SIG"
            elif rx == "555" or rx == "572" or rx == "119":
                return "REF"
            elif rx == "SPL":
                if self.type == "AC1":
                    return "SIG"
                return "REF"
        return "NAN"

    def Chop(self, words: list[int]) -> str:
        """This routine returns the phase of FBA data via
        the chopper wheel infromation contained in AC2"""
        if self.type != "AC2":
            raise TypeError
        chop = words[8]
        if chop == 0xAAAA:
            return "SIG"
        return "REF"

    def CmdTime(self, words: list[int]) -> float:
        """Calculate command time"""
        return float(words[35] & 0xFF) / 16.0

    def IntTime(self, words: list[int]) -> float:
        """Calculate integration time"""
        prescaler = int(words[49])
        if prescaler >= 2 and prescaler <= 6:
            samples = int(0x0000FFFF & words[12])
            samples = samples << (14 - prescaler)
            return float(samples) / 10.0e6
        # prescaler out of range
        return 0

    def Mode(self, words: list[int]) -> int:
        mode = words[35] >> 8 & 0x00FF
        # bands = 0
        # if mode == 0x7f or mode == 0xf7:
        #     bands = 8
        # elif mode == 0x2a or mode == 0xa2:
        #     bands = 4
        # elif mode == 0x08 or mode == 0x8a:
        #     bands = 2
        # elif mode == 0x00:
        #     bands = 1
        return mode

    def ZeroLags(self, words: list[int]) -> list[float]:
        bands = self.Mode(words)
        zlag = [0.0] * bands
        scale = 2048.0 / (224.0e6 / 2.0)
        inttime = self.IntTime(words)
        if inttime > 0.0:
            for i in range(bands):
                # (block, offset) = divmod(i*96,64)
                # block = block+1
                zlag[i] = scale * float(words[50 + i] << 4) / inttime
        return zlag


class AOSfile(Level0File):
    """A derived  class to handle Odin level 0 AOS files"""

    def __init__(self, filename: str) -> None:
        Level0File.__init__(self, filename)
        if self.type != "AOS":
            raise TypeError
        self.block0 = 0x7360

    def getSpectrumHead(self) -> list[int] | None:
        words = self.getBlock()
        while words:
            if self.sync == 0x2BD3 and self.user == self.block0:
                if words[1] != 322:
                    return words
            words = self.getBlock()
        return None

    def Frontend(self, words: list[int]) -> str:
        input = words[30 + 2]
        if input == 1:
            return "555"
        elif input == 2:
            return "572"
        elif input == 4:
            return "495"
        elif input == 8:
            return "549"
        elif input == 16:
            return "119"
        return "OFF"

    def Type(self, words: list[int]) -> str:
        if words[19]:
            aligned = words[8] & 0x0080
        elif words[20]:
            aligned = words[9] & 0x0080
        else:
            aligned = words[8] & 0x0080

        rx = self.Frontend(words)
        if aligned:
            if rx == "495" or rx == "549":
                type = "SIG"
            else:
                type = "REF"
        else:
            if rx == "495" or rx == "549":
                type = "REF"
            else:
                type = "SIG"

        if type == "REF":
            calmirror = words[11] & 0x000F
            if calmirror == 1:
                type = "SK1"
            elif calmirror == 2:
                type = "CAL"
            elif calmirror == 3:
                type = "SK2"

        if words[30 + 2] == 0:
            type = "DRK"
        if words[30 + 4] == 1:
            type = "CMB"

        return type

    def IntTime(self, words: list[int]) -> float:
        """Calculate integration time"""
        samples = words[35]
        return float(samples) * (1760.0 / 3.0e5)

    def Mode(self, words: list[int]) -> int:
        return words[1]

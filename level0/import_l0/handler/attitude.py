from datetime import datetime
import logging
import os

LineResult = tuple[
    int, int, int, int, int, float,
    int, float,
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float],
    tuple[float, float, float, float, float, float],
    float,
]


class AttitudeParser:

    def __init__(
        self,
        files,
        stw0: int = 0,
        stw1: int = 0x800000000,
    ) -> None:
        logger = logging.getLogger("level0.attitude_parser")
        logger.setLevel(logging.INFO)

        self.files = files
        self.stw0 = stw0
        self.stw1 = stw1
        m = 0
        self.table: dict[str, LineResult] = {}
        for file in files:
            n = 0
            logger.info(f"processing file {file}")
            self.input = open(file, 'r')
            # start to read header info in file
            line = ""
            # first extract soda version
            line0 = self.input.readline()
            line1 = line0.rsplit()
            self.soda = int(float(line1[len(line1) - 1]))
            logger.debug(f"soda version {self.soda} for file {file}")
            while (line != 'EOF\n'):
                line = self.input.readline()
            for _ in range(5):
                self.input.readline()
            t = self.getLine()
            min_stw = None
            max_stw = None
            min_date = None
            max_date = None
            while t:
                (
                    year, mon, day, hour, min, secs,
                    stw, orbit, qt, qa, qe, gps, acs,
                ) = t
                timestamp = datetime(
                    int(year), int(mon), int(day),
                    int(hour), int(min),
                )
                if min_stw is None or min_stw > stw:
                    min_stw = stw
                    min_date = timestamp
                if max_stw is None or max_stw < stw:
                    max_stw = stw
                    max_date = timestamp
                if stw >= stw0 and stw <= stw1:
                    key = "%08X" % (stw)
                    if key in self.table:
                        logger.warning(f"duplicate in {file}: {key}")
                        qe0 = self.table[key][10]
                        qe1 = t[10]
                        if qe0 != qe1:
                            err0 = (
                                qe0[0] * qe0[0] + qe0[1]
                                * qe0[1] + qe0[2] * qe0[2]
                            )
                            err1 = (
                                qe1[0] * qe1[0] + qe1[1]
                                * qe1[1] + qe1[2] * qe1[2]
                            )
                            logger.warning(f"errors in {file}: {err0}; {err1}")
                            if err1 < err0:
                                self.table[key] = t
                    else:
                        self.table[key] = t
                    n += 1
                t = self.getLine()
            logger.info(
                f"{n} lines in file {os.path.basename(file)} with stw from {min_stw} to {max_stw} ({min_date} to {max_date})"  # noqa: E501
            )
            m += n
            self.input.close()

        logger.info("total of %5d lines" % (m))

    def rewind(self) -> None:
        self.input.seek(0, 0)

    def getLine(self) -> LineResult | None:
        line = self.input.readline()
        if not line:
            return None
        cols = line.split()
        if len(cols) < 23:
            return None
        date = cols[0]
        hour = int(cols[1])
        min = int(cols[2])
        sec = float(cols[3])
        stw = int(cols[4])
        orbit = float(cols[5])
        year = int(date[0:4])
        mon = int(date[4:6])
        day = int(date[6:8])
        qt = (
            float(cols[6]), float(cols[7]),
            float(cols[8]), float(cols[9]),
        )
        qa = (
            float(cols[10]), float(cols[11]),
            float(cols[12]), float(cols[13]),
        )
        qe = (float(cols[14]), float(cols[15]), float(cols[16]))
        gps = (
            float(cols[17]), float(cols[18]), float(cols[19]),
            float(cols[20]), float(cols[21]), float(cols[22]),
        )
        # new attitude format, cols[34] == 5 indicates astronomy fine pointing
        if len(cols) == 37 and int(cols[34]) == 5:
            acs = float(cols[36])
        else:
            acs = 0.0
        self.t1 = (
            year, mon, day, hour, min, sec,
            stw, orbit, qt, qa, qe, gps, acs,
        )
        return self.t1

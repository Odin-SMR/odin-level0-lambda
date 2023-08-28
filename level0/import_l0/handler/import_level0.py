import codecs
import logging
import warnings
from io import BytesIO
from os import path
from datetime import datetime
from typing import Any

import numpy as np
import psycopg2
from psycopg2 import ProgrammingError

from .level0 import ACfile, FBAfile, SHKfile, HKdata
from .attitude import AttitudeParser


class UnknownFileType(Warning):
    pass


def get_full_path(
    filename: str,
    dirname: str = "/odindata/odin/level0",
) -> str:
    """ Construct filenames """

    basename, extention = path.splitext(filename)
    filetype = extention[1:]
    if filetype in ("ac1", "ac2", "shk", "fba"):
        pass
    elif extention == "att":
        if int("0x" + basename, base=16) < 0x0ce8666f:
            filetype = "att_17"
    else:
        raise ValueError("file type not recognised for " + filename)

    partdir = filename[0:3]
    return path.join(dirname, filetype, partdir, filename)


def getSHK(hk: SHKfile) -> dict[str, tuple[list[int], np.ndarray]]:
    """use Ohlbergs code to read in shk data from file
        and creates a dictionary for easy insertation
        into a postgresdatabase.
        """
    STWa, LO495, LO549, STWb, LO555, LO572 = hk.getLOfreqs()
    STW, SSB495, SSB549, SSB555, SSB572 = hk.getSSBtunings()
    shktypes = {
        "LO495": (STWa, np.array(LO495)),
        "LO549": (STWa, np.array(LO549)),
        "LO555": (STWb, np.array(LO555)),
        "LO572": (STWb, np.array(LO572)),
        "SSB495": (STW, np.array(SSB495)),
        "SSB549": (STW, np.array(SSB549)),
        "SSB555": (STW, np.array(SSB555)),
        "SSB572": (STW, np.array(SSB572)),
    }
    shktypeslist = {
        "mixer current 495": "mixC495",
        "mixer current 549": "mixC549",
        "mixer current 555": "mixC555",
        "mixer current 572": "mixC572",
        "image load B-side": "imageloadB",
        "image load A-side": "imageloadA",
        "hot load A-side": "hotloadA",
        "hot load B-side": "hotloadB",
        "mixer A-side": "mixerA",
        "mixer B-side": "mixerB",
        "LNA A-side": "lnaA",
        "LNA B-side": "lnaB",
        "119GHz mixer A-side": "119mixerA",
        "119GHz mixer B-side": "119mixerB",
        "warm IF A-side": "warmifA",
        "warm IF B-side": "warmifB",
    }
    for shktype in shktypeslist:
        table = HKdata[shktype]
        data = hk.getHKword(table[0], sub=table[1])
        data1 = np.array(map(table[2], data[1]))
        if shktype in ("hot load A-side", "hot load B-side"):
            data1 = data1 + 273.15

        shktypes[shktypeslist[shktype]] = (data[0], data1)
    return shktypes


def getACdis(ac: ACfile) -> str:
    """AC factory.
    reads a fileobject and extract the discipline of AC-data. Uses Ohlbergs
    routines to read the files (ACfile)
    """
    head = ac.getSpectrumHead()
    while head is not None:
        discipline = ac.getIndex()
        if discipline is not None:
            discipline_name = discipline[2]
            if discipline_name is None:
                discipline_name = "Problem"
        else:
            discipline_name = "Problem"
        return discipline_name
    raise EOFError


def getAC(ac: ACfile) -> dict[str, Any]:
    """AC factory.
    reads a fileobject and creates a dictionary for easy insertation
    into a postgresdatabase. Uses Ohlbergs routines to read the files (ACfile)
    """
    backend = {
        0x7380: "AC1",
        0x73b0: "AC2",
    }
    CLOCKFREQ = 224.0e6
    head = ac.getSpectrumHead()
    while head is not None:
        data = []
        stw = ac.stw
        back = backend[ac.user]
        for j in range(12):
            data.append(ac.getBlock())
            if data[j] == []:
                raise EOFError
        cc = np.array(data, dtype="int16")
        cc.shape = (8, 96)
        cc64 = np.array(cc, dtype="int64")
        lags = np.array(head[50:58], dtype="uint16")
        lags64 = np.array(lags, dtype="int64")
        # combine lag and data to ensure validity of first value in cc-channels
        zlags = np.left_shift(lags64, 4) + np.bitwise_and(cc64[:, 0], 0xf)
        zlags = zlags.reshape((8, 1))
        mode = ac.Mode(head)
        _, _, band_start = get_seq(mode)

        for ind in range(8):
            if (band_start == ind).any():
                cc64[ind, 0] = zlags[ind, 0]
                if cc64[ind, 2] > 0:
                    # find potential underflow in third element of cc
                    cc64[ind, 2] -= 65536
        if ac.IntTime(head) == 0:
            IntTime = 9999.
        else:
            IntTime = ac.IntTime(head)
        cc64 = cc64 * 2048.0 * (1 / IntTime) / (CLOCKFREQ / 2.0)
        mon = np.array(head[16:32], dtype="uint16")
        mon.shape = (8, 2)
        # find potential overflows/underflows in monitor values
        mon64 = np.bitwise_and(zlags, 0xf0000) + mon
        overflow_mask = np.abs(mon64 - zlags) > 0x8000
        mon64[overflow_mask & (mon64 > zlags)] -= 0x10000
        mon64[overflow_mask & (mon64 < zlags)] += 0x10000
        # scale
        mon64 = mon64 * 1024.0 * (1 / IntTime) / (CLOCKFREQ / 2.0)
        prescaler = head[49]
        datadict = {
            "stw": stw,
            "backend": back,
            "frontend": ac.Frontend(head),
            "sig_type": ac.Type(head),
            "ssb_att": "{{{0},{1},{2},{3}}}".format(*ac.Attenuation(head)),
            "ssb_fq": "{{{0},{1},{2},{3}}}".format(*ac.SSBfrequency(head)),
            "prescaler": prescaler,
            "inttime": IntTime,
            "mode": mode,
            "acd_mon": mon64,
            "cc": cc64,
        }
        return datadict
    raise EOFError


def getFBA(fba: FBAfile) -> dict[str, Any]:
    """AC factory.
    reads a fileobject and creates a dictionary for easy insertation
    into a postgresdatabase. Uses Ohlbergs routines to read the files (ACfile)
    """
    word = fba.getSpectrumHead()
    while word is not None:
        stw = fba.stw
        mech = fba.Type(word)
        datadict = {
            "stw": stw,
            "mech_type": mech,
        }
        return datadict
    raise EOFError


def getATT(datafile: str) -> list[dict[str, Any]]:
    """use Ohlbergs code to read in attitude data from file
    and creates a dictionary for easy insertation
    into a postgresdatabase.
    """
    ap = AttitudeParser([datafile])
    # sorting attitudes
    tbl = ap.table
    keys = sorted(tbl.keys())
    if not keys:
        return []
    key0 = keys[0]
    for key1 in keys[1:]:
        stw0 = tbl[key0][6]
        stw1 = tbl[key1][6]
        if stw1 - stw0 < 17:
            qe0 = tbl[key0][10]
            qe1 = tbl[key1][10]
            if qe0 != qe1:
                err0 = qe0[0] * qe0[0] + qe0[1] * qe0[1] + qe0[2] * qe0[2]
                err1 = qe1[0] * qe1[0] + qe1[1] * qe1[1] + qe1[2] * qe1[2]
                if err1 < err0:
                    del tbl[key0]
                    key0 = key1
                else:
                    del tbl[key1]
        else:
            key0 = key1

    datalist = []
    for key in keys:
        try:
            (year, mon, day, hour, minute,
             secs, stw, orbit, qt, qa, qe, gps, acs) = ap.table[key]
            datadict = {
                "year": year,
                "mon": mon,
                "day": day,
                "hour": hour,
                "min": minute,
                "secs": secs,
                "stw": stw,
                "orbit": orbit,
                "qt": "{{{0},{1},{2},{3}}}".format(*qt),
                "qa": "{{{0},{1},{2},{3}}}".format(*qa),
                "qe": "{{{0},{1},{2}}}".format(*qe),
                "gps": "{{{0},{1},{2},{3},{4},{5}}}".format(*gps),
                "acs": acs,
                "soda": int(ap.soda),
            }
            datalist.append(datadict)
        except BaseException:
            pass
    return datalist


def get_seq(mode: int) -> tuple[np.ndarray, list[list[int]], np.ndarray]:
    """get the ac chip configuration from the mode parameter"""
    seq = np.zeros(16, dtype=int)
    ssb = [1, -1, 1, -1, -1, 1, -1, 1]
    mode = (mode << 1) | 1
    for i in range(8):
        if (mode & 1):
            m = i
        seq[2 * m] = seq[2 * m] + 1
        mode >>= 1

    for i in range(8):
        if (seq[2 * i]):
            if (ssb[i] < 0):
                seq[2 * i + 1] = -1
            else:
                seq[2 * i + 1] = 1
        else:
            seq[2 * i + 1] = 0
    chips = []
    band_start = []
    band = 0
    # Chips is a list of vectors
    # For example chips=[[0], [1, 2, 3, 4], [5, 6, 7]] gives
    # that we observe three bands:
    #     - the first is from a single chip,
    #     - for second band chip 1,2,3,4 are cascaded,
    #     - for third band chip 5,6,7 are cascaded
    for ind, se in enumerate(seq):
        if ind == band:
            band_start.append(ind // 2)
            chips.append(list(range(ind // 2, ind // 2 + se)))
            band = ind + 2 * se

    return seq, chips, np.array(band_start)


def stw_correction(datafile: str) -> int:
    hex_part_of_filename = path.splitext(path.basename(datafile))[0]
    file_stw = int(hex_part_of_filename, 16) << 4
    return file_stw & 0xF00000000


def import_file(
    datafile: str,
    host: str,
    user: str,
    secret: str,
    db_name: str,
) -> dict[str, str]:
    pg_string = f"host={host} user={user} password={secret} dbname={db_name} sslmode=verify-ca"  # noqa: E501
    extension = path.splitext(datafile)[1]
    fgr = BytesIO()
    logger = logging.getLogger("level0 process")
    logger.info("importing file {0}".format(datafile))

    if extension == ".ac1" or extension == ".ac2":
        ac = ACfile(datafile)
        ac_2 = ACfile(datafile)
        while True:
            try:
                datadict = getAC(ac)
                discipline = getACdis(ac_2)
                datadict["stw"] += stw_correction(datafile)
                if (
                    datadict["inttime"] != 9999
                    and discipline == "AERO"
                    and datadict["frontend"] is not None
                    and datadict["sig_type"] != "problem"
                ):
                    # create an import file to dump in data into
                    fgr.write((
                        str(datadict["stw"]) + "\t"
                        + str(datadict["backend"]) + "\t"
                        + str(datadict["frontend"]) + "\t"
                        + str(datadict["sig_type"]) + "\t"
                        + str(datadict["ssb_att"]) + "\t"
                        + str(datadict["ssb_fq"]) + "\t"
                        + str(datadict["prescaler"]) + "\t"
                        + str(datadict["inttime"]) + "\t"
                        + str(datadict["mode"]) + "\t"
                        + "\\\\x" + codecs.encode(datadict["acd_mon"].tobytes(), "hex").decode() + "\t"  # noqa: E501
                        + "\\\\x" + codecs.encode(datadict["cc"].tobytes(), "hex").decode() + "\t"  # noqa: E501
                        + str(path.split(datafile)[1]) + "\t"
                        + str(datetime.now()) + "\n"
                    ).encode())
            except EOFError:
                break
            except ProgrammingError:
                continue
        with psycopg2.connect(pg_string) as conn:
            with conn.cursor() as cur:
                fgr.seek(0)
                cur.execute("create temporary table foo ( like ac_level0 );")
                cur.copy_from(file=fgr, table="foo")
                cur.execute(
                    "select stw, count(*) from foo group by stw having count(*) > 1"  # noqa: E501
                )

                with conn.cursor() as cur2:
                    for r in cur:
                        cur2.execute("""
                            delete from foo where stw={0}
                            and created=any(array(select created from foo
                            where stw={0} limit {1}))
                        """.format(*[r[0], r[1] - 1]))
                fgr.close()

                cur.execute("""
                    delete from ac_level0 ac using foo f
                    where f.stw=ac.stw and ac.backend=f.backend
                """)
                cur.execute("insert into ac_level0 (select * from foo)")
            conn.commit()

    elif extension == ".fba":
        fba = FBAfile(datafile)
        while True:
            try:
                datadict = getFBA(fba)
                datadict["stw"] += stw_correction(datafile)
                # create an import file to dump in data into db
                fgr.write((
                    str(datadict["stw"]) + "\t"
                    + str(datadict["mech_type"]) + "\t"
                    + str(path.split(datafile)[1]) + "\t"
                    + str(datetime.now()) + "\n"
                ).encode())
            except EOFError:
                break
            except ProgrammingError:
                continue

        with psycopg2.connect(pg_string) as conn:
            with conn.cursor() as cur:
                fgr.seek(0)
                cur.execute("create temporary table foo ( like fba_level0 );")
                cur.copy_from(file=fgr, table="foo")
                cur.execute(
                    "select stw, count(*) from foo group by stw having count(*) > 1"  # noqa: E501
                )

                with conn.cursor() as cur2:
                    for r in cur:
                        cur2.execute("""
                            delete from foo where stw={0} and
                            and created=any(array(
                                select created from foo where stw={0} limit {1}
                            ))
                        """.format(*[r[0], r[1] - 1]))
                fgr.close()

                cur.execute(
                    "delete from  fba_level0 fba using foo f where f.stw=fba.stw"  # noqa: E501
                )
                cur.execute("insert into fba_level0 (select * from foo)")
            conn.commit()

    elif extension == ".att":
        datalist = getATT(datafile)
        for datadict in datalist:
            fgr.write((
                str(datadict["stw"]) + "\t"
                + str(datadict["soda"]) + "\t"
                + str(datadict["year"]) + "\t"
                + str(datadict["mon"]) + "\t"
                + str(datadict["day"]) + "\t"
                + str(datadict["hour"]) + "\t"
                + str(datadict["min"]) + "\t"
                + str(datadict["secs"]) + "\t"
                + str(datadict["orbit"]) + "\t"
                + str(datadict["qt"]) + "\t"
                + str(datadict["qa"]) + "\t"
                + str(datadict["qe"]) + "\t"
                + str(datadict["gps"]) + "\t"
                + str(datadict["acs"]) + "\t"
                + str(path.split(datafile)[1]) + "\t"
                + str(datetime.now()) + "\n"
            ).encode())

        with psycopg2.connect(pg_string) as conn:
            with conn.cursor() as cur:
                fgr.seek(0)
                cur.execute(
                    "create temporary table foo ( like attitude_level0 );"
                )
                cur.copy_from(file=fgr, table="foo")
                fgr.close()

                cur.execute(
                    "delete from attitude_level0 att using foo f where f.stw=att.stw"  # noqa: E501
                )
                cur.execute("insert into attitude_level0 (select * from foo)")
            conn.commit()

    elif extension == ".shk":
        hk = SHKfile(datafile)
        datadict = getSHK(hk)
        for data in datadict:
            for index, stw in enumerate(datadict[data][0]):
                stw += stw_correction(datafile)
                fgr.write((
                    str(stw) + "\t"
                    + str(data) + "\t"
                    + str(float(datadict[data][1][index])) + "\t"
                    + str(path.split(datafile)[1]) + "\t"
                    + str(datetime.now()) + "\n"
                ).encode())

        with psycopg2.connect(pg_string) as conn:
            with conn.cursor() as cur:
                fgr.seek(0)
                cur.execute("create temporary table foo ( like shk_level0 );")
                cur.copy_from(file=fgr, table="foo")
                cur.execute("""
                    select stw,shk_type,count(*)
                    from foo group by stw, shk_type having count(*) > 1
                """)

                with conn.cursor() as cur2:
                    for r in cur:
                        cur2.execute("""
                            delete from foo where stw={0} and shk_type="{1}"
                            and created=any(array(select created from foo
                            where stw={0} and shk_type="{1}" limit {2}))
                        """.format(*[r[0], r[1], r[2] - 1]))
                fgr.close()

                cur.execute(
                    "delete from shk_level0 shk using foo f where f.stw=shk.stw"
                )
                cur.execute("insert into shk_level0 (select * from foo)")
            conn.commit()

    else:
        warnings.warn(
            f"{datafile} has unknown filetype",
            category=UnknownFileType,
        )
    return {
        "name": datafile,
        "type": extension[1:],
    }

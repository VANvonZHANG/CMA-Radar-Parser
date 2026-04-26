"""
This module contains the classes and functions to read and parse radar data 
from the CMA proprietary binary format.
"""
import dataclasses
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import List, Mapping, Optional

import numpy as np

class BaseBinaryReader:
    """A base class to unpack binary data into dataclass fields."""
    def from_bytes(self, burfer: bytes):
        all_fields = sorted(dataclasses.fields(self.__class__), key=lambda f: f.metadata["struct_index"])
        offset = 0
        for fld in all_fields:
            meta = fld.metadata
            size = meta["struct_size"]
            res = struct.unpack(meta["struct_type"], burfer[offset:offset+size])[0]
            if "s" in meta["struct_type"]:
                res = res.decode("utf-8", errors='ignore').strip("\x00").strip()
            setattr(self, fld.name, res)
            offset += size
        return self

    @property
    def len(self):
        """Calculates the total length of the struct from its fields."""
        return sum(f.metadata["struct_size"] for f in dataclasses.fields(self.__class__))

@dataclass(init=False)
class SiteConfig(BaseBinaryReader):
    """Dataclass for the site configuration block. Total size: 72 bytes."""
    SiteCode: str = field(metadata={"struct_index": 0, "struct_type": "8s", "struct_size": 8})
    SiteName: str = field(metadata={"struct_index": 1, "struct_type": "24s", "struct_size": 24})
    Latitude: float = field(metadata={"struct_index": 2, "struct_type": "f", "struct_size": 4})
    Longitude: float = field(metadata={"struct_index": 3, "struct_type": "f", "struct_size": 4})
    AntennaHeight: float = field(metadata={"struct_index": 4, "struct_type": "f", "struct_size": 4})
    GroundHeight: float = field(metadata={"struct_index": 5, "struct_type": "f", "struct_size": 4})
    AmendNorth: float = field(metadata={"struct_index": 6, "struct_type": "f", "struct_size": 4})
    RDAVersion: int = field(metadata={"struct_index": 7, "struct_type": "h", "struct_size": 2})
    RadarType: int = field(metadata={"struct_index": 8, "struct_type": "h", "struct_size": 2})
    Manufacturers: str = field(metadata={"struct_index": 9, "struct_type": "6s", "struct_size": 6})
    Reserved: str = field(metadata={"struct_index": 10, "struct_type": "10s", "struct_size": 10})

@dataclass(init=False)
class TaskConfig(BaseBinaryReader):
    """Dataclass for the task configuration block. Total size: 256 bytes."""
    TaskName: str = field(metadata={"struct_index": 0, "struct_type": "16s", "struct_size": 16})
    TaskDescription: str = field(metadata={"struct_index": 1, "struct_type": "96s", "struct_size": 96})
    PolarizationWay: int = field(metadata={"struct_index": 2, "struct_type": "h", "struct_size": 2})
    ScanType: int = field(metadata={"struct_index": 3, "struct_type": "h", "struct_size": 2})
    PulseWidth1: int = field(metadata={"struct_index": 4, "struct_type": "i", "struct_size": 4})
    PulseWidth2: int = field(metadata={"struct_index": 5, "struct_type": "i", "struct_size": 4})
    PulseWidth3: int = field(metadata={"struct_index": 6, "struct_type": "i", "struct_size": 4})
    PulseWidth4: int = field(metadata={"struct_index": 7, "struct_type": "i", "struct_size": 4})
    ScanStartTime: int = field(metadata={"struct_index": 8, "struct_type": "Q", "struct_size": 8})
    CutNumber: int = field(metadata={"struct_index": 9, "struct_type": "i", "struct_size": 4})
    HorizontalNoise: float = field(metadata={"struct_index": 10, "struct_type": "f", "struct_size": 4})
    VerticalNoise: float = field(metadata={"struct_index": 11, "struct_type": "f", "struct_size": 4})
    HorizontalCalibration1: float = field(metadata={"struct_index": 12, "struct_type": "f", "struct_size": 4})
    HorizontalCalibration2: float = field(metadata={"struct_index": 13, "struct_type": "f", "struct_size": 4})
    HorizontalCalibration3: float = field(metadata={"struct_index": 14, "struct_type": "f", "struct_size": 4})
    HorizontalCalibration4: float = field(metadata={"struct_index": 15, "struct_type": "f", "struct_size": 4})
    VerticalCalibration1: float = field(metadata={"struct_index": 16, "struct_type": "f", "struct_size": 4})
    VerticalCalibration2: float = field(metadata={"struct_index": 17, "struct_type": "f", "struct_size": 4})
    VerticalCalibration3: float = field(metadata={"struct_index": 18, "struct_type": "f", "struct_size": 4})
    VerticalCalibration4: float = field(metadata={"struct_index": 19, "struct_type": "f", "struct_size": 4})
    HorizontalNoiseTemperature: float = field(metadata={"struct_index": 20, "struct_type": "f", "struct_size": 4})
    VerticalNoiseTemperature: float = field(metadata={"struct_index": 21, "struct_type": "f", "struct_size": 4})
    ZDRCalibration: float = field(metadata={"struct_index": 22, "struct_type": "f", "struct_size": 4})
    PHIDPCalibration: float = field(metadata={"struct_index": 23, "struct_type": "f", "struct_size": 4})
    LDRCalibration: float = field(metadata={"struct_index": 24, "struct_type": "f", "struct_size": 4})
    NumberOfCoherentAccumulation1: bytes = field(metadata={"struct_index": 25, "struct_type": "c", "struct_size": 1})
    NumberOfCoherentAccumulation2: bytes = field(metadata={"struct_index": 26, "struct_type": "c", "struct_size": 1})
    NumberOfCoherentAccumulation3: bytes = field(metadata={"struct_index": 27, "struct_type": "c", "struct_size": 1})
    NumberOfCoherentAccumulation4: bytes = field(metadata={"struct_index": 28, "struct_type": "c", "struct_size": 1})
    FFTCount1: int = field(metadata={"struct_index": 29, "struct_type": "H", "struct_size": 2})
    FFTCount2: int = field(metadata={"struct_index": 30, "struct_type": "H", "struct_size": 2})
    FFTCount3: int = field(metadata={"struct_index": 31, "struct_type": "H", "struct_size": 2})
    FFTCount4: int = field(metadata={"struct_index": 32, "struct_type": "H", "struct_size": 2})
    AccumulationOfPowerSpectrum1: bytes = field(metadata={"struct_index": 33, "struct_type": "c", "struct_size": 1})
    AccumulationOfPowerSpectrum2: bytes = field(metadata={"struct_index": 34, "struct_type": "c", "struct_size": 1})
    AccumulationOfPowerSpectrum3: bytes = field(metadata={"struct_index": 35, "struct_type": "c", "struct_size": 1})
    AccumulationOfPowerSpectrum4: bytes = field(metadata={"struct_index": 36, "struct_type": "c", "struct_size": 1})
    PulseWidth1StartingPosition: int = field(metadata={"struct_index": 37, "struct_type": "I", "struct_size": 4})
    PulseWidth2StartingPosition: int = field(metadata={"struct_index": 38, "struct_type": "I", "struct_size": 4})
    PulseWidth3StartingPosition: int = field(metadata={"struct_index": 39, "struct_type": "I", "struct_size": 4})
    PulseWidth4StartingPosition: int = field(metadata={"struct_index": 40, "struct_type": "I", "struct_size": 4})
    Reserved: str = field(metadata={"struct_index": 41, "struct_type": "20s", "struct_size": 20})

@dataclass(init=False)
class CutConfig(BaseBinaryReader):
    """Dataclass for the cut configuration block. Total size: 256 bytes."""
    ProcessMode: int = field(metadata={"struct_index": 0, "struct_type": "h", "struct_size": 2})
    WaveForm: int = field(metadata={"struct_index": 1, "struct_type": "h", "struct_size": 2})
    PRF1: float = field(metadata={"struct_index": 2, "struct_type": "f", "struct_size": 4})
    PRF2: float = field(metadata={"struct_index": 3, "struct_type": "f", "struct_size": 4})
    PRF3: float = field(metadata={"struct_index": 4, "struct_type": "f", "struct_size": 4})
    PRF4: float = field(metadata={"struct_index": 5, "struct_type": "f", "struct_size": 4})
    PRFMode: int = field(metadata={"struct_index": 6, "struct_type": "h", "struct_size": 2})
    PulseWidthCombinationMode: int = field(metadata={"struct_index": 7, "struct_type": "h", "struct_size": 2})
    Azimuth: float = field(metadata={"struct_index": 8, "struct_type": "f", "struct_size": 4})
    Elevation: float = field(metadata={"struct_index": 9, "struct_type": "f", "struct_size": 4})
    StartAngle: float = field(metadata={"struct_index": 10, "struct_type": "f", "struct_size": 4})
    EndAngle: float = field(metadata={"struct_index": 11, "struct_type": "f", "struct_size": 4})
    AngularResolution: float = field(metadata={"struct_index": 12, "struct_type": "f", "struct_size": 4})
    ScanSpeed: float = field(metadata={"struct_index": 13, "struct_type": "f", "struct_size": 4})
    LogResolution: int = field(metadata={"struct_index": 14, "struct_type": "i", "struct_size": 4})
    DopplerResolution: int = field(metadata={"struct_index": 15, "struct_type": "i", "struct_size": 4})
    StartRange: int = field(metadata={"struct_index": 16, "struct_type": "i", "struct_size": 4})
    PhaseMode: int = field(metadata={"struct_index": 17, "struct_type": "i", "struct_size": 4})
    AtmosphericLoss: float = field(metadata={"struct_index": 18, "struct_type": "f", "struct_size": 4})
    NyquistSpeed: float = field(metadata={"struct_index": 19, "struct_type": "f", "struct_size": 4})
    MiscFilterMask: int = field(metadata={"struct_index": 20, "struct_type": "i", "struct_size": 4})
    SQIThreshold: float = field(metadata={"struct_index": 21, "struct_type": "f", "struct_size": 4})
    SIGThreshold: float = field(metadata={"struct_index": 22, "struct_type": "f", "struct_size": 4})
    CSRThreshold: float = field(metadata={"struct_index": 23, "struct_type": "f", "struct_size": 4})
    LOGThreshold: float = field(metadata={"struct_index": 24, "struct_type": "f", "struct_size": 4})
    CPAThreshold: float = field(metadata={"struct_index": 25, "struct_type": "f", "struct_size": 4})
    PMIThreshold: float = field(metadata={"struct_index": 26, "struct_type": "f", "struct_size": 4})
    DPLOGThreshold: float = field(metadata={"struct_index": 27, "struct_type": "f", "struct_size": 4})
    ThresholdsR: str = field(metadata={"struct_index": 28, "struct_type": "12s", "struct_size": 12})
    dBTMask: int = field(metadata={"struct_index": 29, "struct_type": "i", "struct_size": 4})
    dBZMask: int = field(metadata={"struct_index": 30, "struct_type": "i", "struct_size": 4})
    VelocityMask: int = field(metadata={"struct_index": 31, "struct_type": "i", "struct_size": 4})
    SpectrumWidthMask: int = field(metadata={"struct_index": 32, "struct_type": "i", "struct_size": 4})
    DPMask: int = field(metadata={"struct_index": 33, "struct_type": "i", "struct_size": 4})
    MaskReserved: str = field(metadata={"struct_index": 34, "struct_type": "12s", "struct_size": 12})
    ScanSync: int = field(metadata={"struct_index": 35, "struct_type": "i", "struct_size": 4})
    Direction: int = field(metadata={"struct_index": 36, "struct_type": "i", "struct_size": 4})
    GroundClutterClassifierType: int = field(metadata={"struct_index": 37, "struct_type": "h", "struct_size": 2})
    GroundClutterFilterType: int = field(metadata={"struct_index": 38, "struct_type": "h", "struct_size": 2})
    GroundClutterFilterNotchWidth: int = field(metadata={"struct_index": 39, "struct_type": "h", "struct_size": 2})
    GroundClutterFilterWindow: int = field(metadata={"struct_index": 40, "struct_type": "h", "struct_size": 2})
    Reserved: str = field(metadata={"struct_index": 41, "struct_type": "92s", "struct_size": 92})

@dataclass(init=False)
class RadarConfig(BaseBinaryReader):
    """Dataclass for the radar configuration block. Total size: 152 bytes."""
    Frequency: float = field(metadata={"struct_index": 0, "struct_type": "f", "struct_size": 4})
    Wavelength: float = field(metadata={"struct_index": 1, "struct_type": "f", "struct_size": 4})
    BeamWidthHori: float = field(metadata={"struct_index": 2, "struct_type": "f", "struct_size": 4})
    BeamWidthVert: float = field(metadata={"struct_index": 3, "struct_type": "f", "struct_size": 4})
    TransmitterPeakPower: float = field(metadata={"struct_index": 4, "struct_type": "f", "struct_size": 4})
    AntennaGain: float = field(metadata={"struct_index": 5, "struct_type": "f", "struct_size": 4})
    TotalLoss: float = field(metadata={"struct_index": 6, "struct_type": "f", "struct_size": 4})
    ReceiverGain: float = field(metadata={"struct_index": 7, "struct_type": "f", "struct_size": 4})
    FirstSide: float = field(metadata={"struct_index": 8, "struct_type": "f", "struct_size": 4})
    ReceiverDynamicRange: float = field(metadata={"struct_index": 9, "struct_type": "f", "struct_size": 4})
    ReceiverSensitivity: float = field(metadata={"struct_index": 10, "struct_type": "f", "struct_size": 4})
    BandWidth: float = field(metadata={"struct_index": 11, "struct_type": "f", "struct_size": 4})
    MaxExploreRange: int = field(metadata={"struct_index": 12, "struct_type": "I", "struct_size": 4})
    DistanceSolution: int = field(metadata={"struct_index": 13, "struct_type": "H", "struct_size": 2})
    PolarizationType: int = field(metadata={"struct_index": 14, "struct_type": "H", "struct_size": 2})
    Reserved: str = field(metadata={"struct_index": 15, "struct_type": "96s", "struct_size": 96})

@dataclass(init=False)
class RadialHeader(BaseBinaryReader):
    """Dataclass for the radial header block. Total size: 64 bytes."""
    RadialState: int = field(metadata={"struct_index": 0, "struct_type": "h", "struct_size": 2})
    SpotBlank: int = field(metadata={"struct_index": 1, "struct_type": "h", "struct_size": 2})
    SequenceNumber: int = field(metadata={"struct_index": 2, "struct_type": "H", "struct_size": 2})
    RadialNumber: int = field(metadata={"struct_index": 3, "struct_type": "H", "struct_size": 2})
    MomentNumber: int = field(metadata={"struct_index": 4, "struct_type": "H", "struct_size": 2})
    ElevationNumber: int = field(metadata={"struct_index": 5, "struct_type": "H", "struct_size": 2})
    Azimuth: float = field(metadata={"struct_index": 6, "struct_type": "f", "struct_size": 4})
    Elevation: float = field(metadata={"struct_index": 7, "struct_type": "f", "struct_size": 4})
    Seconds: int = field(metadata={"struct_index": 8, "struct_type": "Q", "struct_size": 8})
    Microseconds: int = field(metadata={"struct_index": 9, "struct_type": "I", "struct_size": 4})
    LengthOfData: int = field(metadata={"struct_index": 10, "struct_type": "I", "struct_size": 4})
    Duration: int = field(metadata={"struct_index": 11, "struct_type": "H", "struct_size": 2})
    MaxFFTCount: int = field(metadata={"struct_index": 12, "struct_type": "H", "struct_size": 2})
    Reserved: str = field(metadata={"struct_index": 13, "struct_type": "24s", "struct_size": 24})

@dataclass(init=False)
class MomentHeader(BaseBinaryReader):
    """Dataclass for the moment header block. Total size: 32 bytes."""
    DataType: int = field(metadata={"struct_index": 0, "struct_type": "H", "struct_size": 2})
    Scale: int = field(metadata={"struct_index": 1, "struct_type": "H", "struct_size": 2})
    Offset: int = field(metadata={"struct_index": 2, "struct_type": "H", "struct_size": 2})
    BinBytes: int = field(metadata={"struct_index": 3, "struct_type": "H", "struct_size": 2})
    BinNumber: int = field(metadata={"struct_index": 4, "struct_type": "H", "struct_size": 2})
    Flags: int = field(metadata={"struct_index": 5, "struct_type": "h", "struct_size": 2})
    DataLength: int = field(metadata={"struct_index": 6, "struct_type": "i", "struct_size": 4})
    Reserved: str = field(metadata={"struct_index": 7, "struct_type": "16s", "struct_size": 16})

@dataclass
class MomentData:
    """Container for a single moment's data and header."""
    header: MomentHeader
    value: np.array

@dataclass
class RadialData:
    """Container for a single radial's data and header."""
    header: Optional[RadialHeader] = None
    variable: Mapping[int, MomentData] = field(default_factory=dict)

@dataclass
class CmaRadarData:
    """Top-level container for all parsed CMA radar data."""
    site_config: Optional[SiteConfig] = None
    radar_config: Optional[RadarConfig] = None
    task_config: Optional[TaskConfig] = None
    cut_configs: List[CutConfig] = field(default_factory=list)
    radials: List[RadialData] = field(default_factory=list)

def read_cma_radar(filename: str) -> CmaRadarData:
    """Reads and parses a CMA binary radar file."""
    obj = CmaRadarData()
    with open(filename, "rb") as f:
        f.seek(32)  # Skip GenericHeader
        obj.site_config = SiteConfig().from_bytes(f.read(SiteConfig().len))
        obj.radar_config = RadarConfig().from_bytes(f.read(RadarConfig().len))
        obj.task_config = TaskConfig().from_bytes(f.read(TaskConfig().len))
        for _ in range(obj.task_config.CutNumber):
            obj.cut_configs.append(CutConfig().from_bytes(f.read(CutConfig().len)))
        
        while f.tell() < os.path.getsize(filename):
            header_bytes = f.read(RadialHeader().len)
            if len(header_bytes) < RadialHeader().len: break
            
            radial_obj = RadialData(header=RadialHeader().from_bytes(header_bytes))
            for _ in range(radial_obj.header.MomentNumber):
                moment_header_bytes = f.read(MomentHeader().len)
                if len(moment_header_bytes) < MomentHeader().len: break
                
                header = MomentHeader().from_bytes(moment_header_bytes)
                data_bytes = f.read(header.DataLength)
                if len(data_bytes) < header.DataLength: break

                try:
                    if header.BinBytes == 1:
                        res = np.array(struct.unpack(f"<{header.BinNumber}B", data_bytes), dtype=float)
                    elif header.BinBytes == 2:
                        res = np.array(struct.unpack(f"<{header.BinNumber}H", data_bytes), dtype=float)
                    else:
                        res = np.full(header.BinNumber, np.nan, dtype=float)
                except struct.error:
                    logging.warning(f"Could not unpack moment data for type {header.DataType}")
                    continue
                
                res[res == 0] = np.nan
                data = (res - header.Offset) / header.Scale
                data[data == 32768 / header.Scale] = np.nan
                
                radial_obj.variable[header.DataType] = MomentData(header=header, value=data)
            
            if radial_obj.variable:
                obj.radials.append(radial_obj)
    return obj

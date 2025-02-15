import numpy as np
from typing import overload, Union

from generic.physics.constants import SPEED_OF_LIGHT


'''
@overload
def freq_to_wvln(freq: float) -> float:
    ...


@overload
def freq_to_wvln(freq: np.ndarray) -> np.ndarray:
    ...


def freq_to_wvln(freq: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Standard conversion from frequency to wavelength.

    Args:
        freq - Frequency [MHz]
    Returns:
        wvln - Wavelength [m]
    """
    wvln = SPEED_OF_LIGHT / (freq * 1e6)
    return wvln


@overload
def wvln_to_freq(wvln: float) -> float:
    ...


@overload
def wvln_to_freq(wvln: np.ndarray) -> np.ndarray:
    ...


def wvln_to_freq(wvln: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Standard conversion from wavelength to frequency.

    Args:
        wvln - Wavelength [m]
    Returns:
        freq - Frequency [MHz]
    """
    freq = (SPEED_OF_LIGHT / (wvln)) * 1e-6
    return freq


@overload
def db_to_decimal(db: float) -> float:
    ...


@overload
def db_to_decimal(db: np.ndarray) -> np.ndarray:
    ...


def db_to_decimal(db: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Standard conversion from decibels [dB] to decimal loss.

    Args:
        db - Absolute power loss [dB]
    Returns:
        dm - Decimal loss
    """
    dm = 10 ** (db / 10) - 1
    return dm
'''

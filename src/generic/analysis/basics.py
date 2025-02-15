from rtlsdr import RtlSdr

sdr = RtlSdr()

# configure device
sdr.sample_rate = 2.048e6  # Hz
sdr.center_freq = 70e6  # Hz
sdr.freq_correction = 60  # PPM
sdr.gain = "auto"

samples = sdr.read_samples(512)


'''
def unpack_coordinates(
    arr: np.ndarray,
) -> Union[Tuple[float, float, float], Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Examines the dimension length of a coordinate array and resizes array dimensions
    to match downstream expected formats.

    Args:
        arr (np.ndarray): Array containing coordinate array

    Returns:
        Three dimension values of the input array.
    """
    if len(arr.shape) == 1:
        return arr[0], arr[1], arr[2]
    elif arr.shape[0] == 1:
        return arr[0, 0], arr[0, 1], arr[0, 2]
    else:
        return arr[:, 0], arr[:, 1], arr[:, 2]
'''

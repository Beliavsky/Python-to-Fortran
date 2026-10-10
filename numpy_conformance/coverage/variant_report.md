# numpy coverage probe: input variants

1846 variants.

| status | count |
|---|---|
| DIFF | 23 |
| RUN-FAIL | 3 |
| XLATE-FAIL | 20 |
| MATCH | 1800 |

## Known differences

- `np.bartlett[empty]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.bartlett[int]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.bartlett[nan]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.bartlett[one]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.bartlett[ties]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman[empty]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman[int]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman[nan]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman[one]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.blackman[ties]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.digitize[nan]` (RUN-FAIL): bins with NaN are rejected as not monotonic
- `np.empty_like[int]` (DIFF): uninitialized values
- `np.fft.fft2[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.fft[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.fftn[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.ifft2[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.ifft[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.ifftn[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.ihfft[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.rfft2[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.rfft[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.fft.rfftn[nan]` (DIFF): NaN propagation through the FFT differs (numpy keeps some parts finite)
- `np.frexp[nan]` (DIFF): the exponent of inf and NaN is platform-dependent (0 here, numpy on Windows -1)
- `np.hamming[empty]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hamming[int]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hamming[nan]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hamming[one]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hamming[ties]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning[empty]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning[int]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning[nan]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning[one]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.hanning[ties]` (XLATE-FAIL): the probe's float M is rejected (M must be an integer)
- `np.interp[nan]` (DIFF): xp with NaN and inf (not increasing, as numpy requires)
- `np.linalg.pinv[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.qr[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.solve[nan]` (DIFF): NaN propagation through the LAPACK factorization differs
- `np.linalg.svd[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.svdvals[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.nonzero[empty]` (DIFF): the probe reads numpy's dtype=int64 as a number
- `np.polymul[empty]` (DIFF): empty coefficient arrays
- `np.resize[empty]` (RUN-FAIL): resizing an empty array
- `np.roots[ties]` (DIFF): the roots in another order (eigenvalue order)
- `np.setxor1d[nan]` (DIFF): NaN treated as one value
- `np.vander[empty]` (RUN-FAIL): an empty array
- `np.where[empty]` (DIFF): the probe reads numpy's dtype=int64 as a number

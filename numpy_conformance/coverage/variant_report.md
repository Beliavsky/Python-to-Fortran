# numpy coverage probe: input variants

2626 variants.

| status | count |
|---|---|
| DIFF | 22 |
| RUN-FAIL | 3 |
| XLATE-FAIL | 34 |
| MATCH | 2567 |

## XLATE-FAIL

- `np.asarray_chkfinite[complex]`: unsupported call: np.asarray_chkfinite(x)
- `np.diag_indices_from[3d]`: unsupported assign: r0, r1, r2 = np.diag_indices_from(m)
- `np.histogram_bin_edges[complex]`: np.histogram of a complex array is not supported (the translation would drop the imaginary part)
- `np.linalg.eigh[complex]`: np.linalg.eigh of a complex matrix is not supported (numpy's eigenvector phases come from LAPACK's zheevd; np.linalg.eigvalsh gives the eigenvalues)
- `np.linalg.lstsq[complex]`: np.linalg.lstsq currently supports real inputs only
- `np.linalg.qr[complex]`: np.linalg.qr of a complex matrix is not supported (numpy's Q and R phases come from LAPACK's zgeqrf)
- `np.linalg.svd[complex]`: np.linalg.svd of a complex matrix supports only the singular values (svdvals or compute_uv=False)
- `np.poly[complex]`: np.poly of complex roots is not supported
- `np.polynomial.chebyshev.chebcompanion[complex]`: np.polynomial.chebyshev.chebcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebdiv[complex]`: np.polynomial.chebyshev.chebdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebroots[complex]`: np.polynomial.chebyshev.chebroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebvander[complex]`: np.polynomial.chebyshev.chebvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermcompanion[complex]`: np.polynomial.hermite.hermcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermdiv[complex]`: np.polynomial.hermite.hermdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermroots[complex]`: np.polynomial.hermite.hermroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermvander[complex]`: np.polynomial.hermite.hermvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermecompanion[complex]`: np.polynomial.hermite_e.hermecompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermediv[complex]`: np.polynomial.hermite_e.hermediv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeroots[complex]`: np.polynomial.hermite_e.hermeroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermevander[complex]`: np.polynomial.hermite_e.hermevander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagcompanion[complex]`: np.polynomial.laguerre.lagcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagdiv[complex]`: np.polynomial.laguerre.lagdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagroots[complex]`: np.polynomial.laguerre.lagroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagvander[complex]`: np.polynomial.laguerre.lagvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legcompanion[complex]`: np.polynomial.legendre.legcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legdiv[complex]`: np.polynomial.legendre.legdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legroots[complex]`: np.polynomial.legendre.legroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legvander[complex]`: np.polynomial.legendre.legvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polycompanion[complex]`: np.polynomial.polynomial.polycompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polydiv[complex]`: np.polynomial.polynomial.polydiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyroots[complex]`: np.polynomial.polynomial.polyroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.real_if_close[complex]`: np.real_if_close of a complex array is not supported (the translation would drop the imaginary part)
- `np.roots[complex]`: np.roots of a complex array is not supported (the translation would drop the imaginary part)
- `np.searchsorted[complex]`: np.searchsorted of complex numbers is not supported

## Known differences

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
- `np.interp[nan]` (DIFF): xp with NaN and inf (not increasing, as numpy requires)
- `np.linalg.pinv[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.qr[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.solve[nan]` (DIFF): NaN propagation through the LAPACK factorization differs
- `np.linalg.svd[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.linalg.svdvals[empty]` (DIFF): empty matrices are not supported (LAPACK reports an illegal argument)
- `np.nonzero[empty]` (DIFF): the probe reads numpy's dtype=int64 as a number
- `np.polymul[empty]` (DIFF): empty coefficient arrays
- `np.resize[empty]` (RUN-FAIL): resizing an empty array
- `np.setxor1d[nan]` (DIFF): NaN treated as one value
- `np.vander[empty]` (RUN-FAIL): an empty array
- `np.where[empty]` (DIFF): the probe reads numpy's dtype=int64 as a number

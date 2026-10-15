# numpy coverage probe: input variants

2597 variants.

| status | count |
|---|---|
| DIFF | 24 |
| RUN-FAIL | 3 |
| BUILD-FAIL | 11 |
| XLATE-FAIL | 104 |
| MATCH | 2455 |

## BUILD-FAIL

- `np.linalg.cond[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.det[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.eigh[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.eigvalsh[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.inv[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.matrix_power[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.pinv[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.qr[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.slogdet[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.svd[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)
- `np.linalg.svdvals[complex]`: Type mismatch in argument 'a' at (1); passed COMPLEX(8) to REAL(8)

## XLATE-FAIL

- `np.asarray_chkfinite[complex]`: unsupported call: np.asarray_chkfinite(x)
- `np.diag_indices_from[3d]`: unsupported assign: r0, r1, r2 = np.diag_indices_from(m)
- `np.histogram_bin_edges[complex]`: np.histogram of a complex array is not supported (the translation would drop the imaginary part)
- `np.linalg.cholesky[complex]`: complex Cholesky is not supported by the real-valued helper
- `np.linalg.lstsq[complex]`: np.linalg.lstsq currently supports real inputs only
- `np.poly[complex]`: np.poly of complex roots is not supported
- `np.polynomial.chebyshev.cheb2poly[complex]`: np.polynomial.chebyshev.cheb2poly of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebadd[complex]`: np.polynomial.chebyshev.chebadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebcompanion[complex]`: np.polynomial.chebyshev.chebcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebder[complex]`: np.polynomial.chebyshev.chebder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebdiv[complex]`: np.polynomial.chebyshev.chebdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebfromroots[complex]`: np.polynomial.chebyshev.chebfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebint[complex]`: np.polynomial.chebyshev.chebint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebmul[complex]`: np.polynomial.chebyshev.chebmul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebmulx[complex]`: np.polynomial.chebyshev.chebmulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebpow[complex]`: np.polynomial.chebyshev.chebpow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebsub[complex]`: np.polynomial.chebyshev.chebsub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebtrim[complex]`: np.polynomial.chebyshev.chebtrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebval[complex]`: np.polynomial.chebyshev.chebval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.chebvander[complex]`: np.polynomial.chebyshev.chebvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.chebyshev.poly2cheb[complex]`: np.polynomial.chebyshev.poly2cheb of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.herm2poly[complex]`: np.polynomial.hermite.herm2poly of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermadd[complex]`: np.polynomial.hermite.hermadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermcompanion[complex]`: np.polynomial.hermite.hermcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermder[complex]`: np.polynomial.hermite.hermder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermdiv[complex]`: np.polynomial.hermite.hermdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermfromroots[complex]`: np.polynomial.hermite.hermfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermint[complex]`: np.polynomial.hermite.hermint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermmul[complex]`: np.polynomial.hermite.hermmul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermmulx[complex]`: np.polynomial.hermite.hermmulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermpow[complex]`: np.polynomial.hermite.hermpow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermsub[complex]`: np.polynomial.hermite.hermsub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermtrim[complex]`: np.polynomial.hermite.hermtrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermval[complex]`: np.polynomial.hermite.hermval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermvander[complex]`: np.polynomial.hermite.hermvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.hermweight[complex]`: np.polynomial.hermite.hermweight of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite.poly2herm[complex]`: np.polynomial.hermite.poly2herm of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.herme2poly[complex]`: np.polynomial.hermite_e.herme2poly of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeadd[complex]`: np.polynomial.hermite_e.hermeadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermecompanion[complex]`: np.polynomial.hermite_e.hermecompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeder[complex]`: np.polynomial.hermite_e.hermeder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermediv[complex]`: np.polynomial.hermite_e.hermediv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermefromroots[complex]`: np.polynomial.hermite_e.hermefromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeint[complex]`: np.polynomial.hermite_e.hermeint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermemul[complex]`: np.polynomial.hermite_e.hermemul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermemulx[complex]`: np.polynomial.hermite_e.hermemulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermepow[complex]`: np.polynomial.hermite_e.hermepow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermesub[complex]`: np.polynomial.hermite_e.hermesub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermetrim[complex]`: np.polynomial.hermite_e.hermetrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeval[complex]`: np.polynomial.hermite_e.hermeval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermevander[complex]`: np.polynomial.hermite_e.hermevander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.hermeweight[complex]`: np.polynomial.hermite_e.hermeweight of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.hermite_e.poly2herme[complex]`: np.polynomial.hermite_e.poly2herme of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lag2poly[complex]`: np.polynomial.laguerre.lag2poly of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagadd[complex]`: np.polynomial.laguerre.lagadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagcompanion[complex]`: np.polynomial.laguerre.lagcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagder[complex]`: np.polynomial.laguerre.lagder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagdiv[complex]`: np.polynomial.laguerre.lagdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagfromroots[complex]`: np.polynomial.laguerre.lagfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagint[complex]`: np.polynomial.laguerre.lagint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagmul[complex]`: np.polynomial.laguerre.lagmul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagmulx[complex]`: np.polynomial.laguerre.lagmulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagpow[complex]`: np.polynomial.laguerre.lagpow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagsub[complex]`: np.polynomial.laguerre.lagsub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagtrim[complex]`: np.polynomial.laguerre.lagtrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagval[complex]`: np.polynomial.laguerre.lagval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagvander[complex]`: np.polynomial.laguerre.lagvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.lagweight[complex]`: np.polynomial.laguerre.lagweight of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.laguerre.poly2lag[complex]`: np.polynomial.laguerre.poly2lag of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.leg2poly[complex]`: np.polynomial.legendre.leg2poly of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legadd[complex]`: np.polynomial.legendre.legadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legcompanion[complex]`: np.polynomial.legendre.legcompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legder[complex]`: np.polynomial.legendre.legder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legdiv[complex]`: np.polynomial.legendre.legdiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legfromroots[complex]`: np.polynomial.legendre.legfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legint[complex]`: np.polynomial.legendre.legint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legmul[complex]`: np.polynomial.legendre.legmul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legmulx[complex]`: np.polynomial.legendre.legmulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legpow[complex]`: np.polynomial.legendre.legpow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legsub[complex]`: np.polynomial.legendre.legsub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legtrim[complex]`: np.polynomial.legendre.legtrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legval[complex]`: np.polynomial.legendre.legval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legvander[complex]`: np.polynomial.legendre.legvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.legweight[complex]`: np.polynomial.legendre.legweight of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.legendre.poly2leg[complex]`: np.polynomial.legendre.poly2leg of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyadd[complex]`: np.polynomial.polynomial.polyadd of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polycompanion[complex]`: np.polynomial.polynomial.polycompanion of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyder[complex]`: np.polynomial.polynomial.polyder of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polydiv[complex]`: np.polynomial.polynomial.polydiv of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyfromroots[complex]`: np.polynomial.polynomial.polyfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyint[complex]`: np.polynomial.polynomial.polyint of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polymul[complex]`: np.polynomial.polynomial.polymul of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polymulx[complex]`: np.polynomial.polynomial.polymulx of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polypow[complex]`: np.polynomial.polynomial.polypow of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polysub[complex]`: np.polynomial.polynomial.polysub of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polytrim[complex]`: np.polynomial.polynomial.polytrim of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyval[complex]`: np.polynomial.polynomial.polyval of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyvalfromroots[complex]`: np.polynomial.polynomial.polyvalfromroots of a complex array is not supported (the translation would drop the imaginary part)
- `np.polynomial.polynomial.polyvander[complex]`: np.polynomial.polynomial.polyvander of a complex array is not supported (the translation would drop the imaginary part)
- `np.real_if_close[complex]`: np.real_if_close of a complex array is not supported (the translation would drop the imaginary part)
- `np.searchsorted[complex]`: np.searchsorted of complex numbers is not supported

## Known differences

- `np.cov[complex]` (DIFF): a real number (numpy's complex result of a vector has a zero imaginary part)
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
- `np.polynomial.legendre.legroots[complex]` (XLATE-FAIL): always complex in the translation
- `np.polynomial.polynomial.polyroots[complex]` (XLATE-FAIL): always complex in the translation
- `np.resize[empty]` (RUN-FAIL): resizing an empty array
- `np.roots[complex]` (XLATE-FAIL): always complex in the translation
- `np.roots[ties]` (DIFF): the roots in another order (eigenvalue order)
- `np.setxor1d[nan]` (DIFF): NaN treated as one value
- `np.vander[empty]` (RUN-FAIL): an empty array
- `np.where[empty]` (DIFF): the probe reads numpy's dtype=int64 as a number

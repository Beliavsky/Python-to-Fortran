! python_mod: the Fortran runtime of xp2f.py, and numerical routines that can be
! called directly from Fortran. Code adapted from other projects says so in its
! own comments; see the "Third-Party Code" section of README.md for the sources
! and licenses (John Burkardt's prob.f90, pyccel, Alan Miller's dceigv.f90, and
! numpy's algorithms). Routines that use LAPACK (lapack_d.f90) or roots-fortran
! (root.f90) need those files linked too.
module python_mod
use, intrinsic :: iso_fortran_env, only: real64, int64
use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_is_nan, ieee_value, ieee_quiet_nan
implicit none
private
integer, parameter :: dp = real64
logical, parameter :: fft_use_fast = .true.
logical :: rng_replay_checked = .false.
logical :: rng_replay_enabled = .false.
integer :: rng_replay_meta_u = -1
integer :: rng_replay_bin_u = -1
integer :: rng_replay_call_index = 0
character(len=:), allocatable :: rng_replay_stem

type :: strvec_t
   character(len=:), allocatable :: v(:)
end type strvec_t

public :: isqrt_int       !@pyapi kind=function ret=integer args=x:integer:intent(in) lib=integers desc="integer square root: return floor(sqrt(x)) for x >= 0"
public :: mod_pow_int !@pyapi kind=function ret=integer args=base:integer:intent(in),exp:integer:intent(in),modulus:integer:intent(in) lib=integers desc="modular exponentiation: pow(base, exp, modulus) for integer inputs"
public :: factorial_int !@pyapi kind=function ret=integer args=x:integer:intent(in) lib=integers desc="factorial for nonnegative integers"
public :: comb_int !@pyapi kind=function ret=integer args=n:integer:intent(in),k:integer:intent(in) lib=integers desc="binomial coefficient for integer inputs"
public :: perm_int !@pyapi kind=function ret=integer args=n:integer:intent(in),k:integer:intent(in):optional lib=integers desc="permutations nPk for integer inputs"
public :: print_int_list  !@pyapi kind=subroutine args=a:integer(:):intent(in),n:integer:intent(in) desc="print integer list a(1:n) in python-style [..] format"
public :: print_char_list  !@pyapi kind=subroutine args=a:character(:):intent(in),n:integer:intent(in) desc="print character list a(1:n) in python-style [..] format"
public :: grow_and_set_char !@pyapi kind=subroutine args=arr:character(:)(:):intent(inout),idx:integer:intent(in),item:character(*):intent(in) desc="grow allocatable character list arr (size and/or declared length) so index idx and item both fit, then set arr(idx) = item"
public :: insert_char !@pyapi kind=subroutine args=arr:character(:)(:):intent(inout),idx:integer:intent(in),item:character(*):intent(in) desc="insert item into allocatable character list arr at Python-style index idx, widening declared length if needed"
public :: print_real_list  !@pyapi kind=subroutine args=a:real(dp)(:):intent(in),n:integer:intent(in) desc="print real list a(1:n) in python-style [..] format"
public :: print_log_list  !@pyapi kind=subroutine args=a:logical(:):intent(in),n:integer:intent(in) desc="print logical list a(1:n) in python-style [..] format"
public :: str_int_list  !@pyapi kind=function ret=character args=a:integer(:):intent(in),n:integer:intent(in) desc="return integer list a(1:n) in python-style [..] format"
public :: seed_rng !@pyapi kind=subroutine args=seed:integer:intent(in):optional lib=random desc="seed intrinsic RNG; deterministic stream when seed is provided"
public :: random_normal_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out) lib=random desc="fill x with N(0,1) variates using Box-Muller"
public :: runif !@pyapi kind=function ret=real(dp) args=n:integer:intent(in):optional,m:integer:intent(in):optional desc="uniform variates: scalar runif(), vector runif(n), matrix runif(n,m)"
public :: rnorm !@pyapi kind=function ret=real(dp) args=n:integer:intent(in):optional,m:integer:intent(in):optional desc="normal variates: scalar rnorm(), vector rnorm(n), matrix rnorm(n,m)"
public :: random_randrange_int !@pyapi kind=function ret=integer args=start:integer:intent(in),stop:integer:intent(in),step:integer:intent(in) desc="random integer from range(start, stop, step)"
public :: random_exponential !@pyapi kind=function ret=real(dp) args=scale:real(dp):intent(in):optional lib=random desc="sample scalar exponential with scale (default 1)"
public :: random_exponential_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),scale:real(dp):intent(in):optional lib=random desc="fill x with exponential samples with scale (default 1)"
public :: random_gamma !@pyapi kind=function ret=real(dp) args=shape:real(dp):intent(in),scale:real(dp):intent(in):optional lib=random desc="sample scalar gamma(shape, scale), shape>0"
public :: random_gamma_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),shape:real(dp):intent(in),scale:real(dp):intent(in):optional lib=random desc="fill x with gamma samples"
public :: random_student_t !@pyapi kind=function ret=real(dp) args=df:real(dp):intent(in) lib=random desc="sample scalar Student t(df)"
public :: random_student_t_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),df:real(dp):intent(in) lib=random desc="fill x with Student t(df) samples"
public :: random_f !@pyapi kind=function ret=real(dp) args=dfnum:real(dp):intent(in),dfden:real(dp):intent(in) lib=random desc="sample scalar F(dfnum,dfden)"
public :: random_f_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),dfnum:real(dp):intent(in),dfden:real(dp):intent(in) lib=random desc="fill x with F samples"
public :: random_poisson !@pyapi kind=function ret=integer args=mu:real(dp):intent(in) lib=random desc="sample scalar Poisson(mu)"
public :: random_poisson_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),mu:real(dp):intent(in) lib=random desc="fill x with Poisson(mu) samples"
public :: random_geometric !@pyapi kind=function ret=integer args=p:real(dp):intent(in) lib=random desc="sample scalar Geometric(p), support on {1,2,...}"
public :: random_geometric_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),p:real(dp):intent(in) lib=random desc="fill x with Geometric(p) samples"
public :: random_binomial !@pyapi kind=function ret=integer args=n:integer:intent(in),p:real(dp):intent(in) lib=random desc="sample scalar Binomial(n,p)"
public :: random_binomial_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),n:integer:intent(in),p:real(dp):intent(in) lib=random desc="fill x with Binomial(n,p) samples"
public :: random_hypergeometric !@pyapi kind=function ret=integer args=ngood:integer:intent(in),nbad:integer:intent(in),nsample:integer:intent(in) lib=random desc="sample scalar Hypergeometric(ngood,nbad,nsample)"
public :: random_hypergeometric_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),ngood:integer:intent(in),nbad:integer:intent(in),nsample:integer:intent(in) lib=random desc="fill x with hypergeometric samples"
public :: random_zipf !@pyapi kind=function ret=integer args=a:real(dp):intent(in) lib=random desc="sample scalar Zipf(a), a>1"
public :: random_zipf_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),a:real(dp):intent(in) lib=random desc="fill x with Zipf(a) samples"
public :: random_weibull !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in) lib=random desc="sample scalar Weibull(a)"
public :: random_weibull_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),a:real(dp):intent(in) lib=random desc="fill x with Weibull(a) samples"
public :: random_neg_binomial !@pyapi kind=function ret=integer args=sk:real(dp):intent(in),p:real(dp):intent(in) lib=random desc="sample scalar negative binomial failures before sk successes"
public :: random_neg_binomial_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),sk:real(dp):intent(in),p:real(dp):intent(in) lib=random desc="fill x with negative binomial samples"
public :: random_von_mises !@pyapi kind=function ret=real(dp) args=kappa:real(dp):intent(in) lib=random desc="sample scalar von Mises with concentration kappa"
public :: random_von_mises_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),kappa:real(dp):intent(in) lib=random desc="fill x with von Mises samples"
public :: random_pareto !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in) lib=random desc="sample scalar Pareto(a) in NumPy convention"
public :: random_pareto_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),a:real(dp):intent(in) lib=random desc="fill x with Pareto(a) samples"
public :: random_power !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in) lib=random desc="sample scalar Power(a) in NumPy convention"
public :: random_power_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),a:real(dp):intent(in) lib=random desc="fill x with Power(a) samples"
public :: random_rayleigh !@pyapi kind=function ret=real(dp) args=scale:real(dp):intent(in):optional lib=random desc="sample scalar Rayleigh(scale), default scale=1"
public :: random_rayleigh_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),scale:real(dp):intent(in):optional lib=random desc="fill x with Rayleigh samples"
public :: random_gumbel !@pyapi kind=function ret=real(dp) args=loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="sample scalar Gumbel(loc,scale)"
public :: random_gumbel_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="fill x with Gumbel samples"
public :: random_wald !@pyapi kind=function ret=real(dp) args=mean:real(dp):intent(in),scale:real(dp):intent(in) lib=random desc="sample scalar Wald(mean,scale)"
public :: random_wald_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),mean:real(dp):intent(in),scale:real(dp):intent(in) lib=random desc="fill x with Wald samples"
public :: random_noncentral_chisquare !@pyapi kind=function ret=real(dp) args=df:real(dp):intent(in),nonc:real(dp):intent(in) lib=random desc="sample scalar noncentral chisquare(df,nonc)"
public :: random_noncentral_chisquare_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),df:real(dp):intent(in),nonc:real(dp):intent(in) lib=random desc="fill x with noncentral chisquare samples"
public :: random_noncentral_f !@pyapi kind=function ret=real(dp) args=dfnum:real(dp):intent(in),dfden:real(dp):intent(in),nonc:real(dp):intent(in) lib=random desc="sample scalar noncentral F(dfnum,dfden,nonc)"
public :: random_noncentral_f_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),dfnum:real(dp):intent(in),dfden:real(dp):intent(in),nonc:real(dp):intent(in) lib=random desc="fill x with noncentral F samples"
public :: random_triangular !@pyapi kind=function ret=real(dp) args=left:real(dp):intent(in),mode:real(dp):intent(in),right:real(dp):intent(in) lib=random desc="sample scalar triangular(left,mode,right)"
public :: random_triangular_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),left:real(dp):intent(in),mode:real(dp):intent(in),right:real(dp):intent(in) lib=random desc="fill x with triangular samples"
public :: random_logseries !@pyapi kind=function ret=integer args=p:real(dp):intent(in) lib=random desc="sample scalar logarithmic-series(p)"
public :: random_logseries_vec !@pyapi kind=subroutine args=x:integer(:):intent(out),p:real(dp):intent(in) lib=random desc="fill x with logarithmic-series samples"
public :: random_dirichlet !@pyapi kind=subroutine args=alpha:real(dp)(:):intent(in),x:real(dp)(:):intent(out) lib=random desc="sample one Dirichlet(alpha) vector"
public :: random_dirichlet_samples !@pyapi kind=subroutine args=alpha:real(dp)(:):intent(in),x:real(dp)(:,:):intent(out) lib=random desc="fill rows of x with Dirichlet(alpha) samples"
public :: random_multinomial !@pyapi kind=subroutine args=n:integer:intent(in),p:real(dp)(:):intent(in),x:integer(:):intent(out) lib=random desc="sample one Multinomial(n,p) count vector"
public :: random_multinomial_samples !@pyapi kind=subroutine args=n:integer:intent(in),p:real(dp)(:):intent(in),x:integer(:,:):intent(out) lib=random desc="fill rows of x with Multinomial(n,p) samples"
public :: random_multivariate_hypergeometric !@pyapi kind=subroutine args=ngood:integer(:):intent(in),nsample:integer:intent(in),x:integer(:):intent(out) lib=random desc="sample one multivariate hypergeometric count vector"
public :: random_multivariate_hypergeometric_samples !@pyapi kind=subroutine args=ngood:integer(:):intent(in),nsample:integer:intent(in),x:integer(:,:):intent(out) lib=random desc="fill rows of x with multivariate hypergeometric samples"
public :: random_beta !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in),b:real(dp):intent(in) lib=random desc="sample scalar beta(a,b), a,b>0"
public :: random_beta_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),a:real(dp):intent(in),b:real(dp):intent(in) lib=random desc="fill x with beta samples"
public :: random_lognormal !@pyapi kind=function ret=real(dp) args=meanlog:real(dp):intent(in):optional,sdlog:real(dp):intent(in):optional lib=random desc="sample scalar lognormal exp(N(meanlog,sdlog^2))"
public :: random_lognormal_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),meanlog:real(dp):intent(in):optional,sdlog:real(dp):intent(in):optional lib=random desc="fill x with lognormal samples"
public :: random_chisquare !@pyapi kind=function ret=real(dp) args=df:real(dp):intent(in) lib=random desc="sample scalar chi-square(df)"
public :: random_chisquare_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),df:real(dp):intent(in) lib=random desc="fill x with chi-square samples"
public :: random_laplace !@pyapi kind=function ret=real(dp) args=loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="sample scalar Laplace(loc,scale)"
public :: random_laplace_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="fill x with Laplace samples"
public :: random_logistic !@pyapi kind=function ret=real(dp) args=loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="sample scalar Logistic(loc,scale)"
public :: random_logistic_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="fill x with Logistic samples"
public :: random_cauchy !@pyapi kind=function ret=real(dp) args=loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="sample scalar Cauchy(loc,scale)"
public :: random_cauchy_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(out),loc:real(dp):intent(in):optional,scale:real(dp):intent(in):optional lib=random desc="fill x with Cauchy samples"
public :: random_mvn_samples !@pyapi kind=subroutine args=mean:real(dp)(:):intent(in),cov:real(dp)(:,:):intent(in),x:real(dp)(:,:):intent(out) lib=random desc="fill x(nsamp,ndim) with multivariate-normal samples using Cholesky factorization"
public :: random_choice2 !@pyapi kind=subroutine args=p:real(dp)(:):intent(in),n:integer:intent(in),z:integer(:):intent(out) lib=random desc="sample n labels in {0,1} with probabilities p(1:2)"
public :: random_choice_norep !@pyapi kind=subroutine args=npop:integer:intent(in),nsamp:integer:intent(in),z:integer(:):intent(out) lib=random desc="sample nsamp unique labels from 0..npop-1 without replacement"
public :: random_choice_prob !@pyapi kind=subroutine args=p:real(dp)(:):intent(in),n:integer:intent(in),z:integer(:):intent(out) lib=random desc="sample n labels in 0..size(p)-1 with probabilities p"
public :: random_choice_char !@pyapi kind=function ret=character args=a:character(:):intent(in) desc="choose one string from a character vector"
public :: random_choices_char !@pyapi kind=function ret=character(:) args=a:character(:):intent(in),k:integer:intent(in) desc="choose k strings with replacement"
public :: random_sample_char !@pyapi kind=function ret=character(:) args=a:character(:):intent(in),k:integer:intent(in) desc="choose k unique strings without replacement"
public :: sort_real_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(inout) lib=sorting desc="sort real vector x in ascending order"
public :: sort_int_vec !@pyapi kind=subroutine args=x:integer(:):intent(inout) lib=sorting desc="sort integer vector x in ascending order"
public :: sort_char_vec !@pyapi kind=subroutine args=x:character(:)(:):intent(inout) desc="sort character vector x in ascending order"
public :: argsort_real !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),idx:integer(:):intent(out) lib=sorting desc="argsort indices (0-based) of real vector"
public :: argsort_int !@pyapi kind=subroutine args=x:integer(:):intent(in),idx:integer(:):intent(out) lib=sorting desc="argsort indices (0-based) of integer vector"
public :: argsort_idx_real !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in) lib=sorting desc="argsort indices (0-based) of real vector"
public :: argsort_idx_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=sorting desc="argsort indices (0-based) of integer vector"
public :: sorted_real_vec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=sorting desc="np.sort of a real vector: a sorted copy"
public :: sorted_int_vec !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=sorting desc="np.sort of an integer vector: a sorted copy"
public :: sorted_real_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.sort of a real matrix along dimension dim (1 = down columns)"
public :: sorted_int_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.sort of an integer matrix along dimension dim (1 = down columns)"
public :: argsort_real_2d !@pyapi kind=function ret=integer(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.argsort (0-based) of a real matrix along dimension dim"
public :: argsort_int_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.argsort (0-based) of an integer matrix along dimension dim"
public :: arange_int !@pyapi kind=function ret=integer(:) args=start:integer:intent(in),stop:integer:intent(in),step:integer:intent(in) lib=arrays desc="integer arange(start, stop, step)"
public :: np_insert_real_1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),idx:integer:intent(in),val:real(dp):intent(in) lib=arrays desc="numpy insert for rank-1 real array and scalar value"
public :: np_delete_real_1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),idx:integer:intent(in) lib=arrays desc="numpy delete for rank-1 real array and scalar index"
public :: linspace !@pyapi kind=function ret=real(dp)(:) args=start:real(dp):intent(in),stop:real(dp):intent(in),num:integer:intent(in) lib=arrays desc="linspace(start, stop, num)"
public :: logspace !@pyapi kind=function ret=real(dp)(:) args=start:real(dp):intent(in),stop:real(dp):intent(in),num:integer:intent(in):optional,endpoint:logical:intent(in):optional,base:real(dp):intent(in):optional lib=arrays desc="logspace(start, stop, num=50, endpoint=True, base=10)"
public :: geomspace !@pyapi kind=function ret=real(dp)(:) args=start:real(dp):intent(in),stop:real(dp):intent(in),num:integer:intent(in):optional,endpoint:logical:intent(in):optional lib=arrays desc="geomspace(start, stop, num=50, endpoint=True)"
public :: mean_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) desc="mean of 1D real vector"
public :: weighted_mean_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),w:real(dp)(:):intent(in) lib=statistics desc="weighted mean of 1D real vector"
public :: var_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional desc="variance of 1D real vector with optional ddof (numpy-style)"
public :: skew_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style bias-corrected (adjusted Fisher-Pearson) sample skewness of 1D real vector"
public :: kurt_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style bias-corrected (adjusted Fisher-Pearson) excess sample kurtosis of 1D real vector"
public :: statistics_quantiles_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),n:integer:intent(in) lib=statistics desc="statistics.quantiles default exclusive method for 1D real vector"
public :: median_1d_real !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="median of 1D real vector"
public :: median_low_int !@pyapi kind=function ret=integer args=x:integer(:):intent(in) lib=statistics desc="median_low of 1D integer vector"
public :: median_high_int !@pyapi kind=function ret=integer args=x:integer(:):intent(in) lib=statistics desc="median_high of 1D integer vector"
public :: mode_int !@pyapi kind=function ret=integer args=x:integer(:):intent(in) lib=statistics desc="mode of 1D integer vector"
public :: mode_real !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="mode of 1D real vector"
public :: multimode_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=statistics desc="multimode of 1D integer vector"
public :: zeros_real !@pyapi kind=function ret=real(dp)(:) args=n:integer:intent(in) desc="allocate and return length-n real array initialized to 0"
public :: ones_real !@pyapi kind=function ret=real(dp)(:) args=n:integer:intent(in) desc="allocate and return length-n real array initialized to 1"
public :: zeros_complex !@pyapi kind=function ret=complex(dp)(:) args=n:integer:intent(in) desc="allocate and return length-n complex array initialized to 0"
public :: ones_complex !@pyapi kind=function ret=complex(dp)(:) args=n:integer:intent(in) desc="allocate and return length-n complex array initialized to 1"
public :: complex_isfinite !@pyapi kind=function ret=logical args=z:complex(dp):intent(in) lib=arrays desc="elemental finiteness test for complex values"
public :: complex_isinf !@pyapi kind=function ret=logical args=z:complex(dp):intent(in) lib=arrays desc="elemental infinity test for complex values"
public :: complex_isnan !@pyapi kind=function ret=logical args=z:complex(dp):intent(in) lib=arrays desc="elemental NaN test for complex values"
public :: zeros_int !@pyapi kind=function ret=integer(:) args=n:integer:intent(in) desc="allocate and return length-n integer array initialized to 0"
public :: ones_int !@pyapi kind=function ret=integer(:) args=n:integer:intent(in) desc="allocate and return length-n integer array initialized to 1"
public :: zeros_logical !@pyapi kind=function ret=logical(:) args=n:integer:intent(in) desc="allocate and return length-n logical array initialized to .false."
public :: ones_logical !@pyapi kind=function ret=logical(:) args=n:integer:intent(in) desc="allocate and return length-n logical array initialized to .true."
public :: strvec_t !@pyapi kind=type desc="string vector helper type"
public :: py_str !@pyapi kind=function ret=character args=x:any:intent(in) desc="python-like str() conversion for scalar int/real/logical/char"
public :: py_str_int
public :: str_concat
public :: str_format_real_fixed !@pyapi kind=function ret=character args=x:real(dp):intent(in),prec:integer:intent(in) desc="format real with fixed decimal places"
public :: str_format_real_sci !@pyapi kind=function ret=character args=x:real(dp):intent(in),prec:integer:intent(in) desc="format real in scientific notation matching Python's {:.Ne} f-string spec"
public :: py_float !@pyapi kind=function ret=real(dp) args=s:character:intent(in) desc="parse string to real(dp), NaN on read failure"
public :: py_int !@pyapi kind=function ret=integer args=s:character:intent(in) desc="parse string to integer, 0 on read failure"
public :: digits_of_str !@pyapi kind=function ret=integer(:) args=s:character:intent(in) desc="return decimal digits in a string as an integer vector"
public :: special_factorial !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="scipy.special.factorial approximation via gamma(x+1)"
public :: special_factorial2 !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="scipy.special.factorial2 for integer-like x"
public :: special_binom !@pyapi kind=function ret=real(dp) args=n:real(dp):intent(in),k:real(dp):intent(in) lib=special desc="binomial coefficient via gamma"
public :: special_comb !@pyapi kind=function ret=real(dp) args=n:real(dp):intent(in),k:real(dp):intent(in),exact:logical:intent(in):optional,repetition:logical:intent(in):optional lib=special desc="scipy.special.comb(n,k,exact=False,repetition=False)"
public :: to_lower !@pyapi kind=function ret=character args=s:character:intent(in) desc="lowercase string"
public :: to_upper !@pyapi kind=function ret=character args=s:character:intent(in) desc="uppercase string"
public :: str_strip !@pyapi kind=function ret=character args=s:character:intent(in),chars:character:intent(in):optional desc="strip leading/trailing characters"
public :: str_lstrip !@pyapi kind=function ret=character args=s:character:intent(in),chars:character:intent(in):optional desc="strip leading characters"
public :: str_rstrip !@pyapi kind=function ret=character args=s:character:intent(in),chars:character:intent(in):optional desc="strip trailing characters"
public :: starts_with !@pyapi kind=function ret=logical args=s:character:intent(in),prefix:character:intent(in) desc="prefix test"
public :: ends_with !@pyapi kind=function ret=logical args=s:character:intent(in),suffix:character:intent(in) desc="suffix test"
public :: str_find !@pyapi kind=function ret=integer args=s:character:intent(in),sub:character:intent(in) desc="0-based find index or -1"
public :: str_rfind !@pyapi kind=function ret=integer args=s:character:intent(in),sub:character:intent(in) desc="0-based reverse find index or -1"
public :: str_replace !@pyapi kind=function ret=character args=s:character:intent(in),old:character:intent(in),new:character:intent(in) desc="replace all occurrences"
public :: str_reverse !@pyapi kind=function ret=character args=s:character:intent(in) desc="reverse a string (Python's s[::-1])"
public :: str_to_chars !@pyapi kind=function ret=character args=s:character:intent(in) desc="split a string into a rank-1 array of its own 1-character substrings"
public :: str_zfill !@pyapi kind=function ret=character args=s:character:intent(in),width:integer:intent(in) desc="left-pad string with zeros to given width"
public :: str_head !@pyapi kind=function ret=character args=s:character:intent(in),n:integer:intent(in) desc="first n characters of s (Python s[:n] for n >= 0)"
public :: py_repr_str !@pyapi kind=function ret=character args=s:character:intent(in) desc="Python repr() of a string: quoted, with backslashes and quotes escaped"
public :: str_ljust !@pyapi kind=function ret=character args=s:character:intent(in),width:integer:intent(in) desc="right-pad string with spaces to given width"
public :: str_rjust !@pyapi kind=function ret=character args=s:character:intent(in),width:integer:intent(in) desc="left-pad string with spaces to given width"
public :: str_split !@pyapi kind=function ret=type(strvec_t) args=s:character:intent(in),sep:character:intent(in):optional desc="split into string vector"
public :: str_join !@pyapi kind=function ret=character args=sep:character:intent(in),items:type(strvec_t):intent(in) desc="join string vector with separator"
public :: str_count !@pyapi kind=function ret=integer args=s:character:intent(in),sub:character:intent(in) desc="count non-overlapping occurrences"
public :: csv_split_line !@pyapi kind=function ret=character(:) args=line:character:intent(in),delimiter:character:intent(in):optional,quotechar:character:intent(in):optional desc="split one CSV line into fields (basic quote-aware parser)"
public :: file_read !@pyapi kind=function ret=character args=u:integer:intent(in) desc="read remaining text from open unit as a single string"
public :: str_isdigit !@pyapi kind=function ret=logical args=s:character:intent(in) desc="true when all chars are digits"
public :: str_isalpha !@pyapi kind=function ret=logical args=s:character:intent(in) desc="true when all chars are letters"
public :: str_isalnum !@pyapi kind=function ret=logical args=s:character:intent(in) desc="true when all chars are alnum"
public :: str_isspace !@pyapi kind=function ret=logical args=s:character:intent(in) desc="true when all chars are whitespace"
public :: sys_argv_init !@pyapi kind=function ret=character(:) args= desc="capture process command arguments (including argv[0])"
public :: sys_argv_delete !@pyapi kind=subroutine args=argv:character(:):intent(inout),idx1:integer:intent(in) desc="delete argv element at 1-based index"
public :: index1
public :: index2
public :: slice1
public :: py_slice_bound
public :: py_rshift

public :: rank_min_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style Series.rank(method='min') for a plain 1D real vector"
public :: rank_max_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style Series.rank(method='max') for a plain 1D real vector"
public :: rank_average_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style Series.rank(method='average') for a plain 1D real vector"
public :: rank_first_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style Series.rank(method='first') for a plain 1D real vector"
public :: rank_dense_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=statistics desc="pandas-style Series.rank(method='dense') for a plain 1D real vector"
public :: cumsum_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=arrays desc="cumulative sum of real vector"
public :: cumsum_real_axis0_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="cumulative sum of real matrix along axis 0"
public :: cumsum_real_axis1_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="cumulative sum of real matrix along axis 1"
public :: unique_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=sorting desc="sorted unique values of integer vector"
public :: unique_char !@pyapi kind=function ret=character(:) args=x:character(:):intent(in) desc="unique values of character vector (first-occurrence order)"
public :: tile_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),reps:integer:intent(in) lib=arrays desc="tile integer vector reps times"
public :: tile_int_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in),reps0:integer:intent(in),reps1:integer:intent(in) lib=arrays desc="tile integer matrix reps0 x reps1 times"
public :: diag_from_vec_int !@pyapi kind=function ret=integer(:,:) args=v:integer(:):intent(in) lib=arrays desc="return diagonal matrix from integer vector"
public :: diagonal !@pyapi kind=function ret=any args=a:any:intent(in),offset:integer:intent(in):optional lib=arrays desc="numpy-like diagonal for 2D matrices and 3D axis1=1,axis2=2 arrays"
public :: cumprod_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=arrays desc="cumulative product of integer vector"
public :: repeat_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat each integer element reps times"
public :: repeat_int_axis0_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat rows of integer matrix reps times"
public :: repeat_int_axis1_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat columns of integer matrix reps times"
public :: diag_from_mat_real !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:):intent(in) lib=arrays desc="return main diagonal of real matrix"
public :: cumsum_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=arrays desc="cumulative sum of integer vector"
public :: cumsum_int_axis0_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in) lib=arrays desc="cumulative sum of integer matrix along axis 0"
public :: cumsum_int_axis1_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in) lib=arrays desc="cumulative sum of integer matrix along axis 1"
public :: cumprod_real_axis0_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="cumulative product of real matrix along axis 0"
public :: cumprod_real_axis1_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="cumulative product of real matrix along axis 1"
public :: cumprod_int_axis0_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in) lib=arrays desc="cumulative product of integer matrix along axis 0"
public :: cumprod_int_axis1_2d !@pyapi kind=function ret=integer(:,:) args=x:integer(:,:):intent(in) lib=arrays desc="cumulative product of integer matrix along axis 1"
public :: itertools_product2_int !@pyapi kind=function ret=integer(:,:) args=a:integer(:):intent(in),b:integer(:):intent(in) desc="itertools.product(a,b) for integer vectors"
public :: itertools_combinations_int !@pyapi kind=function ret=integer(:,:) args=x:integer(:):intent(in),r:integer:intent(in) desc="itertools.combinations(x,r) for integer vectors (r=2 currently)"
public :: itertools_combinations_wr_int !@pyapi kind=function ret=integer(:,:) args=x:integer(:):intent(in),r:integer:intent(in) desc="itertools.combinations_with_replacement(x,r) for integer vectors (r=2 currently)"
public :: itertools_permutations_int !@pyapi kind=function ret=integer(:,:) args=x:integer(:):intent(in),r:integer:intent(in) desc="itertools.permutations(x,r) for integer vectors (r=2 currently)"
public :: diag_from_vec_real !@pyapi kind=function ret=real(dp)(:,:) args=v:real(dp)(:):intent(in) lib=arrays desc="return diagonal matrix from real vector"
public :: repeat_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat each real element reps times"
public :: repeat_real_axis0_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat rows of real matrix reps times"
public :: repeat_real_axis1_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat columns of real matrix reps times"
public :: repeat_logical !@pyapi kind=function ret=logical(:) args=x:logical(:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat each logical element reps times"
public :: repeat_logical_axis0_2d !@pyapi kind=function ret=logical(:,:) args=x:logical(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat rows of logical matrix reps times"
public :: repeat_logical_axis1_2d !@pyapi kind=function ret=logical(:,:) args=x:logical(:,:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat columns of logical matrix reps times"
public :: diag_from_mat_int !@pyapi kind=function ret=integer(:) args=a:integer(:,:):intent(in) lib=arrays desc="return main diagonal of integer matrix"
public :: tile_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="tile real vector reps times"
public :: tile_real_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),reps0:integer:intent(in),reps1:integer:intent(in) lib=arrays desc="tile real matrix reps0 x reps1 times"
public :: eye_real !@pyapi kind=function ret=real(dp)(:,:) args=n:integer:intent(in),m:integer:intent(in):optional,k:integer:intent(in):optional lib=arrays desc="return n x m matrix with ones on diagonal k (default m=n, k=0)"
public :: unique_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=sorting desc="sorted unique values of real vector"
public :: bincount_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),minlength:integer:intent(in):optional lib=statistics desc="count occurrences of nonnegative integers"
public :: searchsorted_left_int !@pyapi kind=function ret=integer(:) args=a:integer(:):intent(in),v:integer(:):intent(in) lib=sorting desc="searchsorted left indices for integer vectors"
public :: searchsorted_right_int !@pyapi kind=function ret=integer(:) args=a:integer(:):intent(in),v:integer(:):intent(in) lib=sorting desc="searchsorted right indices for integer vectors"
public :: searchsorted_left_int_scalar !@pyapi kind=function ret=integer args=a:integer(:):intent(in),v:integer:intent(in) lib=sorting desc="searchsorted left index for scalar integer query"
public :: searchsorted_right_int_scalar !@pyapi kind=function ret=integer args=a:integer(:):intent(in),v:integer:intent(in) lib=sorting desc="searchsorted right index for scalar integer query"
public :: setdiff1d_int !@pyapi kind=function ret=integer(:) args=a:integer(:):intent(in),b:integer(:):intent(in) lib=sorting desc="sorted unique values in a not in b"
public :: intersect1d_int !@pyapi kind=function ret=integer(:) args=a:integer(:):intent(in),b:integer(:):intent(in) lib=sorting desc="sorted unique intersection of a and b"
public :: setdiff1d_char !@pyapi kind=function ret=character(:) args=a:character(:):intent(in),b:character(:):intent(in) desc="unique values in a not in b (character)"
public :: intersect1d_char !@pyapi kind=function ret=character(:) args=a:character(:):intent(in),b:character(:):intent(in) desc="unique intersection of a and b (character)"
public :: unique_int_inv_counts !@pyapi kind=subroutine args=a:integer(:):intent(in),u:integer(:):intent(out),inv:integer(:):intent(out),cnt:integer(:):intent(out) lib=sorting desc="unique values with inverse and counts"
public :: unique_int_counts !@pyapi kind=subroutine args=a:integer(:):intent(in),u:integer(:):intent(out),cnt:integer(:):intent(out) lib=sorting desc="unique values with counts"
public :: lexsort2_int !@pyapi kind=function ret=integer(:) args=key0:integer(:):intent(in),key1:integer(:):intent(in) lib=sorting desc="lexsort((key0,key1)): sort by key1 then key0, return 0-based indices"
public :: lexsort2_real !@pyapi kind=function ret=integer(:) args=key0:real(dp)(:):intent(in),key1:real(dp)(:):intent(in) lib=sorting desc="lexsort((key0,key1)) for real keys: sort by key1 then key0, return 0-based indices"
public :: ravel_multi_index_2d !@pyapi kind=function ret=integer args=rc:integer(:):intent(in),shape:integer(:):intent(in),forder:logical:intent(in):optional lib=arrays desc="np.ravel_multi_index(tuple(rc), shape): the flat index (C order, or Fortran order with forder) of a 0-based multi-index"
public :: ravel_multi_index_vec !@pyapi kind=function ret=integer(:) args=rc:integer(:,:):intent(in),shape:integer(:):intent(in),forder:logical:intent(in):optional lib=arrays desc="np.ravel_multi_index of index arrays, rc(k, :) the k-th coordinates"
public :: unravel_index_2d !@pyapi kind=function ret=integer(:) args=i:integer:intent(in),shape:integer(:):intent(in),forder:logical:intent(in):optional lib=arrays desc="np.unravel_index(i, shape): the 0-based multi-index of a flat index (C order, or Fortran order with forder)"
public :: unravel_index_part !@pyapi kind=function ret=integer(:) args=i:integer(:):intent(in),shape:integer(:):intent(in),k:integer:intent(in),forder:logical:intent(in):optional lib=arrays desc="np.unravel_index(i, shape)[k-1]: the k-th coordinate array of a vector of flat indices"
public :: unravel_index_vec !@pyapi kind=function ret=integer(:,:) args=i:integer(:):intent(in),shape:integer(:):intent(in),forder:logical:intent(in):optional lib=arrays desc="np.unravel_index of a vector of flat indices: row k the k-th coordinate array"
public :: kron_2d !@pyapi kind=function ret=integer(:,:) args=a:integer(:,:):intent(in),b:integer(:,:):intent(in) lib=linalg desc="2D Kronecker product for integer matrices"
public :: histogram_real_edges !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),bins:real(dp)(:):intent(in),h:integer(:):intent(out),edges:real(dp)(:):intent(out) lib=statistics desc="1D histogram with explicit real bin edges"
public :: histogram_int_edges !@pyapi kind=subroutine args=x:integer(:):intent(in),bins:integer(:):intent(in),h:integer(:):intent(out),edges:integer(:):intent(out) lib=statistics desc="1D histogram with explicit integer bin edges"
public :: histogram2d_real_edges !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),xbins:real(dp)(:):intent(in),ybins:real(dp)(:):intent(in),h:integer(:,:):intent(out) lib=statistics desc="2D histogram with explicit real bin edges on both axes"
public :: reduceat_add_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.add.reduceat for real vector"
public :: reduceat_add_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.add.reduceat for integer vector"
public :: reduceat_mul_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.multiply.reduceat for real vector"
public :: reduceat_mul_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.multiply.reduceat for integer vector"
public :: reduceat_min_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.minimum.reduceat for real vector"
public :: reduceat_min_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.minimum.reduceat for integer vector"
public :: reduceat_max_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.maximum.reduceat for real vector"
public :: reduceat_max_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.maximum.reduceat for integer vector"
public :: reduceat_logical_and !@pyapi kind=function ret=logical(:) args=x:logical(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.logical_and.reduceat for logical vector"
public :: reduceat_logical_or !@pyapi kind=function ret=logical(:) args=x:logical(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.logical_or.reduceat for logical vector"
public :: cumprod_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=arrays desc="cumulative product of real vector"
public :: gradient_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=calculus desc="1D gradient with unit spacing (numpy-style edge handling)"
public :: np_gradient_1d !@pyapi kind=function ret=real(dp)(:) args=f:real(dp)(:):intent(in),edge_order:integer:intent(in),dx:real(dp):intent(in):optional,x:real(dp)(:):intent(in):optional lib=calculus desc="np.gradient(f, [dx | x], edge_order=...) of a vector, with numpy's formulas: second-order interior differences (for uneven coordinates x too), first- or second-order one-sided ..."
public :: np_gradient_2d !@pyapi kind=function ret=real(dp)(:,:) args=f:real(dp)(:,:):intent(in),dim:integer:intent(in),edge_order:integer:intent(in),dx:real(dp):intent(in):optional,x:real(dp)(:):intent(in):optional lib=calculus desc="np.gradient(f, ..., axis=dim-1) of a matrix: each column (dim 1) or row (dim 2) differentiated by np_gradient_1d"
public :: np_trapezoid_1d !@pyapi kind=function ret=real(dp) args=y:real(dp)(:):intent(in),dx:real(dp):intent(in):optional,x:real(dp)(:):intent(in):optional lib=calculus desc="np.trapezoid(y, x=x | dx=dx) of a vector, summed as numpy does: sum(d * (y[1:] + y[:-1]) / 2)"
public :: interp_0d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),xp:real(dp)(:):intent(in),fp:real(dp)(:):intent(in),left:real(dp):intent(in):optional,right:real(dp):intent(in):optional lib=calculus desc="np.interp of a scalar x"
public :: interp_periodic_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),xp:real(dp)(:):intent(in),fp:real(dp)(:):intent(in),period:real(dp):intent(in) lib=calculus desc="np.interp(x, xp, fp, period=p): x and xp are reduced modulo |p|, xp sorted (fp with it) and extended by one point at each end across the period boundary, as numpy does"
public :: interp_periodic_0d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),xp:real(dp)(:):intent(in),fp:real(dp)(:):intent(in),period:real(dp):intent(in) lib=calculus desc="np.interp(x, xp, fp, period=p) at a scalar x"
public :: np_hist_edges !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),n:integer:intent(in),lo_in:real(dp):intent(in):optional,hi_in:real(dp):intent(in):optional lib=statistics desc="n equal bins over [min(x), max(x)] (or [lo_in, hi_in]), widened by 0.5 each side when the ends are equal, with np.linspace's arithmetic (start + i * step, the last edge exactly ..."
public :: histogram2d_np !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),xbins:real(dp)(:):intent(in),ybins:real(dp)(:):intent(in),h:real(dp)(:,:):intent(out),weights:real(dp)(:):intent(in):optional,density:logical:intent(in):optional lib=statistics desc="numpy.histogram2d(x, y, bins=[xbins, ybins], weights=, density=): float counts (or sums of weights); per axis the last bin includes its right edge; density divides by the bin ..."
public :: histogram_np !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),bins:real(dp)(:):intent(in),h:real(dp)(:):intent(out),edges:real(dp)(:):intent(out),weights:real(dp)(:):intent(in):optional,density:logical:intent(in):optional desc="np.histogram with bin edges, weights= and density=: float counts"
public :: np_hist_bin_count !@pyapi kind=function ret=integer args=x:real(dp)(:):intent(in),method:character(*):intent(in),integer_data:logical:intent(in),lo_in:real(dp):intent(in):optional,hi_in:real(dp):intent(in):optional lib=statistics desc="number of histogram bins chosen by numpy's estimators auto, fd, doane, scott, rice, sturges, sqrt"
public :: np_spacing !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="np.spacing(x): the distance from x to the next float away from 0, with the sign of x (spacing(0) is the smallest subnormal; NaN for inf and NaN)"
public :: np_chkfinite !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="np.asarray_chkfinite(x): x, or an error if it is inf or NaN"
public :: np_nan_to_num !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),nan:real(dp):intent(in),posinf:real(dp):intent(in),neginf:real(dp):intent(in) lib=arrays desc="np.nan_to_num: NaN and infinities replaced (elemental)"
public :: np_heaviside !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),h0:real(dp):intent(in) lib=arrays desc="np.heaviside step function, NaN at NaN (elemental)"
public :: np_corrcoef_1 !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="np.corrcoef of one vector: 1, or NaN for a constant or non-finite vector (var / sqrt(var * var))"
public :: np_packbits !@pyapi kind=function ret=integer(:) args=bits:logical(:):intent(in),little:logical:intent(in) lib=arrays desc="np.packbits: pack a logical vector into bytes (values 0..255), big- or little-endian bit order"
public :: np_unpackbits !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),little:logical:intent(in),count:integer:intent(in):optional lib=arrays desc="np.unpackbits: the bits (0/1) of bytes 0..255, with numpy's count="
public :: np_pad_indices !@pyapi kind=function ret=integer(:) args=n:integer:intent(in),before:integer:intent(in),after:integer:intent(in),mode:integer:intent(in) lib=arrays desc="np.pad: 1-based source indices of a vector of size n padded by before/after elements (mode 1 edge, 2 wrap, 3 reflect, 4 symmetric)"
public :: np_pad_vec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),before:integer:intent(in),after:integer:intent(in),mode:integer:intent(in) lib=arrays desc="np.pad of a real, integer, complex or logical vector with mode 1 edge, 2 wrap, 3 reflect, 4 symmetric"
public :: np_pad_index !@pyapi kind=function ret=integer args=i:integer:intent(in),n:integer:intent(in),mode:integer:intent(in) lib=arrays desc="np.pad index map: 0-based source index of padded position i for mode 1 edge, 2 wrap, 3 reflect, 4 symmetric"
public :: np_window !@pyapi kind=function ret=real(dp)(:) args=kind_name:character(*):intent(in),m:integer:intent(in),beta:real(dp):intent(in):optional lib=signal desc="np.hanning / hamming / blackman / bartlett / kaiser(m[, beta]) with numpy's formulas (n = arange(1-m, m, 2) for the cosine windows); m == 1 gives [1.0] and m < 1 an empty ..."
public :: np_poly_roots !@pyapi kind=function ret=real(dp)(:) args=r:real(dp)(:):intent(in) lib=polynomial desc="np.poly(roots): the monic polynomial with these roots, highest degree first"
public :: np_polyadd !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in),sgn:integer:intent(in) lib=polynomial desc="np.polyadd(a, b) (sgn = 1) / np.polysub(a, b) (sgn = -1): the shorter is padded with leading zeros (generic: np_polyadd_real, np_polyadd_int)"
public :: np_polymul !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=polynomial desc="np.polymul(a, b): the full convolution of the coefficients (generic: np_polymul_real, np_polymul_int)"
public :: np_polydiv_complex !@pyapi kind=function ret=complex(dp)(:) args=u:complex(dp)(:):intent(in),v:complex(dp)(:):intent(in),part:integer:intent(in) lib=polynomial desc="np.polydiv(u, v)[part] of complex polynomials: the quotient (part 0) or the remainder (part 1), as np_polydiv"
public :: np_polydiv !@pyapi kind=function ret=real(dp)(:) args=u:real(dp)(:):intent(in),v:real(dp)(:):intent(in),part:integer:intent(in) lib=polynomial desc="np.polydiv(u, v)[part]: the quotient (part 0) or the remainder (part 1), with numpy's algorithm (leading remainder terms close to zero, allclose with rtol 1e-14, are dropped)"
public :: np_polyint !@pyapi kind=function ret=real(dp)(:) args=p:real(dp)(:):intent(in),m:integer:intent(in),k:real(dp)(:):intent(in):optional lib=polynomial desc="np.polyint(p, m, k): m antiderivatives, integration constants k (a scalar for all, or one per integration; default 0)"
public :: nan_quantile_vec
public :: nan_quantile_qvec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),q:real(dp)(:):intent(in) lib=statistics desc="np.nanquantile(x, q) of a vector at several probabilities q"
public :: nan_quantile_axis_2d_q !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),q:real(dp)(:):intent(in),dim:integer:intent(in) lib=statistics desc="np.nanquantile(x, q, axis=dim-1) of a matrix at several probabilities: row k for q(k)"
public :: nan_quantile_axis_2d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:,:):intent(in),q:real(dp):intent(in),dim:integer:intent(in) lib=statistics desc="np.nanquantile(x, q, axis=dim-1) of a matrix"
public :: powval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polyval: value of the power series (np.polynomial.polynomial, lowest degree first) at x (scalar, vector or matrix x)"
public :: powvander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.polynomial.polyvander: pseudo-Vandermonde matrix"
public :: powval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polyval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: powval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polyval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: powgrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polygrid2d: 2-D series on the grid x by y"
public :: powgrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polygrid3d: 3-D series on the grid x by y by z"
public :: chebval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: chebval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: chebgrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebgrid2d: 2-D series on the grid x by y"
public :: chebgrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebgrid3d: 3-D series on the grid x by y by z"
public :: legval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.legendre.legval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: legval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.legendre.legval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: leggrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.legendre.leggrid2d: 2-D series on the grid x by y"
public :: leggrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.legendre.leggrid3d: 3-D series on the grid x by y by z"
public :: hermval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.hermite.hermval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: hermval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.hermite.hermval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: hermgrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.hermite.hermgrid2d: 2-D series on the grid x by y"
public :: hermgrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.hermite.hermgrid3d: 3-D series on the grid x by y by z"
public :: hermeval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermeval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: hermeval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermeval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: hermegrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermegrid2d: 2-D series on the grid x by y"
public :: hermegrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermegrid3d: 3-D series on the grid x by y by z"
public :: lagval2d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.laguerre.lagval2d: 2-D series value at points (x, y) (scalars, vectors or matrices)"
public :: lagval3d !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in),z:real(dp):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.laguerre.lagval3d: 3-D series value at points (x, y, z) (scalars or vectors)"
public :: laggrid2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),c:real(dp)(:,:):intent(in) lib=polynomial desc="np.polynomial.laguerre.laggrid2d: 2-D series on the grid x by y"
public :: laggrid3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),z:real(dp)(:):intent(in),c:real(dp)(:,:,:):intent(in) lib=polynomial desc="np.polynomial.laguerre.laggrid3d: 3-D series on the grid x by y by z"
public :: powvalfromroots !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),r:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.polynomial.polyvalfromroots: prod(x - r) at scalar, vector or matrix x"
public :: opoly_val2d0, opoly_val3d0, opoly_grid2d, opoly_grid3d
public :: powder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.polynomial.polyder: derivative coefficients"
public :: powint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.polynomial.polyint: integral coefficients"
public :: powfit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.polynomial.polyfit: least-squares fit, coefficients lowest degree first"
public :: chebval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebval: value of the Chebyshev series (np.polynomial.chebyshev) at x (scalar, vector or matrix x)"
public :: chebvander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.chebyshev.chebvander: pseudo-Vandermonde matrix"
public :: chebder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.chebyshev.chebder: derivative coefficients"
public :: chebint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.chebyshev.chebint: integral coefficients"
public :: chebfit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.chebyshev.chebfit: least-squares fit, coefficients lowest degree first"
public :: legval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.legendre.legval: value of the Legendre series (np.polynomial.legendre) at x (scalar, vector or matrix x)"
public :: legvander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.legendre.legvander: pseudo-Vandermonde matrix"
public :: legder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.legendre.legder: derivative coefficients"
public :: legint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.legendre.legint: integral coefficients"
public :: legfit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.legendre.legfit: least-squares fit, coefficients lowest degree first"
public :: hermval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.hermite.hermval: value of the physicists' Hermite series (np.polynomial.hermite) at x (scalar, vector or matrix x)"
public :: hermvander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.hermite.hermvander: pseudo-Vandermonde matrix"
public :: hermder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.hermite.hermder: derivative coefficients"
public :: hermint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.hermite.hermint: integral coefficients"
public :: hermfit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.hermite.hermfit: least-squares fit, coefficients lowest degree first"
public :: hermeval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermeval: value of the probabilists' Hermite series (np.polynomial.hermite_e) at x (scalar, vector or matrix x)"
public :: hermevander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.hermite_e.hermevander: pseudo-Vandermonde matrix"
public :: hermeder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.hermite_e.hermeder: derivative coefficients"
public :: hermeint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.hermite_e.hermeint: integral coefficients"
public :: hermefit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.hermite_e.hermefit: least-squares fit, coefficients lowest degree first"
public :: lagval !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),c:real(dp)(:):intent(in) lib=polynomial desc="np.polynomial.laguerre.lagval: value of the Laguerre series (np.polynomial.laguerre) at x (scalar, vector or matrix x)"
public :: lagvander !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="np.polynomial.laguerre.lagvander: pseudo-Vandermonde matrix"
public :: lagder !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.laguerre.lagder: derivative coefficients"
public :: lagint !@pyapi kind=function ret=real(dp)(:) args=c:real(dp)(:):intent(in),m:integer:intent(in):optional,k:real(dp)(:):intent(in):optional,lbnd:real(dp):intent(in):optional,scl:real(dp):intent(in):optional lib=polynomial desc="np.polynomial.laguerre.lagint: integral coefficients"
public :: lagfit !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in),rcond:real(dp):intent(in):optional,w:real(dp)(:):intent(in):optional lib=polynomial desc="np.polynomial.laguerre.lagfit: least-squares fit, coefficients lowest degree first"
public :: opoly_val0, opoly_vander, opoly_der, opoly_int, opoly_fit
public :: powcompanion, powroots, powrealroots, powfromroots, powmulx, powadd, powsub, powmul, powdiv, powpow, powline, powtrim !@pyapi lib=polynomial desc="np.polynomial.polynomial.poly...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim"
public :: chebcompanion, chebroots, chebrealroots, chebfromroots, chebmulx, chebadd, chebsub, chebmul, chebdiv, chebpow, chebline, chebtrim, cheb2poly, poly2cheb, chebgauss !@pyapi lib=polynomial desc="np.polynomial.chebyshev.cheb...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim, conversions to and from the power series, Gauss quadrature"
public :: legcompanion, legroots, legrealroots, legfromroots, legmulx, legadd, legsub, legmul, legdiv, legpow, legline, legtrim, leg2poly, poly2leg !@pyapi lib=polynomial desc="np.polynomial.legendre.leg...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim, conversions to and from the power series"
public :: hermcompanion, hermroots, hermrealroots, hermfromroots, hermmulx, hermadd, hermsub, hermmul, hermdiv, hermpow, hermline, hermtrim, herm2poly, poly2herm, hermgauss !@pyapi lib=polynomial desc="np.polynomial.hermite.herm...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim, conversions to and from the power series, Gauss quadrature"
public :: hermecompanion, hermeroots, hermerealroots, hermefromroots, hermemulx, hermeadd, hermesub, hermemul, hermediv, hermepow, hermeline, hermetrim, herme2poly, poly2herme, hermegauss !@pyapi lib=polynomial desc="np.polynomial.hermite_e.herme...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim, conversions to and from the power series, Gauss quadrature"
public :: lagcompanion, lagroots, lagrealroots, lagfromroots, lagmulx, lagadd, lagsub, lagmul, lagdiv, lagpow, lagline, lagtrim, lag2poly, poly2lag, laggauss !@pyapi lib=polynomial desc="np.polynomial.laguerre.lag...: companion, roots (complex; realroots: real, not in numpy), fromroots, mulx, add, sub, mul, div (subroutine: quo, rem), pow, line, trim, conversions to and from the power series, Gauss quadrature"
public :: chebpts1, chebpts2 !@pyapi lib=polynomial desc="np.polynomial.chebyshev.chebpts1/chebpts2: Chebyshev points of the first/second kind"
public :: opoly_trim, opoly_trimcoef, opoly_companion, opoly_roots, opoly_realroots, opoly_gauss, opoly_mulx, opoly_add, opoly_mul, opoly_div, opoly_div_part, opoly_pow, opoly_line, opoly_fromroots, opoly_to_pow, opoly_from_pow, opoly_gauss_part
public :: unwrap_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=signal desc="unwrap 1D phase vector using numpy-like default discontinuity pi"
public :: bitwise_count_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in) lib=integers desc="population count for each integer element"
public :: i0_scalar !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="modified Bessel function I0 approximation (elemental)"
public :: sinc_scalar !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="normalized sinc(x) = sin(pi*x)/(pi*x) with sinc(0)=1"
public :: signbit_real !@pyapi kind=function ret=logical args=x:real(dp):intent(in) lib=arrays desc="true when IEEE sign bit is set (including -0.0)"
public :: gcd_int_scalar !@pyapi kind=function ret=integer args=a:integer:intent(in),b:integer:intent(in) lib=integers desc="greatest common divisor"
public :: lcm_int_scalar !@pyapi kind=function ret=integer args=a:integer:intent(in),b:integer:intent(in) lib=integers desc="least common multiple"
public :: gcd_int !@pyapi kind=function ret=integer args=a:integer(:):intent(in) lib=integers desc="greatest common divisor of integer array"
public :: lcm_int !@pyapi kind=function ret=integer args=a:integer(:):intent(in) lib=integers desc="least common multiple of integer array"
public :: interp_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),xp:real(dp)(:):intent(in),fp:real(dp)(:):intent(in) lib=calculus desc="1D linear interpolation with endpoint clamping"
public :: linalg_solve !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:):intent(in),b:real(dp)(:):intent(in) lib=linalg desc="solve linear system A x = b using LAPACK DGESV"
public :: linalg_solve_safe !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),b:real(dp)(:):intent(in),x:real(dp)(:):intent(out),ok:logical:intent(out) lib=linalg desc="solve linear system A x = b using LAPACK DGESV and return success status"
public :: linalg_cholesky !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in) lib=linalg desc="lower-triangular Cholesky factor using LAPACK DPOTRF"
public :: linalg_det !@pyapi kind=function ret=real(dp) args=a:real(dp)(:,:):intent(in) lib=linalg desc="determinant of square matrix using LAPACK DGETRF"
public :: linalg_inv !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in) lib=linalg desc="matrix inverse using LAPACK DGETRF/DGETRI"
public :: linalg_cond !@pyapi kind=function ret=real(dp) args=a:real(dp)(:,:):intent(in) lib=linalg desc="2-norm condition number using SVD singular values"
public :: linalg_matrix_rank !@pyapi kind=function ret=integer args=a:real(dp)(:,:):intent(in) lib=linalg desc="numerical matrix rank using SVD singular values and NumPy-like tolerance"
public :: linalg_eigvals !@pyapi kind=function ret=complex(dp)(:) args=a:real(dp)(:,:):intent(in) lib=linalg desc="eigenvalues of real or complex square matrix"
public :: linalg_eig !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),w:complex(dp)(:):intent(out),v:complex(dp)(:,:):intent(out) lib=linalg desc="complex right eigenpairs of real square matrix using LAPACK DGEEV"
public :: linalg_eigh !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),w:real(dp)(:):intent(out),v:real(dp)(:,:):intent(out) lib=linalg desc="eigenpairs of real symmetric matrix using LAPACK DSYEV"
public :: linalg_eigvalsh !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:):intent(in) lib=linalg desc="eigenvalues only of real symmetric matrix using LAPACK DSYEV (jobz='N')"
public :: linalg_pinv !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in) lib=linalg desc="Moore-Penrose pseudo-inverse via economy SVD"
public :: linalg_matrix_power !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in),p:integer:intent(in) lib=linalg desc="integer matrix power (identity at p=0, repeated matmul of inv(a) for p<0)"
public :: linalg_qr_reduced !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),q:real(dp)(:,:):intent(out),r:real(dp)(:,:):intent(out) lib=linalg desc="reduced QR factorization using LAPACK DGEQRF/DORGQR"
public :: matrix_norm2 !@pyapi kind=function ret=real(dp) args=a:real(dp)(:,:):intent(in) lib=linalg desc="matrix spectral norm"
public :: linalg_svd !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),u:real(dp)(:,:):intent(out),s:real(dp)(:):intent(out),vt:real(dp)(:,:):intent(out) lib=linalg desc="full SVD using LAPACK DGESVD"
public :: linalg_svd_econ !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),u:real(dp)(:,:):intent(out),s:real(dp)(:):intent(out),vt:real(dp)(:,:):intent(out) lib=linalg desc="economy/reduced SVD (full_matrices=False) using LAPACK DGESVD"
public :: leggauss !@pyapi kind=subroutine args=n:integer:intent(in),x:real(dp)(:):intent(out),w:real(dp)(:):intent(out) lib=polynomial desc="Gauss-Legendre quadrature nodes x and weights w on [-1,1] for degree n, matching numpy.polynomial.legendre.leggauss"
public :: quantile_linear !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),q:real(dp):intent(in) lib=statistics desc="1D quantile with linear interpolation (NumPy-like default)"
public :: quantile_linear_vec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),q:real(dp)(:):intent(in) lib=statistics desc="1D quantiles at multiple probabilities with linear interpolation (NumPy-like default)"
public :: tri_int !@pyapi kind=function ret=integer(:,:) args=n:integer:intent(in),m:integer:intent(in),k:integer:intent(in):optional lib=arrays desc="lower-triangular ones matrix with diagonal offset k"
public :: tri_real !@pyapi kind=function ret=real(dp)(:,:) args=n:integer:intent(in),m:integer:intent(in),k:integer:intent(in):optional lib=arrays desc="lower-triangular ones matrix with diagonal offset k"
public :: moveaxis3_int !@pyapi kind=function ret=integer(:,:,:) args=a:integer(:,:,:):intent(in),src:integer:intent(in),dst:integer:intent(in) lib=arrays desc="move one axis for rank-3 integer arrays (NumPy-style indices)"
public :: moveaxis3_real !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),src:integer:intent(in),dst:integer:intent(in) lib=arrays desc="move one axis for rank-3 real arrays (NumPy-style indices)"
public :: moveaxis3_logical !@pyapi kind=function ret=logical(:,:,:) args=a:logical(:,:,:):intent(in),src:integer:intent(in),dst:integer:intent(in) lib=arrays desc="move one axis for rank-3 logical arrays (NumPy-style indices)"
public :: pad2d_int !@pyapi kind=function ret=integer(:,:) args=a:integer(:,:):intent(in),pt:integer:intent(in),pb:integer:intent(in),pl:integer:intent(in),pr:integer:intent(in),c:integer:intent(in) lib=arrays desc="2D constant pad for integer matrix"
public :: pad2d_real !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in),pt:integer:intent(in),pb:integer:intent(in),pl:integer:intent(in),pr:integer:intent(in),c:real(dp):intent(in) lib=arrays desc="2D constant pad for real matrix"
public :: allclose !@pyapi kind=function ret=logical args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in),rtol:real(dp):intent(in):optional,atol:real(dp):intent(in):optional,equal_nan:logical:intent(in):optional lib=arrays desc="NumPy-like allclose on 1D arrays"
public :: isclose_real !@pyapi kind=function ret=logical(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in),rtol:real(dp):intent(in):optional,atol:real(dp):intent(in):optional,equal_nan:logical:intent(in):optional lib=arrays desc="element-wise version of allclose (NumPy's isclose), a or b may have length 1 to broadcast"
public :: isclose_scalar_real !@pyapi kind=function ret=logical args=a:real(dp):intent(in),b:real(dp):intent(in),rtol:real(dp):intent(in):optional,atol:real(dp):intent(in):optional,equal_nan:logical:intent(in):optional lib=arrays desc="scalar counterpart of isclose_real, for np.isclose() with two scalar arguments"
public :: allclose_integer !@pyapi kind=function ret=logical args=a:integer(:):intent(in),b:integer(:):intent(in),rtol:real(dp):intent(in):optional,atol:real(dp):intent(in):optional lib=arrays desc="NumPy-like allclose on 1D integer arrays"
public :: cov2_real !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="2x2 covariance matrix for two real vectors"
public :: cov_matrix_rows_real !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="covariance matrix for observations in rows (numpy rowvar=False)"
public :: corrcoef2_real !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in) lib=statistics desc="2x2 correlation matrix for two real vectors"
public :: corrcoef_matrix_rows_real !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=statistics desc="correlation matrix for observations in rows (numpy rowvar=False)"
public :: autocorr_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),lag:integer:intent(in):optional lib=timeseries desc="pandas-style lag-k serial autocorrelation of a 1D real vector"
public :: corr2_1d !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in) lib=statistics desc="Pearson correlation of two 1D real vectors as a plain scalar"
public :: convolve_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),h:real(dp)(:):intent(in),mode:character:intent(in):optional,np_same:logical:intent(in):optional lib=signal desc="1D convolution with mode full/same/valid (same: scipy's, or np.convolve's with np_same)"
public :: diff_axis0_real_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="first difference along axis 0 for a real matrix"
public :: diff_axis1_real_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in) lib=arrays desc="first difference along axis 1 for a real matrix"
public :: sliding_window_view_axis0_real_2d !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:):intent(in),window:integer:intent(in) lib=arrays desc="axis-0 sliding window view for a real matrix"
public :: convolve_int !@pyapi kind=function ret=integer(:) args=x:integer(:):intent(in),h:integer(:):intent(in),mode:character:intent(in):optional,np_same:logical:intent(in):optional lib=signal desc="1D integer convolution with mode full/same/valid"
public :: correlate_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),mode:character:intent(in):optional,np_same:logical:intent(in):optional lib=signal desc="1D cross-correlation with mode full/same/valid (scipy.signal.correlate; np.correlate's same with np_same)"
public :: lfilter_real !@pyapi kind=function ret=real(dp)(:) args=b:real(dp)(:):intent(in),a:real(dp)(:):intent(in),x:real(dp)(:):intent(in) lib=signal desc="1D IIR/FIR filter, zero initial conditions (scipy.signal.lfilter)"
public :: filtfilt_real !@pyapi kind=function ret=real(dp)(:) args=b:real(dp)(:):intent(in),a:real(dp)(:):intent(in),x:real(dp)(:):intent(in) lib=signal desc="zero-phase forward-backward filter, no edge padding (scipy.signal.filtfilt)"
public :: lfilter_zi_real !@pyapi kind=function ret=real(dp)(:) args=b:real(dp)(:):intent(in),a:real(dp)(:):intent(in) lib=signal desc="steady-state IIR filter initial state for a unit step input (scipy.signal.lfilter_zi)"
public :: detrend_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),dtype:character:intent(in):optional lib=signal desc="remove linear or constant trend (scipy.signal.detrend)"
public :: find_peaks_int !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in),height:real(dp):intent(in):optional,distance:integer:intent(in):optional lib=signal desc="0-based local-maxima indices (scipy.signal.find_peaks, indices only)"
public :: loadtxt_real_vector !@pyapi kind=function ret=real(dp)(:) args=path:character(*):intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character(*):intent(in):optional,comments:character(*):intent(in):optional lib=io desc="np.loadtxt of a one-column (or flattened) text file as a real vector"
public :: loadtxt_int_vector !@pyapi kind=function ret=integer(:) args=path:character(*):intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character(*):intent(in):optional,comments:character(*):intent(in):optional lib=io desc="np.loadtxt(..., dtype=int) of a text file as an integer vector"
public :: loadtxt_logical_vector !@pyapi kind=function ret=logical(:) args=path:character(*):intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character(*):intent(in):optional,comments:character(*):intent(in):optional lib=io desc="np.loadtxt(..., dtype=bool) of a text file as a logical vector (nonzero is true)"
public :: loadtxt_real_2d !@pyapi kind=function ret=real(dp)(:,:) args=path:character:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional,usecols:integer(:):intent(in):optional lib=io desc="load real matrix text file with basic numpy-like options"
public :: loadtxt_real_1d !@pyapi kind=function ret=real(dp)(:) args=path:character:intent(in),usecol:integer:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional lib=io desc="load one selected real column as vector"
public :: loadtxt_int_2d !@pyapi kind=function ret=integer(:,:) args=path:character:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional,usecols:integer(:):intent(in):optional lib=io desc="load integer matrix from text file"
public :: loadtxt_int_1d !@pyapi kind=function ret=integer(:) args=path:character:intent(in),usecol:integer:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional lib=io desc="load one selected integer column as vector"
public :: loadtxt_logical_2d !@pyapi kind=function ret=logical(:,:) args=path:character:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional,usecols:integer(:):intent(in):optional lib=io desc="load logical matrix from text file (nonzero=>true)"
public :: loadtxt_logical_1d !@pyapi kind=function ret=logical(:) args=path:character:intent(in),usecol:integer:intent(in),skiprows:integer:intent(in):optional,max_rows:integer:intent(in):optional,skip_footer:integer:intent(in):optional,delimiter:character:intent(in):optional,comments:character:intent(in):optional lib=io desc="load one selected logical column as vector (nonzero=>true)"
public :: np_fmt_number
public :: savetxt_real_2d !@pyapi kind=subroutine args=path:character:intent(in),x:real(dp)(:,:):intent(in),delimiter:character:intent(in):optional,fmt:character:intent(in):optional lib=io desc="write real matrix text file with basic delimiter/fmt options"
public :: print_matrix !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),label:character:intent(in):optional desc="print 2D real matrix with aligned columns"
public :: print_array_3d !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),label:character:intent(in):optional desc="print 3D real array with numpy-style nested brackets"
public :: polyval_real_scalar !@pyapi kind=function ret=real(dp) args=p:real(dp)(:):intent(in),x:real(dp):intent(in) lib=polynomial desc="evaluate polynomial with descending coefficients at scalar x"
public :: polyval_real_vec !@pyapi kind=function ret=real(dp)(:) args=p:real(dp)(:):intent(in),x:real(dp)(:):intent(in) lib=polynomial desc="evaluate polynomial with descending coefficients at vector x"
public :: polyder_real !@pyapi kind=function ret=real(dp)(:) args=p:real(dp)(:):intent(in),m:integer:intent(in):optional lib=polynomial desc="m-th derivative coefficients for descending-order polynomial"
public :: polyroots_real !@pyapi kind=function ret=complex(dp)(:) args=p:real(dp)(:):intent(in) lib=polynomial desc="roots of real-coefficient polynomial (descending order) via LAPACK DGEEV"
public :: fft_fft !@pyapi kind=function ret=complex(dp)(:) args=x:real(dp)(:):intent(in),n:integer:intent(in):optional lib=fft desc="numpy-like fft for 1D real/complex input (naive DFT backend)"
public :: fft_ifft !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in),n:integer:intent(in):optional lib=fft desc="numpy-like ifft for 1D complex input (naive DFT backend)"
public :: fft_rfft !@pyapi kind=function ret=complex(dp)(:) args=x:real(dp)(:):intent(in),n:integer:intent(in):optional lib=fft desc="numpy-like rfft for 1D real input"
public :: fft_irfft !@pyapi kind=function ret=real(dp)(:) args=x:complex(dp)(:):intent(in),n:integer:intent(in):optional lib=fft desc="numpy-like irfft for 1D Hermitian spectrum"
public :: fft_fftfreq !@pyapi kind=function ret=real(dp)(:) args=n:integer:intent(in),d:real(dp):intent(in):optional lib=fft desc="numpy-like fftfreq(n,d)"
public :: fft_rfftfreq !@pyapi kind=function ret=real(dp)(:) args=n:integer:intent(in),d:real(dp):intent(in):optional lib=fft desc="numpy-like rfftfreq(n,d)"
public :: fft_axis_2d !@pyapi kind=function ret=complex(dp)(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in),n:integer:intent(in):optional,inverse:logical:intent(in):optional lib=fft desc="FFT (or inverse) of each column (dim=1) or row (dim=2) of a matrix, cropped or zero-padded to n"
public :: rfft_axis_2d !@pyapi kind=function ret=complex(dp)(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in),n:integer:intent(in):optional lib=fft desc="np.fft.rfft of each column (dim=1) or row (dim=2) of a real matrix"
public :: irfft_axis_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in),n:integer:intent(in):optional lib=fft desc="np.fft.irfft of each column (dim=1) or row (dim=2) of a matrix"
public :: fft2 !@pyapi kind=function ret=complex(dp)(:,:) args=x:real(dp)(:,:):intent(in),n1:integer:intent(in):optional,n2:integer:intent(in):optional lib=fft desc="np.fft.fft2 of a real or complex matrix (s=(n1, n2))"
public :: ifft2 !@pyapi kind=function ret=complex(dp)(:,:) args=x:complex(dp)(:,:):intent(in),n1:integer:intent(in):optional,n2:integer:intent(in):optional lib=fft desc="np.fft.ifft2 of a matrix"
public :: rfft2 !@pyapi kind=function ret=complex(dp)(:,:) args=x:real(dp)(:,:):intent(in),n1:integer:intent(in):optional,n2:integer:intent(in):optional lib=fft desc="np.fft.rfft2 of a real matrix"
public :: irfft2 !@pyapi kind=function ret=real(dp)(:,:) args=x:complex(dp)(:,:):intent(in),n1:integer:intent(in):optional,n2:integer:intent(in):optional lib=fft desc="np.fft.irfft2: inverse of rfft2"

public :: var !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="variance of 1D real vector with optional ddof (numpy-style)"
public :: mean !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="mean of 1D real vector"
public :: std !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="standard deviation of 1D real vector with optional ddof (numpy-style)"
public :: log2 !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="base-2 logarithm"
public :: nansum !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="sum ignoring NaN values"
public :: nanmean !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="mean ignoring NaN values"
public :: nanvar !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="variance ignoring NaN values with optional ddof"
public :: nanstd !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=statistics desc="standard deviation ignoring NaN values with optional ddof"
public :: nanmin !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="minimum ignoring NaN values"
public :: nanmax !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=statistics desc="maximum ignoring NaN values"
public :: nanargmin !@pyapi kind=function ret=integer args=x:real(dp)(:):intent(in) lib=statistics desc="0-based argmin ignoring NaN values; -1 when all NaN"
public :: nanargmax !@pyapi kind=function ret=integer args=x:real(dp)(:):intent(in) lib=statistics desc="0-based argmax ignoring NaN values; -1 when all NaN"
public :: optval !@pyapi kind=function ret=scalar args=x:scalar:intent(in):optional,default:scalar:intent(in) desc="return x when present, otherwise default"
public :: exec_cmd_status !@pyapi kind=function ret=integer args=cmd:character:intent(in) desc="execute shell command via execute_command_line and return exit status"
public :: py_time !@pyapi kind=function ret=real args= desc="wall-clock seconds from system_clock (Python time.time approximation)"
public :: py_omp_get_thread_num !@pyapi kind=function ret=integer args= desc="OpenMP thread number (0 without -fopenmp)"
public :: py_omp_get_num_threads !@pyapi kind=function ret=integer args= desc="OpenMP threads in the current team (1 without -fopenmp)"
public :: py_omp_get_max_threads !@pyapi kind=function ret=integer args= desc="OpenMP maximum threads (1 without -fopenmp)"
public :: py_omp_set_num_threads !@pyapi kind=subroutine args=n:integer:intent(in) desc="set the OpenMP thread count (no effect without -fopenmp)"
public :: py_ctime !@pyapi kind=function ret=character args=t:real(dp):intent(in):optional desc="string timestamp approximation for Python time.ctime"
public :: py_format_g_real !@pyapi kind=function ret=character args=x:real(dp):intent(in) desc="Python-like %g formatting helper for real scalars"
public :: py_format_real
public :: py_format_int
public :: narrow_int
public :: cumsum !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=arrays desc="cumulative sum of real vector (generic: cumsum_real, cumsum_int)"
public :: cumprod !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=arrays desc="cumulative product of real vector (generic: cumprod_real, cumprod_int)"
public :: eye !@pyapi kind=function ret=real(dp)(:,:) args=n:integer:intent(in),m:integer:intent(in):optional,k:integer:intent(in):optional lib=arrays desc="return n x m matrix with ones on diagonal k (default m=n, k=0) (generic: eye_real)"
public :: diag !@pyapi kind=function ret=complex(dp)(:) args=a:complex(dp)(:,:):intent(in) lib=arrays desc="(generic: diag_from_mat_complex, diag_from_vec_complex, diag_from_vec_real, diag_from_mat_real, diag_from_vec_int, diag_from_mat_int)"
public :: repeat !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="repeat each real element reps times (generic: repeat_real, repeat_int, repeat_logical, repeat_complex)"
public :: tile !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="tile real vector reps times (generic: tile_real, tile_int, tile_complex, tile_real_2d, tile_int_2d)"
public :: unique !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=sorting desc="sorted unique values of real vector (generic: unique_real, unique_int, unique_char, unique_complex)"
public :: sort_vec !@pyapi kind=subroutine args=x:real(dp)(:):intent(inout) lib=sorting desc="sort real vector x in ascending order (generic: sort_real_vec, sort_int_vec, sort_char_vec, sort_complex_vec)"
public :: argsort !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),idx:integer(:):intent(out) lib=sorting desc="argsort indices (0-based) of real vector (generic: argsort_real, argsort_int)"
public :: argsort_idx !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in) lib=sorting desc="argsort indices (0-based) of real vector (generic: argsort_idx_real, argsort_idx_int, argsort_complex_vec)"
public :: sorted_vec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=sorting desc="np.sort of a real vector: a sorted copy (generic: sorted_real_vec, sorted_int_vec, sorted_complex_vec)"
public :: diag_k !@pyapi kind=function ret=real(dp)(:,:) args=v:real(dp)(:):intent(in),k:integer:intent(in) lib=arrays desc="np.diag(v, k) of a vector: a square matrix with v on diagonal k (generic: diag_k_vec_real, diag_k_vec_int, diag_k_mat_real, diag_k_mat_int, diag_k_vec_complex, diag_k_mat_complex)"
public :: rng_pick
public :: rng_take_values
public :: rng_integers_v
public :: rng_choice_idx
public :: rng_choice_idx_p
public :: rng_permutation_idx
public :: rng_mvnormal
public :: rng_unit_uniform
public :: rng_std_normal1
public :: rng_std_gamma1
public :: rng_exponential_v
public :: rng_lognormal_v
public :: rng_gamma_v
public :: rng_beta_v
public :: rng_chisquare_v
public :: rng_laplace_v
public :: rng_logistic_v
public :: rng_standard_t_v
public :: rng_triangular_v
public :: rng_weibull_v
public :: rng_pareto_v
public :: rng_rayleigh_v
public :: rng_poisson_v
public :: rng_binomial_v
public :: rng_geometric_v
public :: stack_inv !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked (batched) linear algebra: linalg_inv(A) of each a(b,:,:)"
public :: stack_cholesky !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked (batched) linear algebra: linalg_cholesky(A) of each a(b,:,:)"
public :: stack_pinv !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked (batched) linear algebra: linalg_pinv(A) of each a(b,:,:)"
public :: stack_matrix_power !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),p:integer:intent(in) lib=linalg desc="numpy's stacked (batched) linear algebra: linalg_matrix_power(A, p) of each a(b,:,:)"
public :: stack_det !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: linalg_det(A) of each a(b,:,:)"
public :: stack_cond !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: linalg_cond(A) of each a(b,:,:)"
public :: stack_matrix_rank !@pyapi kind=function ret=integer(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: linalg_matrix_rank(A) of each a(b,:,:)"
public :: stack_norm2 !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: matrix_norm2_real(A) of each a(b,:,:)"
public :: stack_normm2 !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: matrix_normm2_real(A) of each a(b,:,:)"
public :: stack_eigvalsh !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: linalg_eigvalsh(A) of each a(b,:,:)"
public :: stack_eigvals !@pyapi kind=function ret=complex(dp)(:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="numpy's stacked linear algebra: linalg_eigvals_real(A) of each a(b,:,:)"
public :: stack_trace !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="np.linalg.trace of a stack: the trace of each a(b,:,:)"
public :: stack_diagonal !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="np.linalg.diagonal of a stack: the diagonal of each a(b,:,:)"
public :: stack_fro !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:,:):intent(in) lib=linalg desc="The Frobenius norm of each a(b,:,:) (norm(a, axis=(-2, -1)))"
public :: stack_solve_v !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:):intent(in) lib=linalg desc="np.linalg.solve(a, x) with a 1-D x: solve each a(b,:,:) y = x"
public :: stack_solve_m !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:,:):intent(in) lib=linalg desc="np.linalg.solve(a, x) with a matrix x, used for every a(b,:,:)"
public :: stack_solve_s !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:,:,:):intent(in) lib=linalg desc="np.linalg.solve(a, x) of two stacks: a(b,:,:) y = x(b,:,:)"
public :: stack_matmul_ss !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:,:,:):intent(in) lib=linalg desc="a @ x of two stacks of matrices"
public :: stack_matmul_sm !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:,:):intent(in) lib=linalg desc="a @ x of a stack and a matrix"
public :: stack_matmul_ms !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:):intent(in),x:real(dp)(:,:,:):intent(in) lib=linalg desc="a @ x of a matrix and a stack"
public :: stack_matmul_sv !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:,:):intent(in),x:real(dp)(:):intent(in) lib=linalg desc="a @ x of a stack and a vector"
public :: stack_matmul_vs !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:):intent(in),x:real(dp)(:,:,:):intent(in) lib=linalg desc="a @ x of a vector and a stack"
public :: stack_eigh !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),w:real(dp)(:,:):intent(out),v:real(dp)(:,:,:):intent(out) lib=linalg desc="w, v = np.linalg.eigh(a) of a stack"
public :: stack_eig !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),w:complex(dp)(:,:):intent(out),v:complex(dp)(:,:,:):intent(out) lib=linalg desc="w, v = np.linalg.eig(a) of a stack"
public :: stack_qr !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),q:real(dp)(:,:,:):intent(out),r:real(dp)(:,:,:):intent(out) lib=linalg desc="q, r = np.linalg.qr(a) (reduced) of a stack"
public :: stack_svd !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),u:real(dp)(:,:,:):intent(out),s:real(dp)(:,:):intent(out),vt:real(dp)(:,:,:):intent(out) lib=linalg desc="u, s, vt = np.linalg.svd(a) of a stack"
public :: stack_svd_econ !@pyapi kind=subroutine args=a:real(dp)(:,:,:):intent(in),u:real(dp)(:,:,:):intent(out),s:real(dp)(:,:):intent(out),vt:real(dp)(:,:,:):intent(out) lib=linalg desc="u, s, vt = np.linalg.svd(a, full_matrices=False) of a stack"
public :: np_kron2 !@pyapi kind=function ret=integer(:,:) args=a:integer(:,:):intent(in),b:integer(:,:):intent(in) lib=linalg desc="np.kron of two matrices (generic: np_kron2_int, np_kron2_real, np_kron2_complex)"
public :: np_cross3 !@pyapi kind=function ret=integer(:) args=a:integer(:):intent(in),b:integer(:):intent(in) lib=linalg desc="np.cross of two 3-vectors (generic: np_cross3_int, np_cross3_real, np_cross3_complex)"
public :: matrix_normm2_real !@pyapi kind=function ret=real(dp) args=a:real(dp)(:,:):intent(in) lib=linalg desc="np.linalg.norm(a, -2): the smallest singular value"
public :: np_searchsorted !@pyapi kind=function ret=integer args=a:real(dp)(:):intent(in),v:real(dp):intent(in),right:logical:intent(in) lib=sorting desc="np.searchsorted(a, v, side): 0-based insertion index of v in the sorted vector a (before equal values, or after them if right); NaN sorts after every number, as in numpy (generic: np_searchsorted_real, np_searchsorted_real_vec, np_searchsorted_int, np_searchsorted_int_vec)"
public :: np_union1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="np.union1d of vectors: sorted, without duplicates (generic: np_union1d_real, np_union1d_int, np_union1d_complex)"
public :: np_intersect1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="np.intersect1d of vectors: sorted, without duplicates (generic: np_intersect1d_real, np_intersect1d_int, np_intersect1d_complex)"
public :: np_setdiff1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="np.setdiff1d of vectors: sorted, without duplicates (generic: np_setdiff1d_real, np_setdiff1d_int, np_setdiff1d_complex)"
public :: np_setxor1d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="np.setxor1d of vectors: sorted, without duplicates (generic: np_setxor1d_real, np_setxor1d_int, np_setxor1d_complex)"
public :: np_isin1 !@pyapi kind=function ret=logical(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="a(i) in b for each element of the vector a (generic: np_isin1_real, np_isin1_int, np_isin1_complex)"
public :: np_unique_counts !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in) lib=sorting desc="np.unique(x, return_counts=True)[1] of a vector (0-based indices) (generic: np_unique_counts_real, np_unique_counts_int, np_unique_counts_complex)"
public :: np_unique_index !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in) lib=sorting desc="np.unique(x, return_index=True)[1] of a vector (0-based indices) (generic: np_unique_index_real, np_unique_index_int, np_unique_index_complex)"
public :: np_unique_inverse !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in) lib=sorting desc="np.unique(x, return_inverse=True)[1] of a vector (0-based indices) (generic: np_unique_inverse_real, np_unique_inverse_int, np_unique_inverse_complex)"
public :: np_gather2d !@pyapi kind=function ret=real(dp)(:) args=m:real(dp)(:,:):intent(in),i:integer(:):intent(in),j:integer(:):intent(in) lib=arrays desc="m[i, j] with integer index vectors i, j (0-based, negative from the end): [m[i[0], j[0]], m[i[1], j[1]], ...] (generic: np_gather2d_real, np_gather2d_int, np_gather2d_log, np_gather2d_complex)"
public :: np_bincount_weights !@pyapi kind=function ret=real(dp)(:) args=x:integer(:):intent(in),w:real(dp)(:):intent(in),minlength:integer:intent(in) lib=statistics desc="np.bincount(x, weights=w, minlength=...): c(v+1) = sum of w where x == v"
public :: np_digitize !@pyapi kind=function ret=integer args=x:real(dp):intent(in),bins:real(dp)(:):intent(in),right:logical:intent(in) lib=statistics desc="np.digitize(x, bins, right): for increasing bins the i with bins[i-1] <= x < bins[i] (bins[i-1] < x <= bins[i] if right), for decreasing bins numpy's len(bins) - ... (generic: np_digitize_scalar, np_digitize_vec)"
public :: c_lt !@pyapi kind=function ret=logical args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="numpy's ordering of complex numbers: by real part, then imaginary part"
public :: c_le !@pyapi kind=function ret=logical args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="numpy's ordering of complex numbers: by real part, then imaginary part, a NaN after every number (as np.sort places them)"
public :: c_gt !@pyapi kind=function ret=logical args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="numpy's ordering of complex numbers: by real part, then imaginary part"
public :: c_ge !@pyapi kind=function ret=logical args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="numpy's ordering of complex numbers: by real part, then imaginary part"
public :: c_maximum !@pyapi kind=function ret=complex(dp) args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="np.maximum of complex numbers (lexicographic)"
public :: c_minimum !@pyapi kind=function ret=complex(dp) args=a:complex(dp):intent(in),b:complex(dp):intent(in) lib=arrays desc="np.minimum of complex numbers in numpy's order (real part, then imaginary part)"
public :: c_round !@pyapi kind=function ret=complex(dp) args=z:complex(dp):intent(in),d:integer:intent(in) lib=arrays desc="np.round of a complex number: both parts, half to even"
public :: c_amin !@pyapi kind=function ret=complex(dp) args=x:complex(dp)(:):intent(in) lib=arrays desc="(generic: c_amin_r1, c_amin_r2, c_amin_r2_dim)"
public :: c_amax !@pyapi kind=function ret=complex(dp) args=x:complex(dp)(:):intent(in) lib=arrays desc="(generic: c_amax_r1, c_amax_r2, c_amax_r2_dim)"
public :: c_argmin !@pyapi kind=function ret=integer args=x:complex(dp)(:):intent(in) lib=arrays desc="np.argmin (0-based) of complex numbers, the first extreme value (generic: c_argmin_r1, c_argmin_r2_dim)"
public :: c_argmax !@pyapi kind=function ret=integer args=x:complex(dp)(:):intent(in) lib=arrays desc="np.argmax (0-based) of complex numbers, the first extreme value (generic: c_argmax_r1, c_argmax_r2_dim)"
public :: cumsum_complex !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in) lib=arrays desc="cumulative sum of a complex vector"
public :: cumprod_complex !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in) lib=arrays desc="cumulative product of a complex vector"
public :: cumsum_complex_2d !@pyapi kind=function ret=complex(dp)(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.cumsum(x, axis=dim-1) of a complex matrix"
public :: cumprod_complex_2d !@pyapi kind=function ret=complex(dp)(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.cumprod(x, axis=dim-1) of a complex matrix"
public :: sorted_complex_vec !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in) lib=sorting desc="np.sort of a complex vector (by real part, then imaginary part, NaN last): a sorted copy"
public :: sorted_complex_2d !@pyapi kind=function ret=complex(dp)(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.sort of a complex matrix along dimension dim (1 = down columns)"
public :: argsort_complex_vec !@pyapi kind=function ret=integer(:) args=x:complex(dp)(:):intent(in) lib=sorting desc="np.argsort (0-based, stable) of complex numbers in numpy's lexicographic order -- an insertion-free bottom-up merge sort"
public :: argsort_complex_2d !@pyapi kind=function ret=integer(:,:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.argsort (0-based) of a complex matrix along dimension dim"
public :: sort_complex_vec !@pyapi kind=subroutine args=x:complex(dp)(:):intent(inout) lib=sorting desc="x.sort() of a complex vector"
public :: unique_complex !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in) lib=sorting desc="np.unique of complex numbers: sorted, duplicates removed"
public :: median_complex !@pyapi kind=function ret=complex(dp) args=x:complex(dp)(:):intent(in) lib=statistics desc="np.median of complex numbers: the middle of the lexicographic order (the mean of the two middle values for an even count)"
public :: median_complex_2d !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:,:):intent(in),dim:integer:intent(in) lib=statistics desc="np.median of a complex matrix along dimension dim"
public :: reversed_complex_vec !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in) lib=arrays desc="x[::-1] of a complex vector expression"
public :: repeat_complex !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="np.repeat of a complex vector: each element reps times"
public :: tile_complex !@pyapi kind=function ret=complex(dp)(:) args=x:complex(dp)(:):intent(in),reps:integer:intent(in) lib=arrays desc="np.tile of a complex vector reps times"
public :: diag_k_vec_complex !@pyapi kind=function ret=complex(dp)(:,:) args=v:complex(dp)(:):intent(in),k:integer:intent(in) lib=arrays desc="np.diag(v, k) of a complex vector"
public :: diag_k_mat_complex !@pyapi kind=function ret=complex(dp)(:) args=a:complex(dp)(:,:):intent(in),k:integer:intent(in) lib=arrays desc="np.diag(a, k) of a complex matrix: its k-th diagonal"
public :: sort_axis_3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:,:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.sort(x, axis=dim-1) of a rank-3 array: sorted_vec along dim (generic: sort_axis_3d_real, sort_axis_3d_int)"
public :: argsort_axis_3d !@pyapi kind=function ret=integer(:,:,:) args=x:real(dp)(:,:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.argsort(x, axis=dim-1) of a rank-3 array: argsort_idx along dim (generic: argsort_axis_3d_real, argsort_axis_3d_int)"
public :: cumsum_axis_3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:,:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.cumsum(x, axis=dim-1) of a rank-3 array: cumsum_real along dim (generic: cumsum_axis_3d_real, cumsum_axis_3d_int)"
public :: cumprod_axis_3d !@pyapi kind=function ret=real(dp)(:,:,:) args=x:real(dp)(:,:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.cumprod(x, axis=dim-1) of a rank-3 array: cumprod_real along dim (generic: cumprod_axis_3d_real, cumprod_axis_3d_int)"
public :: trace_3d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:,:,:):intent(in) lib=arrays desc="np.trace of a rank-3 array: sum of x[i, i, :] over i (generic: trace_3d_real, trace_3d_int)"
public :: concat_3d !@pyapi kind=function ret=real(dp)(:,:,:) args=a:real(dp)(:,:,:):intent(in),b:real(dp)(:,:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.concatenate([a, b], axis=dim-1) of rank-3 arrays (generic: concat_3d_real, concat_3d_int)"
public :: nonzero_3d !@pyapi kind=function ret=integer(:) args=mask:logical(:,:,:):intent(in),k:integer:intent(in) lib=arrays desc="np.nonzero(x)[k-1] of a rank-3 array (mask = x /= 0): the 0-based axis-k indices of the true elements, in C (row-major) order"
public :: quantile_axis_3d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:,:):intent(in),q:real(dp):intent(in),dim:integer:intent(in) lib=statistics desc="np.quantile(x, q, axis) of a rank-3 array"
public :: np_amin !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=arrays desc="np.min: NaN if x holds a NaN (numpy propagates it) (generic: np_amin_r1, np_amin_r2, np_amin_r2_dim)"
public :: np_amax !@pyapi kind=function ret=real(dp) args=x:real(dp)(:):intent(in) lib=arrays desc="np.max: NaN if x holds a NaN (numpy propagates it) (generic: np_amax_r1, np_amax_r2, np_amax_r2_dim)"
public :: np_argmin !@pyapi kind=function ret=integer args=x:real(dp)(:):intent(in) lib=arrays desc="np.argmin (0-based): the first NaN if x holds one, as numpy does (generic: np_argmin_r1, np_argmin_r2_dim)"
public :: np_argmax !@pyapi kind=function ret=integer args=x:real(dp)(:):intent(in) lib=arrays desc="np.argmax (0-based): the first NaN if x holds one, as numpy does (generic: np_argmax_r1, np_argmax_r2_dim)"
public :: np_maximum !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in),b:real(dp):intent(in) lib=arrays desc="np.maximum: NaN if either is NaN"
public :: np_minimum !@pyapi kind=function ret=real(dp) args=a:real(dp):intent(in),b:real(dp):intent(in) lib=arrays desc="np.minimum: NaN if either is NaN"
public :: np_clip !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),lo:real(dp):intent(in),hi:real(dp):intent(in) lib=arrays desc="np.clip: NaN stays NaN"
public :: np_floor !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="np.floor of a float: NaN and infinities unchanged, no integer conversion (which overflows for large values)"
public :: np_ceil !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="np.ceil of a float: NaN and infinities unchanged, no integer conversion"
public :: np_sign !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="np.sign of a float: -1, 0 or 1, NaN for NaN"
public :: histogram_counts !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in),nbins:integer:intent(in) lib=statistics desc="np.histogram(x, bins=n)[0]: counts in n equal bins spanning min(x)..max(x)"
public :: histogram_counts_edges !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in),edges:real(dp)(:):intent(in) lib=statistics desc="np.histogram(x, bins=edges)[0]"
public :: triu !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in),k:integer:intent(in):optional lib=arrays desc="np.triu(a, k): zero below diagonal k (generic: triu_real, triu_int, triu_complex)"
public :: tril !@pyapi kind=function ret=real(dp)(:,:) args=a:real(dp)(:,:):intent(in),k:integer:intent(in):optional lib=arrays desc="np.tril(a, k): zero above diagonal k (generic: tril_real, tril_int, tril_complex)"
public :: quantile_axis_2d_q !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),q:real(dp)(:):intent(in),dim:integer:intent(in) lib=statistics desc="np.quantile(x, q, axis=dim-1) of a matrix at several probabilities: row k for q(k)"
public :: quantile_axis_2d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:,:):intent(in),q:real(dp):intent(in),dim:integer:intent(in) lib=statistics desc="np.quantile(x, q, axis) of a matrix: linear quantile of each column (dim=1) or row (dim=2)"
public :: reversed_vec !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=arrays desc="x[::-1] / np.flip(x) of a vector expression (a function result can't be subscripted in Fortran) (generic: reversed_real_vec, reversed_int_vec, reversed_logical_vec, reversed_complex_vec)"
public :: reversed_mat !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in) lib=arrays desc="np.flip(x, axis) of a matrix expression: dim 1 reverses the rows (axis=0), 2 the columns (axis=1), 0 both (axis=None) (generic: reversed_real_mat, reversed_int_mat, reversed_logical_mat, reversed_complex_mat)"
public :: sorted_2d !@pyapi kind=function ret=real(dp)(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.sort of a real matrix along dimension dim (1 = down columns) (generic: sorted_real_2d, sorted_int_2d, sorted_complex_2d)"
public :: argsort_2d !@pyapi kind=function ret=integer(:,:) args=x:real(dp)(:,:):intent(in),dim:integer:intent(in) lib=sorting desc="np.argsort (0-based) of a real matrix along dimension dim (generic: argsort_real_2d, argsort_int_2d, argsort_complex_2d)"
public :: histogram !@pyapi kind=subroutine args=x:real(dp)(:):intent(in),bins:real(dp)(:):intent(in),h:integer(:):intent(out),edges:real(dp)(:):intent(out) lib=statistics desc="1D histogram with explicit real bin edges (generic: histogram_real_edges, histogram_int_edges)"
public :: reduceat_add !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.add.reduceat for real vector (generic: reduceat_add_real, reduceat_add_int)"
public :: reduceat_mul !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.multiply.reduceat for real vector (generic: reduceat_mul_real, reduceat_mul_int)"
public :: reduceat_min !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.minimum.reduceat for real vector (generic: reduceat_min_real, reduceat_min_int)"
public :: reduceat_max !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),idx:integer(:):intent(in) lib=arrays desc="np.maximum.reduceat for real vector (generic: reduceat_max_real, reduceat_max_int)"
public :: polyval !@pyapi kind=function ret=real(dp) args=p:real(dp)(:):intent(in),x:real(dp):intent(in) lib=polynomial desc="evaluate polynomial with descending coefficients at scalar x (generic: polyval_real_scalar, polyval_real_vec, polyval_complex_scalar, polyval_complex_vec)"
public :: polyder !@pyapi kind=function ret=real(dp)(:) args=p:real(dp)(:):intent(in),m:integer:intent(in):optional lib=polynomial desc="m-th derivative coefficients for descending-order polynomial (generic: polyder_real)"
public :: polyfit_real !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),y:real(dp)(:):intent(in),deg:integer:intent(in) lib=polynomial desc="least-squares polynomial fit (deg+1 coefficients, highest degree first), matching numpy.polyfit"
public :: digitize_real !@pyapi kind=function ret=integer(:) args=x:real(dp)(:):intent(in),bins:real(dp)(:):intent(in) lib=statistics desc="bin index of each x(i) against increasing bin edges, matching numpy.digitize (right=False)"
public :: isin_real !@pyapi kind=function ret=logical(:) args=a:real(dp)(:):intent(in),b:real(dp)(:):intent(in) lib=sorting desc="element-wise membership test, matching numpy.isin (and numpy.in1d) for real arrays"
public :: isin_int !@pyapi kind=function ret=logical(:) args=a:integer(:):intent(in),b:integer(:):intent(in) lib=sorting desc="element-wise membership test, matching numpy.isin (and numpy.in1d) for integer arrays"
public :: np_save_1d_real !@pyapi kind=subroutine args=filename:character(*):intent(in),x:real(dp)(:):intent(in) lib=io desc="write a 1D real array to a binary .npy file, matching numpy.save"
public :: np_load_1d_real !@pyapi kind=function ret=real(dp)(:) args=filename:character(*):intent(in) lib=io desc="read a 1D real array from a binary .npy file, matching numpy.load"

public :: rolling_mean_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),window:integer:intent(in) lib=timeseries desc="rolling mean over a trailing window (NaN until the window fills), Alan Miller's online update/downdate algorithm"
public :: rolling_std_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),window:integer:intent(in),ddof:integer:intent(in) lib=timeseries desc="rolling sample standard deviation over a trailing window (NaN until the window fills), Alan Miller's online update/downdate algorithm"
public :: expanding_mean_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in) lib=timeseries desc="expanding (growing-window, min_periods=1) running mean"
public :: expanding_std_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),ddof:integer:intent(in):optional lib=timeseries desc="expanding (growing-window) sample standard deviation"
public :: ewm_mean_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),alpha:real(dp):intent(in) lib=timeseries desc="exponentially weighted moving average (adjust=True, pandas' default)"
public :: ewm_std_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),alpha:real(dp):intent(in) lib=timeseries desc="exponentially weighted sample standard deviation (adjust=True, bias=False, pandas' defaults)"
public :: shift_1d !@pyapi kind=function ret=real(dp)(:) args=x:real(dp)(:):intent(in),periods:integer:intent(in):optional,fill_value:real(dp):intent(in):optional lib=timeseries desc="pandas-style Series.shift(periods, fill_value) for a plain 1D real vector"

public :: py_round_ndigits !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),ndigits:integer:intent(in) desc="Python 3 round(x, ndigits): ties round to even (banker's rounding)"
public :: floor_div_real !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in) lib=arrays desc="Python-style real floor division (x // y, floor of the quotient, result stays real)"
public :: np_rint !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=arrays desc="numpy rint/round: nearest integer, ties to even"
public :: py_round_int !@pyapi kind=function ret=integer args=x:real(dp):intent(in) desc="Python 3 round(x) with no ndigits: banker's rounding to the nearest integer"
public :: csign_complex !@pyapi kind=function ret=complex(dp) args=x:complex(dp):intent(in) lib=arrays desc="np.sign() for complex input: x / abs(x), 0 at the origin"
public :: floor_div_int !@pyapi kind=function ret=integer args=x:integer:intent(in),y:integer:intent(in) lib=integers desc="Python-style integer floor division (x // y, floors toward negative infinity)"

public :: log1p !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="log(1 + x), full precision for small abs(x) via the C library's own log1p()"
public :: expm1 !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in) lib=special desc="exp(x) - 1, full precision for small abs(x) via the C library's own expm1()"

public :: math_remainder !@pyapi kind=function ret=real(dp) args=x:real(dp):intent(in),y:real(dp):intent(in) desc="Python 3 math.remainder(x, y): IEEE 754 remainder, x - round(x/y)*y with ties to even"

public :: expm1_complex !@pyapi kind=function ret=complex(dp) args=x:complex(dp):intent(in) lib=special desc="np.expm1 for complex input: exp(x) - 1, precise for small abs(real(x))"
public :: log1p_complex !@pyapi kind=function ret=complex(dp) args=x:complex(dp):intent(in) lib=special desc="np.log1p for complex input: log(1 + x)"

public :: complex_amin !@pyapi kind=function ret=complex(dp) args=arr:complex(dp)(:):intent(in) lib=arrays desc="np.amin/np.min on a complex array: numpy orders complex values lexicographically (real part first, then imaginary part as a tiebreak), which MINVAL can't do since it rejects complex operands entirely"
public :: complex_amax !@pyapi kind=function ret=complex(dp) args=arr:complex(dp)(:):intent(in) lib=arrays desc="np.amax/np.max on a complex array: numpy orders complex values lexicographically (real part first, then imaginary part as a tiebreak), which MAXVAL can't do since it rejects complex operands entirely"

interface cumsum
   module procedure cumsum_real, cumsum_int
end interface cumsum

interface cumprod
   module procedure cumprod_real, cumprod_int
end interface cumprod

interface matrix_norm2
   module procedure matrix_norm2_real, matrix_norm2_complex
end interface matrix_norm2

interface linalg_eigvals
   module procedure linalg_eigvals_real, linalg_eigvals_complex
end interface linalg_eigvals

interface eye
   module procedure eye_real
end interface eye

interface diag
   module procedure diag_from_mat_complex, diag_from_vec_complex
   module procedure diag_from_vec_real, diag_from_mat_real
   module procedure diag_from_vec_int, diag_from_mat_int
end interface diag

interface diagonal
   module procedure diagonal_int_2d, diagonal_real_2d, diagonal_complex_2d
   module procedure diagonal_int_3d_axis12, diagonal_real_3d_axis12
end interface diagonal

interface repeat
   module procedure repeat_real, repeat_int, repeat_logical, repeat_complex
end interface repeat

interface tile
   module procedure tile_real, tile_int, tile_complex
   module procedure tile_real_2d, tile_int_2d
end interface tile

interface unique
   module procedure unique_real, unique_int, unique_char, unique_complex
end interface unique

interface sort_vec
   module procedure sort_real_vec, sort_int_vec, sort_char_vec, sort_complex_vec
end interface sort_vec

interface argsort
   module procedure argsort_real, argsort_int
end interface argsort

interface argsort_idx
   module procedure argsort_idx_real, argsort_idx_int, argsort_complex_vec
end interface argsort_idx

interface sorted_vec
   module procedure sorted_real_vec, sorted_int_vec, sorted_complex_vec
end interface sorted_vec

interface np_amin
   module procedure np_amin_r1, np_amin_r2, np_amin_r2_dim
end interface np_amin

interface np_amax
   module procedure np_amax_r1, np_amax_r2, np_amax_r2_dim
end interface np_amax

interface np_argmin
   module procedure np_argmin_r1, np_argmin_r2_dim
end interface np_argmin

interface np_argmax
   module procedure np_argmax_r1, np_argmax_r2_dim
end interface np_argmax

interface sort_axis_3d
   module procedure sort_axis_3d_real, sort_axis_3d_int
end interface sort_axis_3d

interface argsort_axis_3d
   module procedure argsort_axis_3d_real, argsort_axis_3d_int
end interface argsort_axis_3d

interface cumsum_axis_3d
   module procedure cumsum_axis_3d_real, cumsum_axis_3d_int
end interface cumsum_axis_3d

interface cumprod_axis_3d
   module procedure cumprod_axis_3d_real, cumprod_axis_3d_int
end interface cumprod_axis_3d

interface trace_3d
   module procedure trace_3d_real, trace_3d_int
end interface trace_3d

interface concat_3d
   module procedure concat_3d_real, concat_3d_int
end interface concat_3d

interface c_amin
   module procedure c_amin_r1, c_amin_r2, c_amin_r2_dim
end interface c_amin

interface c_amax
   module procedure c_amax_r1, c_amax_r2, c_amax_r2_dim
end interface c_amax

interface c_argmin
   module procedure c_argmin_r1, c_argmin_r2_dim
end interface c_argmin

interface c_argmax
   module procedure c_argmax_r1, c_argmax_r2_dim
end interface c_argmax

interface np_searchsorted
   module procedure np_searchsorted_real, np_searchsorted_real_vec, np_searchsorted_int, np_searchsorted_int_vec
end interface np_searchsorted

interface np_union1d
   module procedure np_union1d_real, np_union1d_int, np_union1d_complex
end interface np_union1d

interface np_intersect1d
   module procedure np_intersect1d_real, np_intersect1d_int, np_intersect1d_complex
end interface np_intersect1d

interface np_setdiff1d
   module procedure np_setdiff1d_real, np_setdiff1d_int, np_setdiff1d_complex
end interface np_setdiff1d

interface np_setxor1d
   module procedure np_setxor1d_real, np_setxor1d_int, np_setxor1d_complex
end interface np_setxor1d

interface np_isin1
   module procedure np_isin1_real, np_isin1_int, np_isin1_complex
end interface np_isin1

interface np_unique_counts
   module procedure np_unique_counts_real, np_unique_counts_int, np_unique_counts_complex
end interface np_unique_counts

interface np_unique_index
   module procedure np_unique_index_real, np_unique_index_int, np_unique_index_complex
end interface np_unique_index

interface np_unique_inverse
   module procedure np_unique_inverse_real, np_unique_inverse_int, np_unique_inverse_complex
end interface np_unique_inverse

interface np_digitize
   module procedure np_digitize_scalar, np_digitize_vec
end interface np_digitize

interface np_gather2d
   module procedure np_gather2d_real, np_gather2d_int, np_gather2d_log, np_gather2d_complex
end interface np_gather2d

interface np_kron2
   module procedure np_kron2_int, np_kron2_real, np_kron2_complex
end interface np_kron2

interface np_cross3
   module procedure np_cross3_int, np_cross3_real, np_cross3_complex
end interface np_cross3

interface rng_pick
   module procedure rng_pick_real, rng_pick_int, rng_pick_log, rng_pick_complex
end interface rng_pick

interface diag_k
   module procedure diag_k_vec_real, diag_k_vec_int, diag_k_mat_real, diag_k_mat_int
   module procedure diag_k_vec_complex, diag_k_mat_complex
end interface diag_k

interface triu
   module procedure triu_real, triu_int, triu_complex
end interface triu

interface tril
   module procedure tril_real, tril_int, tril_complex
end interface tril

interface reversed_vec
   module procedure reversed_real_vec, reversed_int_vec, reversed_logical_vec, reversed_complex_vec
end interface reversed_vec
interface reversed_mat
   module procedure reversed_real_mat, reversed_int_mat, reversed_logical_mat, reversed_complex_mat
end interface reversed_mat

interface sorted_2d
   module procedure sorted_real_2d, sorted_int_2d, sorted_complex_2d
end interface sorted_2d

interface argsort_2d
   module procedure argsort_real_2d, argsort_int_2d, argsort_complex_2d
end interface argsort_2d

interface powval
   module procedure powval_0, powval_1, powval_2
end interface powval

interface powval2d
   module procedure powval2d_0, powval2d_1, powval2d_2
end interface powval2d
interface powval3d
   module procedure powval3d_0, powval3d_1
end interface powval3d
interface chebval2d
   module procedure chebval2d_0, chebval2d_1, chebval2d_2
end interface chebval2d
interface chebval3d
   module procedure chebval3d_0, chebval3d_1
end interface chebval3d
interface legval2d
   module procedure legval2d_0, legval2d_1, legval2d_2
end interface legval2d
interface legval3d
   module procedure legval3d_0, legval3d_1
end interface legval3d
interface hermval2d
   module procedure hermval2d_0, hermval2d_1, hermval2d_2
end interface hermval2d
interface hermval3d
   module procedure hermval3d_0, hermval3d_1
end interface hermval3d
interface hermeval2d
   module procedure hermeval2d_0, hermeval2d_1, hermeval2d_2
end interface hermeval2d
interface hermeval3d
   module procedure hermeval3d_0, hermeval3d_1
end interface hermeval3d
interface lagval2d
   module procedure lagval2d_0, lagval2d_1, lagval2d_2
end interface lagval2d
interface lagval3d
   module procedure lagval3d_0, lagval3d_1
end interface lagval3d
interface powvalfromroots
   module procedure powvalfromroots_0, powvalfromroots_1, powvalfromroots_2
end interface powvalfromroots
interface chebval
   module procedure chebval_0, chebval_1, chebval_2
end interface chebval

interface legval
   module procedure legval_0, legval_1, legval_2
end interface legval

interface hermval
   module procedure hermval_0, hermval_1, hermval_2
end interface hermval

interface hermeval
   module procedure hermeval_0, hermeval_1, hermeval_2
end interface hermeval

interface lagval
   module procedure lagval_0, lagval_1, lagval_2
end interface lagval

interface np_polyadd
   module procedure np_polyadd_real, np_polyadd_int
end interface np_polyadd

interface np_polymul
   module procedure np_polymul_real, np_polymul_int
end interface np_polymul

interface histogram
   module procedure histogram_real_edges, histogram_int_edges
end interface histogram

interface reduceat_add
   module procedure reduceat_add_real, reduceat_add_int
end interface reduceat_add

interface reduceat_mul
   module procedure reduceat_mul_real, reduceat_mul_int
end interface reduceat_mul

interface reduceat_min
   module procedure reduceat_min_real, reduceat_min_int
end interface reduceat_min

interface reduceat_max
   module procedure reduceat_max_real, reduceat_max_int
end interface reduceat_max

interface polyval
   module procedure polyval_real_scalar, polyval_real_vec, polyval_complex_scalar, polyval_complex_vec
end interface polyval

interface polyder
   module procedure polyder_real
end interface polyder

interface runif
   module procedure runif0, runif1, runif2, runif3
end interface runif

interface rnorm
   module procedure rnorm0, rnorm1, rnorm2, rnorm3
end interface rnorm

interface allclose
   module procedure allclose_real, allclose_integer
end interface allclose

interface py_str
   module procedure py_str_int32, py_str_int64, py_str_real, py_str_logical, py_str_char
   module procedure py_str_int_vec, py_str_int64_vec, py_str_real_vec, py_str_logical_vec, py_str_char_vec
end interface py_str

! Integer text for default and 64-bit integers (--int-kind int64 keeps a
! value beyond 2**31 intact instead of narrowing it first).
interface py_str_int
   module procedure py_str_int32, py_str_int64
end interface py_str_int

interface py_format_int
   module procedure py_format_int32, py_format_int64
end interface py_format_int

! Default-kind value of a 64-bit integer, stopping if it does not fit
! (used by --int-kind int64 where a helper takes a default integer).
interface narrow_int
   module procedure narrow_int_i32, narrow_int_i64
end interface narrow_int

! The mold selects the integer result kind, not the value to round.
interface py_round_int
   module procedure py_round_int32, py_round_int64
end interface py_round_int

interface str_concat
   module procedure str_concat_ss, str_concat_sv, str_concat_vs, str_concat_vv
end interface str_concat

interface linalg_solve
   module procedure linalg_solve_vec, linalg_solve_mat
   module procedure linalg_solve_complex_vec, linalg_solve_complex_mat
end interface linalg_solve

public :: where_indices_2d !@pyapi kind=function ret=integer(:,:) args=mask:logical(:,:):intent(in) lib=arrays desc="np.argwhere of a logical matrix: the 0-based (row, column) of each true element, in C order"
public :: where_axis_2d !@pyapi kind=function ret=integer(:) args=mask:logical(:,:):intent(in),axis:integer:intent(in) lib=arrays desc="np.nonzero(mask)[axis] of a logical matrix: 0-based row (axis 0) or column (axis 1) indices of the true elements, in C order"
public :: where_pair_2d !@pyapi kind=function ret=integer(:,:) args=rows:integer(:):intent(in),cols:integer(:):intent(in) lib=arrays desc="pair 0-based row and column index vectors (a length-1 one broadcast) as a 2 x n index array"
public :: gather_where2d !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:):intent(in),idx:integer(:,:):intent(in) lib=arrays desc="(generic: gather_where2d_real, gather_where2d_int, gather_where2d_complex, gather_where2d_logical)"
interface gather_where2d
   module procedure gather_where2d_real, &
      & gather_where2d_int, &
      & gather_where2d_complex, &
      & gather_where2d_logical
end interface gather_where2d
public :: lexsort_keys !@pyapi kind=function ret=integer(:) args=keys:integer(:,:):intent(in),reverse_keys:logical:intent(in):optional lib=sorting desc="(generic: lexsort_keys_int, lexsort_keys_real, lexsort_packed_int, lexsort_packed_real)"
interface lexsort_keys
   module procedure lexsort_keys_int, lexsort_keys_real
   module procedure lexsort_packed_int, lexsort_packed_real
end interface lexsort_keys

public :: linalg_lstsq !@pyapi kind=subroutine args=a:real(dp)(:,:):intent(in),b:real(dp)(:):intent(in),x:real(dp)(:):intent(out),residuals:real(dp)(:):intent(out),rnk:integer:intent(out),s:real(dp)(:):intent(out),rcond:real(dp):intent(in):optional lib=linalg desc="(generic: linalg_lstsq_vec, linalg_lstsq_mat)"
public :: linalg_lstsq_x !@pyapi kind=function ret=real(dp)(:) args=a:real(dp)(:,:):intent(in),b:real(dp)(:):intent(in),rcond:real(dp):intent(in):optional lib=linalg desc="(generic: linalg_lstsq_x_vec, linalg_lstsq_x_mat)"
interface linalg_lstsq
   module procedure linalg_lstsq_vec, linalg_lstsq_mat
end interface linalg_lstsq
interface linalg_lstsq_x
   module procedure linalg_lstsq_x_vec, linalg_lstsq_x_mat
end interface linalg_lstsq_x

interface linalg_solve_safe
   module procedure linalg_solve_safe_vec
end interface linalg_solve_safe

interface optval
   module procedure optval_int
   module procedure optval_real
   module procedure optval_logical
   module procedure optval_char
   module procedure optval_complex
end interface optval

interface convolve
   module procedure convolve_real
   module procedure convolve_int
end interface convolve

interface print_matrix
   module procedure print_matrix_real_2d
   module procedure print_matrix_label_real_2d
   module procedure print_matrix_int_2d
   module procedure print_matrix_label_int_2d
   module procedure print_matrix_logical_2d
   module procedure print_matrix_complex_2d
end interface print_matrix

interface print_array_3d
   module procedure print_array_3d_real
   module procedure print_array_3d_label_real
   module procedure print_array_3d_int
   module procedure print_array_3d_logical
   module procedure print_array_3d_label_int
end interface print_array_3d

interface index1
   module procedure index1_real
   module procedure index1_int
   module procedure index1_logical
   module procedure index1_complex
   module procedure index1_char
end interface index1

interface index2
   module procedure index2_real
   module procedure index2_int
   module procedure index2_logical
   module procedure index2_complex
   module procedure index2_char
end interface index2

interface slice1
   module procedure slice1_real
   module procedure slice1_int
   module procedure slice1_logical
   module procedure slice1_complex
   module procedure slice1_char
end interface slice1

interface np_pad_vec
   module procedure np_pad_vec_real, np_pad_vec_int, np_pad_vec_complex, np_pad_vec_logical
end interface np_pad_vec
interface fft2
   module procedure fft2_real, fft2_complex
end interface fft2
interface fft_fft
   module procedure fft_fft_real
   module procedure fft_fft_complex
end interface fft_fft

contains

      pure integer function isqrt_int(x)
         ! integer square root: return floor(sqrt(x)) for x >= 0
         implicit none
         integer, intent(in) :: x  ! input integer (x >= 0 expected)
         integer :: r
         if (x <= 0) then
            isqrt_int = 0
            return
         end if
         r = int(sqrt(real(x, kind=dp)))
         do while ((r+1)*(r+1) <= x)
            r = r + 1
         end do
         do while (r*r > x)
            r = r - 1
         end do
         isqrt_int = r
      end function isqrt_int

      pure integer function mod_pow_int(base, exp, modulus)
         ! modular exponentiation: pow(base, exp, modulus)
         implicit none
         integer, intent(in) :: base, exp, modulus
         integer(kind=int64) :: b, e, m, res
         if (modulus == 0) then
            mod_pow_int = 0
            return
         end if
         m = int(modulus, kind=int64)
         b = modulo(int(base, kind=int64), m)
         e = int(exp, kind=int64)
         res = 1_int64
         do while (e > 0_int64)
            if (modulo(e, 2_int64) == 1_int64) res = modulo(res * b, m)
            e = e / 2_int64
            if (e > 0_int64) b = modulo(b * b, m)
         end do
         mod_pow_int = int(res)
      end function mod_pow_int

      pure integer function factorial_int(x) result(v)
         integer, intent(in) :: x
         integer :: i
         if (x < 0) then
            v = 0
            return
         end if
         v = 1
         do i = 2, x
            v = v * i
         end do
      end function factorial_int

      pure integer function comb_int(n, k) result(v)
         integer, intent(in) :: n, k
         integer :: i, kk
         if (n < 0 .or. k < 0 .or. k > n) then
            v = 0
            return
         end if
         kk = min(k, n - k)
         v = 1
         if (kk <= 0) return
         do i = 1, kk
            v = (v * (n - kk + i)) / i
         end do
      end function comb_int

      pure integer function perm_int(n, k) result(v)
         integer, intent(in) :: n
         integer, intent(in), optional :: k
         integer :: i, kk
         if (present(k)) then
            kk = k
         else
            kk = n
         end if
         if (n < 0 .or. kk < 0 .or. kk > n) then
            v = 0
            return
         end if
         v = 1
         if (kk <= 0) return
         do i = n - kk + 1, n
            v = v * i
         end do
      end function perm_int

      pure elemental real(kind=dp) function special_factorial(x) result(v)
         real(kind=dp), intent(in) :: x
         if (x < 0.0_dp) then
            v = ieee_value(0.0_dp, ieee_quiet_nan)
         else
            v = gamma(x + 1.0_dp)
         end if
      end function special_factorial

      pure elemental real(kind=dp) function special_factorial2(x) result(v)
         real(kind=dp), intent(in) :: x
         integer :: n, i
         if (x < -1.0_dp) then
            v = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         n = nint(x)
         if (abs(x - real(n, kind=dp)) > 1.0e-12_dp) then
            v = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         if (n == -1 .or. n == 0) then
            v = 1.0_dp
            return
         end if
         if (n < -1) then
            v = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         v = 1.0_dp
         do i = n, 1, -2
            v = v * real(i, kind=dp)
         end do
      end function special_factorial2

      pure elemental real(kind=dp) function special_binom(n, k) result(v)
         real(kind=dp), intent(in) :: n, k
         integer :: ni, ki
         logical :: n_int, k_int
         if (k < 0.0_dp) then
            v = 0.0_dp
            return
         end if
         ni = nint(n)
         ki = nint(k)
         n_int = abs(n - real(ni, kind=dp)) <= 1.0e-12_dp
         k_int = abs(k - real(ki, kind=dp)) <= 1.0e-12_dp
         if (n_int .and. k_int) then
            if (ki < 0 .or. ni < 0 .or. ki > ni) then
               v = 0.0_dp
               return
            end if
            v = special_comb(real(ni, kind=dp), real(ki, kind=dp), exact=.true.)
            return
         end if
         v = gamma(n + 1.0_dp) / (gamma(k + 1.0_dp) * gamma(n - k + 1.0_dp))
      end function special_binom

      pure elemental real(kind=dp) function special_comb(n, k, exact, repetition) result(v)
         real(kind=dp), intent(in) :: n, k
         logical, intent(in), optional :: exact, repetition
         logical :: repetition_opt, exact_opt, n_int, k_int
         real(kind=dp) :: nn, kk
         integer :: ni, ki, i, kwork
         nn = n
         kk = k
         repetition_opt = .false.
         exact_opt = .false.
         if (present(repetition)) repetition_opt = repetition
         if (present(exact)) exact_opt = exact
         if (repetition_opt) then
            nn = n + k - 1.0_dp
         end if
         if (kk < 0.0_dp) then
            v = 0.0_dp
            return
         end if
         ni = nint(nn)
         ki = nint(kk)
         n_int = abs(nn - real(ni, kind=dp)) <= 1.0e-12_dp
         k_int = abs(kk - real(ki, kind=dp)) <= 1.0e-12_dp
         if (exact_opt) then
            if ((.not. n_int) .or. (.not. k_int)) then
               v = ieee_value(0.0_dp, ieee_quiet_nan)
               return
            end if
            if (ni < 0 .or. ki < 0 .or. ki > ni) then
               v = 0.0_dp
               return
            end if
            kwork = ki
            if (kwork > ni - kwork) kwork = ni - kwork
            v = 1.0_dp
            do i = 1, kwork
               v = v * real(ni - kwork + i, kind=dp) / real(i, kind=dp)
            end do
            return
         end if
         if (n_int .and. k_int) then
            if (ni < 0 .or. ki < 0 .or. ki > ni) then
               v = 0.0_dp
               return
            end if
         end if
         v = gamma(nn + 1.0_dp) / (gamma(kk + 1.0_dp) * gamma(nn - kk + 1.0_dp))
      end function special_comb

      subroutine print_int_list(a, n)
         ! print integer list a(1:n) in python-style [..] format
         implicit none
         integer, intent(in) :: a(:)  ! array containing values to print
         integer, intent(in) :: n     ! number of elements from a to print
         integer :: j
         if (n <= 0) then
            write(*,'(a)') '[]'
            return
         end if
         write(*,'(a)', advance='no') '['
         do j = 1, n
            if (j > 1) write(*,'(a)', advance='no') ', '
            write(*,'(i0)', advance='no') a(j)
         end do
         write(*,'(a)') ']'
      end subroutine print_int_list

      subroutine print_char_list(a, n)
         ! print character list a(1:n) in python-style ['..', ...] format
         implicit none
         character(len=*), intent(in) :: a(:)  ! array containing values to print
         integer, intent(in) :: n               ! number of elements from a to print
         integer :: j
         if (n <= 0) then
            write(*,'(a)') '[]'
            return
         end if
         write(*,'(a)', advance='no') '['
         do j = 1, n
            if (j > 1) write(*,'(a)', advance='no') ', '
            write(*,'(a)', advance='no') "'" // trim(a(j)) // "'"
         end do
         write(*,'(a)') ']'
      end subroutine print_char_list

      pure subroutine grow_and_set_char(arr, idx, item)
         ! grow allocatable character list arr to fit index idx and item's
         ! length, then set arr(idx) = item -- the shared "list.append()"
         ! growth machinery previously inlined at every append call site.
         implicit none
         character(len=:), allocatable, intent(inout) :: arr(:)  ! growable character list
         integer, intent(in) :: idx                              ! 1-based target index (== new length after an append)
         character(len=*), intent(in) :: item                    ! value to store at arr(idx)
         integer :: len_new
         if (.not. allocated(arr)) allocate(character(len=1) :: arr(1))
         if (idx > size(arr) .or. len(item) > len(arr)) then
            len_new = max(len(arr), len(item))
            if (idx > size(arr)) then
               arr = [character(len=len_new) :: arr, item]
            else
               arr = [character(len=len_new) :: arr]
            end if
         end if
         arr(idx) = item
      end subroutine grow_and_set_char

      pure subroutine insert_char(arr, idx, item)
         ! insert item into allocatable character list arr at Python-style
         ! index idx (negative counts from the end, out-of-range clamps to
         ! the nearer end), widening arr's declared length if item is
         ! longer than its current elements -- the shared "list.insert()"
         ! machinery previously inlined at every insert call site.
         implicit none
         character(len=:), allocatable, intent(inout) :: arr(:)  ! growable character list
         integer, intent(in) :: idx                              ! Python-style insertion index
         character(len=*), intent(in) :: item                    ! value to insert
         integer :: n_ins, pos_ins, len_new
         if (.not. allocated(arr)) allocate(character(len=1) :: arr(0))
         n_ins = size(arr)
         pos_ins = idx
         if (pos_ins < 0) pos_ins = n_ins + pos_ins
         if (pos_ins < 0) pos_ins = 0
         if (pos_ins > n_ins) pos_ins = n_ins
         len_new = max(len(arr), len(item))
         arr = [character(len=len_new) :: arr(:pos_ins), item, arr(pos_ins + 1:)]
      end subroutine insert_char

      subroutine print_real_list(a, n)
         ! print real list a(1:n) in python-style [..] format
         implicit none
         real(kind=dp), intent(in) :: a(:)  ! array containing values to print
         integer, intent(in) :: n            ! number of elements from a to print
         integer :: j
         if (n <= 0) then
            write(*,'(a)') '[]'
            return
         end if
         write(*,'(a)', advance='no') '['
         do j = 1, n
            if (j > 1) write(*,'(a)', advance='no') ', '
            write(*,'(a)', advance='no') trim(py_str(a(j)))
         end do
         write(*,'(a)') ']'
      end subroutine print_real_list

      subroutine print_log_list(a, n)
         ! print logical list a(1:n) in python-style [..] format
         implicit none
         logical, intent(in) :: a(:)  ! array containing values to print
         integer, intent(in) :: n      ! number of elements from a to print
         integer :: j
         if (n <= 0) then
            write(*,'(a)') '[]'
            return
         end if
         write(*,'(a)', advance='no') '['
         do j = 1, n
            if (j > 1) write(*,'(a)', advance='no') ', '
            write(*,'(a)', advance='no') trim(py_str(a(j)))
         end do
         write(*,'(a)') ']'
      end subroutine print_log_list

      function str_int_list(a, n) result(s)
         ! return integer list a(1:n) in python-style [..] format
         implicit none
         integer, intent(in) :: a(:)
         integer, intent(in) :: n
         character(len=:), allocatable :: s
         integer :: j
         if (n <= 0) then
            s = '[]'
            return
         end if
         s = '['
         do j = 1, n
            if (j > 1) s = s // ', '
            s = s // py_str(a(j))
         end do
         s = s // ']'
      end function str_int_list

      subroutine print_matrix_real_2d(a)
         real(kind=dp), intent(in) :: a(:,:)
         integer :: i, j, pad, w
         character(len=64) :: buf

         if (size(a,1) <= 0 .or. size(a,2) <= 0) then
            write(*, "(a)") "[]"
            return
         end if

         w = 1
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               write(buf, "(g0)") a(i, j)
               w = max(w, len_trim(adjustl(buf)))
            end do
         end do

         do i = 1, size(a,1)
            if (size(a,1) == 1) then
               write(*, "(a)", advance="no") "[["
            else if (i == 1) then
               write(*, "(a)", advance="no") "[["
            else
               write(*, "(a)", advance="no") " ["
            end if
            do j = 1, size(a,2)
               if (j > 1) write(*, "(a)", advance="no") " "
               write(buf, "(g0)") a(i, j)
               buf = adjustl(buf)
               pad = w - len_trim(buf)
               if (pad > 0) write(*, "(a)", advance="no") repeat(" ", pad)
               write(*, "(a)", advance="no") trim(buf)
            end do
            if (size(a,1) == 1 .or. i == size(a,1)) then
               write(*, "(a)") "]]"
            else
               write(*, "(a)") "]"
            end if
         end do
      end subroutine print_matrix_real_2d

      subroutine print_matrix_int_2d(a)
         integer, intent(in) :: a(:,:)
         integer :: i, j, pad, w
         character(len=64) :: buf

         if (size(a,1) <= 0 .or. size(a,2) <= 0) then
            write(*, "(a)") "[]"
            return
         end if

         w = 1
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               write(buf, "(i0)") a(i, j)
               w = max(w, len_trim(adjustl(buf)))
            end do
         end do

         do i = 1, size(a,1)
            if (size(a,1) == 1) then
               write(*, "(a)", advance="no") "[["
            else if (i == 1) then
               write(*, "(a)", advance="no") "[["
            else
               write(*, "(a)", advance="no") " ["
            end if
            do j = 1, size(a,2)
               if (j > 1) write(*, "(a)", advance="no") " "
               write(buf, "(i0)") a(i, j)
               buf = adjustl(buf)
               pad = w - len_trim(buf)
               if (pad > 0) write(*, "(a)", advance="no") repeat(" ", pad)
               write(*, "(a)", advance="no") trim(buf)
            end do
            if (size(a,1) == 1 .or. i == size(a,1)) then
               write(*, "(a)") "]]"
            else
               write(*, "(a)") "]"
            end if
         end do
      end subroutine print_matrix_int_2d

      subroutine print_matrix_complex_2d(a)
         ! A 2-D complex array row by row, each element as (re,im).
         complex(kind=dp), intent(in) :: a(:,:)
         integer :: i, j
         character(len=80) :: buf
         if (size(a,1) <= 0 .or. size(a,2) <= 0) then
            write(*, "(a)") "[]"
            return
         end if
         do i = 1, size(a,1)
            if (i == 1) then
               write(*, "(a)", advance="no") "[["
            else
               write(*, "(a)", advance="no") " ["
            end if
            do j = 1, size(a,2)
               if (j > 1) write(*, "(a)", advance="no") " "
               write(buf, "(a,g0,a,g0,a)") "(", real(a(i,j)), ",", aimag(a(i,j)), ")"
               write(*, "(a)", advance="no") trim(buf)
            end do
            if (i == size(a,1)) then
               write(*, "(a)") "]]"
            else
               write(*, "(a)") "]"
            end if
         end do
      end subroutine print_matrix_complex_2d

      subroutine print_matrix_logical_2d(a)
         ! A 2-D logical array in NumPy's layout: rows in order, each
         ! element right-justified in 5 columns (`[[ True False  True]`).
         logical, intent(in) :: a(:,:)
         integer :: i, j

         if (size(a,1) <= 0 .or. size(a,2) <= 0) then
            write(*, "(a)") "[]"
            return
         end if
         do i = 1, size(a,1)
            if (i == 1) then
               write(*, "(a)", advance="no") "["
            else
               write(*, "(a)", advance="no") " "
            end if
            write(*, "(a)", advance="no") "["
            do j = 1, size(a,2)
               if (j > 1) write(*, "(a)", advance="no") " "
               if (a(i, j)) then
                  write(*, "(a)", advance="no") " True"
               else
                  write(*, "(a)", advance="no") "False"
               end if
            end do
            if (i == size(a,1)) then
               write(*, "(a)") "]]"
            else
               write(*, "(a)") "]"
            end if
         end do
      end subroutine print_matrix_logical_2d

      subroutine print_array_3d_real(a)
         real(kind=dp), intent(in) :: a(:,:,:)
         integer :: i, j, k, pad, w
         character(len=64) :: buf

         if (size(a,1) <= 0 .or. size(a,2) <= 0 .or. size(a,3) <= 0) then
            write(*, "(a)") "[]"
            return
         end if

         w = 1
         do k = 1, size(a,3)
            do j = 1, size(a,2)
               do i = 1, size(a,1)
                  write(buf, "(g0)") a(i, j, k)
                  w = max(w, len_trim(adjustl(buf)))
               end do
            end do
         end do

         do i = 1, size(a,1)
            do j = 1, size(a,2)
               if (i == 1 .and. j == 1) then
                  write(*, "(a)", advance="no") "[[["
               else if (j == 1) then
                  write(*, "(a)", advance="no") " [["
               else
                  write(*, "(a)", advance="no") "  ["
               end if
               do k = 1, size(a,3)
                  if (k > 1) write(*, "(a)", advance="no") " "
                  write(buf, "(g0)") a(i, j, k)
                  buf = adjustl(buf)
                  pad = w - len_trim(buf)
                  if (pad > 0) write(*, "(a)", advance="no") repeat(" ", pad)
                  write(*, "(a)", advance="no") trim(buf)
               end do
               if (i == size(a,1) .and. j == size(a,2)) then
                  write(*, "(a)") "]]]"
               else if (j == size(a,2)) then
                  write(*, "(a)") "]]"
               else
                  write(*, "(a)") "]"
               end if
            end do
            if (i < size(a,1)) write(*, "(a)") ""
         end do
      end subroutine print_array_3d_real

      subroutine print_array_3d_int(a)
         integer, intent(in) :: a(:,:,:)
         integer :: i, j, k, pad, w
         character(len=64) :: buf

         if (size(a,1) <= 0 .or. size(a,2) <= 0 .or. size(a,3) <= 0) then
            write(*, "(a)") "[]"
            return
         end if

         w = 1
         do k = 1, size(a,3)
            do j = 1, size(a,2)
               do i = 1, size(a,1)
                  write(buf, "(i0)") a(i, j, k)
                  w = max(w, len_trim(adjustl(buf)))
               end do
            end do
         end do

         do i = 1, size(a,1)
            do j = 1, size(a,2)
               if (i == 1 .and. j == 1) then
                  write(*, "(a)", advance="no") "[[["
               else if (j == 1) then
                  write(*, "(a)", advance="no") " [["
               else
                  write(*, "(a)", advance="no") "  ["
               end if
               do k = 1, size(a,3)
                  if (k > 1) write(*, "(a)", advance="no") " "
                  write(buf, "(i0)") a(i, j, k)
                  buf = adjustl(buf)
                  pad = w - len_trim(buf)
                  if (pad > 0) write(*, "(a)", advance="no") repeat(" ", pad)
                  write(*, "(a)", advance="no") trim(buf)
               end do
               if (i == size(a,1) .and. j == size(a,2)) then
                  write(*, "(a)") "]]]"
               else if (j == size(a,2)) then
                  write(*, "(a)") "]]"
               else
                  write(*, "(a)") "]"
               end if
            end do
            if (i < size(a,1)) write(*, "(a)") ""
         end do
      end subroutine print_array_3d_int

      subroutine print_array_3d_logical(a)
         logical, intent(in) :: a(:,:,:)
         integer :: i, j, k, pad, w
         character(len=64) :: buf

         if (size(a,1) <= 0 .or. size(a,2) <= 0 .or. size(a,3) <= 0) then
            write(*, "(a)") "[]"
            return
         end if

         w = 1
         do k = 1, size(a,3)
            do j = 1, size(a,2)
               do i = 1, size(a,1)
                  buf = merge("True ", "False", a(i, j, k))
                  w = max(w, len_trim(adjustl(buf)))
               end do
            end do
         end do

         do i = 1, size(a,1)
            do j = 1, size(a,2)
               if (i == 1 .and. j == 1) then
                  write(*, "(a)", advance="no") "[[["
               else if (j == 1) then
                  write(*, "(a)", advance="no") " [["
               else
                  write(*, "(a)", advance="no") "  ["
               end if
               do k = 1, size(a,3)
                  if (k > 1) write(*, "(a)", advance="no") " "
                  buf = merge("True ", "False", a(i, j, k))
                  buf = adjustl(buf)
                  pad = w - len_trim(buf)
                  if (pad > 0) write(*, "(a)", advance="no") repeat(" ", pad)
                  write(*, "(a)", advance="no") trim(buf)
               end do
               if (i == size(a,1) .and. j == size(a,2)) then
                  write(*, "(a)") "]]]"
               else if (j == size(a,2)) then
                  write(*, "(a)") "]]"
               else
                  write(*, "(a)") "]"
               end if
            end do
            if (i < size(a,1)) write(*, "(a)") ""
         end do
      end subroutine print_array_3d_logical

      subroutine print_array_3d_label_real(label, a)
         character(len=*), intent(in) :: label
         real(kind=dp), intent(in) :: a(:,:,:)
         write(*, "(a)") trim(label)
         call print_array_3d_real(a)
      end subroutine print_array_3d_label_real

      subroutine print_array_3d_label_int(label, a)
         character(len=*), intent(in) :: label
         integer, intent(in) :: a(:,:,:)
         write(*, "(a)") trim(label)
         call print_array_3d_int(a)
      end subroutine print_array_3d_label_int

      pure real(kind=dp) function index1_real(x, i)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: i
         index1_real = x(i)
      end function index1_real

      pure integer function index1_int(x, i)
         integer, intent(in) :: x(:)
         integer, intent(in) :: i
         index1_int = x(i)
      end function index1_int

      pure logical function index1_logical(x, i)
         logical, intent(in) :: x(:)
         integer, intent(in) :: i
         index1_logical = x(i)
      end function index1_logical

      pure complex(kind=dp) function index1_complex(x, i)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: i
         index1_complex = x(i)
      end function index1_complex

      pure function index1_char(x, i) result(v)
         character(len=*), intent(in) :: x(:)
         integer, intent(in) :: i
         character(len=len(x(i))) :: v
         v = x(i)
      end function index1_char

      pure real(kind=dp) function index2_real(x, i, j)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: i, j
         index2_real = x(i, j)
      end function index2_real

      pure integer function index2_int(x, i, j)
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: i, j
         index2_int = x(i, j)
      end function index2_int

      pure logical function index2_logical(x, i, j)
         logical, intent(in) :: x(:,:)
         integer, intent(in) :: i, j
         index2_logical = x(i, j)
      end function index2_logical

      pure complex(kind=dp) function index2_complex(x, i, j)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: i, j
         index2_complex = x(i, j)
      end function index2_complex

      pure function index2_char(x, i, j) result(v)
         character(len=*), intent(in) :: x(:,:)
         integer, intent(in) :: i, j
         character(len=len(x(i, j))) :: v
         v = x(i, j)
      end function index2_char

      pure elemental integer function py_slice_bound(index, n, reverse) result(bound)
         ! Normalize an explicit Python slice index, still zero-based.
         integer, intent(in) :: index, n
         logical, intent(in) :: reverse
         bound = index
         if (bound < 0) bound = n + bound
         if (reverse) then
            bound = max(-1, min(n - 1, bound))
         else
            bound = max(0, min(n, bound))
         end if
      end function py_slice_bound

      pure function slice1_real(x, lo, hi, step) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: lo, hi, step
         real(kind=dp), allocatable :: y(:)
         y = x(lo:hi:step)
      end function slice1_real

      pure function slice1_int(x, lo, hi, step) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: lo, hi, step
         integer, allocatable :: y(:)
         y = x(lo:hi:step)
      end function slice1_int

      pure function slice1_logical(x, lo, hi, step) result(y)
         logical, intent(in) :: x(:)
         integer, intent(in) :: lo, hi, step
         logical, allocatable :: y(:)
         y = x(lo:hi:step)
      end function slice1_logical

      pure function slice1_complex(x, lo, hi, step) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: lo, hi, step
         complex(kind=dp), allocatable :: y(:)
         y = x(lo:hi:step)
      end function slice1_complex

      pure function slice1_char(x, lo, hi, step) result(y)
         character(len=*), intent(in) :: x(:)
         integer, intent(in) :: lo, hi, step
         character(len=len(x)), allocatable :: y(:)
         y = x(lo:hi:step)
      end function slice1_char

      pure function digits_of_str(s) result(digits)
         character(len=*), intent(in) :: s
         integer, allocatable :: digits(:)
         character(len=:), allocatable :: t
         integer :: i, n
         t = trim(s)
         n = len(t)
         allocate(digits(n))
         do i = 1, n
            if (t(i:i) >= "0" .and. t(i:i) <= "9") then
               digits(i) = iachar(t(i:i)) - iachar("0")
            else
               digits(i) = 0
            end if
         end do
      end function digits_of_str

      subroutine print_matrix_label_real_2d(label, a)
         character(len=*), intent(in) :: label
         real(kind=dp), intent(in) :: a(:,:)
         write(*, "(a)") trim(label)
         call print_matrix_real_2d(a)
      end subroutine print_matrix_label_real_2d

      subroutine print_matrix_label_int_2d(label, a)
         character(len=*), intent(in) :: label
         integer, intent(in) :: a(:,:)
         write(*, "(a)") trim(label)
         call print_matrix_int_2d(a)
      end subroutine print_matrix_label_int_2d

      pure function py_str_int32(x) result(s)
         integer, intent(in) :: x
         character(len=:), allocatable :: s
         character(len=64) :: buf
         write(buf, "(i0)") x
         s = trim(adjustl(buf))
      end function py_str_int32

      pure function py_str_int64(x) result(s)
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: iso_fortran_env, only: int64
         integer(kind=int64), intent(in) :: x
         character(len=:), allocatable :: s
         character(len=64) :: buf
         write(buf, "(i0)") x
         s = trim(adjustl(buf))
      end function py_str_int64

      elemental function narrow_int_i32(x) result(y)
         integer, intent(in) :: x
         integer :: y
         y = x
      end function narrow_int_i32

      elemental function narrow_int_i64(x) result(y)
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: iso_fortran_env, only: int64
         integer(kind=int64), intent(in) :: x
         integer :: y
         if (x > int(huge(y), int64) .or. x < -int(huge(y), int64) - 1_int64) &
            error stop "narrow_int: integer value out of the default integer range"
         y = int(x)
      end function narrow_int_i64

      pure function py_str_real(x) result(s)
         real(kind=dp), intent(in) :: x
         character(len=:), allocatable :: s
         character(len=128) :: buf
         write(buf, "(g0)") x
         s = trim(adjustl(buf))
      end function py_str_real

      function py_format_g_real(x) result(s)
         real(kind=dp), intent(in) :: x
         character(len=:), allocatable :: s
         character(len=128) :: buf
         real(kind=dp) :: xr
         integer :: p
         xr = anint(x)
         if (abs(x - xr) <= 10.0_dp * epsilon(x) * max(1.0_dp, abs(x)) .and. abs(xr) <= real(huge(0), kind=dp)) then
            write(buf, "(i0)") int(xr)
            s = trim(adjustl(buf))
            return
         end if
         write(buf, "(g0)") x
         s = trim(adjustl(buf))
         p = index(s, ".")
         if (index(s, "e") == 0 .and. index(s, "E") == 0 .and. p > 0) then
            do while (len(s) > p .and. s(len(s):len(s)) == "0")
               s = s(:len(s)-1)
            end do
            if (len(s) >= p .and. s(len(s):len(s)) == ".") then
               s = s(:len(s)-1)
            end if
         end if
      end function py_format_g_real

      function py_format_real(x, prec, width, flags, code) result(s)
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_is_nan
         real(kind=dp), intent(in) :: x
         integer, intent(in) :: prec, width
         character(len=*), intent(in) :: flags, code
         character(len=:), allocatable :: s, buf, digits, prefix, exponent_text
         character(len=64) :: fmt, eb
         integer :: p, e, pos, dot, n, cut
         logical :: alternate, upper, scientific, fixed
         upper = code == 'G' .or. code == 'E' .or. code == 'F'
         scientific = code == 'e' .or. code == 'E'
         fixed = code == 'f' .or. code == 'F'
         p = max(1, prec)
         if (scientific) p = max(0, prec) + 1
         alternate = index(flags, '#') > 0
         prefix = ''
         if (sign(1.0_dp, x) < 0.0_dp .and. .not. ieee_is_nan(x)) then
            prefix = '-'
         else if (index(flags, '+') > 0) then
            prefix = '+'
         else if (index(flags, ' ') > 0) then
            prefix = ' '
         end if
         if (.not. ieee_is_finite(x)) then
            if (ieee_is_nan(x)) then
               s = 'nan'
               if (upper) s = 'NAN'
            else
               s = 'inf'
               if (upper) s = 'INF'
            end if
         else if (fixed) then
            ! Python's field width is a minimum, not an overflow boundary.
            ! Allow the largest finite DP value plus the requested fraction.
            p = max(0, prec)
            n = range(x) + p + 16
            allocate(character(len=n) :: buf)
            write(fmt, '("(f0.",i0,")")') p
            write(buf, fmt) abs(x)
            s = trim(adjustl(buf))
            if (s(:1) == '.') s = '0' // s
            if (p == 0 .and. .not. alternate) then
               if (s(len(s):) == '.') s = s(:len(s)-1)
            end if
         else
            ! Round once to P significant digits before choosing notation.
            ! A generous internal field avoids output overflow, including
            ! subnormals and exponents with three decimal digits.
            n = p + 16
            allocate(character(len=n) :: buf)
            write(fmt, '("(es",i0,".",i0,"e4)")') n, p - 1
            write(buf, fmt) abs(x)
            buf = trim(adjustl(buf))
            pos = index(buf, 'E')
            read(buf(pos+1:), *) e
            digits = buf(:pos-1)
            dot = index(digits, '.')
            if (dot > 0) digits = digits(:dot-1) // digits(dot+1:)
            if (scientific .or. e < -4 .or. e >= p) then
               s = digits(:1)
               if (p > 1 .or. alternate) s = s // '.' // digits(2:)
            else
               cut = e + 1
               if (cut <= 0) then
                  s = '0.' // repeat('0', -cut) // digits
               else if (cut >= len(digits)) then
                  s = digits // repeat('0', cut-len(digits))
                  if (alternate) s = s // '.'
               else
                  s = digits(:cut) // '.' // digits(cut+1:)
               end if
            end if
            if (.not. scientific .and. .not. alternate .and. index(s, '.') > 0) then
               do while (len(s) > 0)
                  if (s(len(s):) /= '0') exit
                  s = s(:len(s)-1)
               end do
               if (s(len(s):) == '.') s = s(:len(s)-1)
            end if
            if (scientific .or. e < -4 .or. e >= p) then
               write(eb, '(i0.2)') abs(e)
               exponent_text = 'e'
               if (upper) exponent_text = 'E'
               if (e < 0) then
                  exponent_text = exponent_text // '-'
               else
                  exponent_text = exponent_text // '+'
               end if
               s = s // exponent_text // trim(eb)
            end if
         end if
         n = max(0, width - len(prefix) - len(s))
         if (index(flags, '-') > 0) then
            s = prefix // s // repeat(' ', n)
         else if (index(flags, '0') > 0) then
            s = prefix // repeat('0', n) // s
         else
            s = repeat(' ', n) // prefix // s
         end if
      end function py_format_real

      pure function py_format_int32(x, width, flags, code) result(s)
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: iso_fortran_env, only: int64
         integer, intent(in) :: x, width
         character(len=*), intent(in) :: flags, code
         character(len=:), allocatable :: s
         s = py_format_int64(int(x, int64), width, flags, code)
      end function py_format_int32

      pure function py_format_int64(x, width, flags, code) result(s)
         ! Python "%<flags><width><code>" for code d, i, u, o, x or X: the
         ! width is a minimum, never an overflow boundary (a Fortran iW
         ! descriptor prints asterisks), and o/x/X are signed magnitudes
         ! ('%x' % -255 is '-ff'), not Fortran's two's-complement O/Z output.
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: iso_fortran_env, only: int64
         integer(kind=int64), intent(in) :: x
         integer, intent(in) :: width
         character(len=*), intent(in) :: flags, code
         character(len=:), allocatable :: s, prefix
         character(len=*), parameter :: digits = '0123456789abcdef'
         integer(kind=int64) :: v, base
         integer :: n, d
         base = 10
         if (code == 'o') base = 8
         if (code == 'x' .or. code == 'X') base = 16
         ! abs(-huge(x)-1) overflows; take the magnitude digit by digit.
         v = x
         s = ''
         do
            d = abs(int(mod(v, base)))  ! mod keeps the sign of a negative v
            s = digits(d+1:d+1) // s
            v = v / base
            if (v == 0) exit
         end do
         if (code == 'X') then
            do n = 1, len(s)
               d = index('abcdef', s(n:n))
               if (d > 0) s(n:n) = 'ABCDEF'(d:d)
            end do
         end if
         if (x < 0) then
            prefix = '-'
         else if (index(flags, '+') > 0) then
            prefix = '+'
         else if (index(flags, ' ') > 0) then
            prefix = ' '
         else
            prefix = ''
         end if
         if (index(flags, '#') > 0 .and. base /= 10) then
            if (code == 'o') then
               prefix = prefix // '0o'
            else
               prefix = prefix // '0' // code
            end if
         end if
         n = max(0, width - len(prefix) - len(s))
         if (index(flags, '-') > 0) then
            s = prefix // s // repeat(' ', n)
         else if (index(flags, '0') > 0) then
            s = prefix // repeat('0', n) // s
         else
            s = repeat(' ', n) // prefix // s
         end if
      end function py_format_int64

      pure function str_format_real_fixed(x, prec) result(s)
         real(kind=dp), intent(in) :: x
         integer, intent(in) :: prec
         character(len=:), allocatable :: s
         character(len=32) :: fmt
         character(len=128) :: buf
         integer :: p
         p = max(0, prec)
         write(fmt, '("(f0.",i0,")")') p
         write(buf, fmt) x
         s = trim(adjustl(buf))
      end function str_format_real_fixed

      pure function str_format_real_sci(x, prec) result(s)
         real(kind=dp), intent(in) :: x
         integer, intent(in) :: prec
         character(len=:), allocatable :: s
         character(len=32) :: fmt
         character(len=128) :: buf
         integer :: p, i, epos
         p = max(0, prec)
         ! gfortran's own ES exponent field always uses a FIXED 3 digits
         ! for real(dp) (e.g. E+008), regardless of the value's actual
         ! magnitude. Python's `.Ne` spec uses a 2-digit MINIMUM,
         ! expanding only when the magnitude genuinely needs a 3rd digit
         ! (e.g. 1e-100 is still shown as e-100 in Python too). Forcing a
         ! fixed 2-digit exponent width via an explicit `E2` format
         ! descriptor suffix does NOT reproduce this -- it hard-overflows
         ! to a field of asterisks for any exponent that actually needs a
         ! 3rd digit, which is worse than gfortran's own always-3-digit
         ! default. Instead, let gfortran pick its own (always-3-digit)
         ! width, then strip exactly one redundant leading zero from the
         ! exponent digits when present -- this reproduces Python's
         ! variable-width behavior exactly, with no overflow risk at any
         ! magnitude.
         write(fmt, '("(ES0.",i0,")")') p
         write(buf, fmt) x
         s = trim(adjustl(buf))
         if (p == 0) then
            ! Python's `.0e` spec omits the decimal point entirely
            ! (e.g. "1e+08"); Fortran's ES format always keeps a
            ! trailing "." even with zero decimal digits (e.g. "1.E+08").
            epos = index(s, '.')
            if (epos > 0) s = s(1:epos-1) // s(epos+1:)
         end if
         epos = index(s, 'E')
         if (epos > 0 .and. epos + 2 <= len(s)) then
            if (s(epos+2:epos+2) == '0') then
               s = s(1:epos+1) // s(epos+3:)
            end if
         end if
         do i = 1, len(s)
            if (s(i:i) == 'E') s(i:i) = 'e'
         end do
      end function str_format_real_sci

      pure function py_str_logical(x) result(s)
         logical, intent(in) :: x
         character(len=:), allocatable :: s
         if (x) then
            s = "True"
         else
            s = "False"
         end if
      end function py_str_logical

      pure function py_str_char(x) result(s)
         character(len=*), intent(in) :: x
         character(len=:), allocatable :: s
         s = x
      end function py_str_char

      function py_str_int_vec(x) result(s)
         integer, intent(in) :: x(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=64) :: s(size(x)))
         do i = 1, size(x)
            s(i) = py_str_int(x(i))
         end do
      end function py_str_int_vec

      function py_str_int64_vec(x) result(s)
         ! Keep intrinsic dependencies local when xpfunc2f extracts this helper.
         use, intrinsic :: iso_fortran_env, only: int64
         integer(kind=int64), intent(in) :: x(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=64) :: s(size(x)))
         do i = 1, size(x)
            s(i) = py_str_int(x(i))
         end do
      end function py_str_int64_vec

      function py_str_real_vec(x) result(s)
         real(kind=dp), intent(in) :: x(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=128) :: s(size(x)))
         do i = 1, size(x)
            s(i) = py_str_real(x(i))
         end do
      end function py_str_real_vec

      function py_str_logical_vec(x) result(s)
         logical, intent(in) :: x(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=5) :: s(size(x)))
         do i = 1, size(x)
            s(i) = py_str_logical(x(i))
         end do
      end function py_str_logical_vec

      function py_str_char_vec(x) result(s)
         character(len=*), intent(in) :: x(:)
         character(len=:), allocatable :: s(:)
         allocate(character(len=len(x)) :: s(size(x)))
         s = x
      end function py_str_char_vec

      pure function str_concat_ss(a, b) result(s)
         character(len=*), intent(in) :: a, b
         character(len=:), allocatable :: s
         s = a // b
      end function str_concat_ss

      pure function str_concat_sv(a, b) result(s)
         character(len=*), intent(in) :: a
         character(len=*), intent(in) :: b(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         ! b's own elements are typically produced by a fixed-length
         ! elemental helper (e.g. py_str_int_vec), so each one carries
         ! trailing blank padding out to its full declared length --
         ! trim it first, or that padding lands in the MIDDLE of the
         ! concatenated result instead of at the end.
         allocate(character(len=len(a) + len(b)) :: s(size(b)))
         do i = 1, size(b)
            s(i) = a // trim(b(i))
         end do
      end function str_concat_sv

      pure function str_concat_vs(a, b) result(s)
         character(len=*), intent(in) :: a(:)
         character(len=*), intent(in) :: b
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=len(a) + len(b)) :: s(size(a)))
         do i = 1, size(a)
            s(i) = trim(a(i)) // b
         end do
      end function str_concat_vs

      pure function str_concat_vv(a, b) result(s)
         character(len=*), intent(in) :: a(:), b(:)
         character(len=:), allocatable :: s(:)
         integer :: i
         allocate(character(len=len(a) + len(b)) :: s(min(size(a), size(b))))
         do i = 1, size(s)
            s(i) = trim(a(i)) // trim(b(i))
         end do
      end function str_concat_vv

      subroutine seed_rng(seed)
         integer, intent(in), optional :: seed
         integer :: nseed_rng, i_rng, s0
         integer, allocatable :: seed_buf(:)
         if (.not. present(seed)) then
            call random_seed()
            return
         end if
         s0 = seed
         call random_seed(size=nseed_rng)
         allocate(seed_buf(nseed_rng))
         do i_rng = 1, nseed_rng
            ! In 64 bits and reduced, so a seed near huge(0) cannot overflow (-ftrapv).
            seed_buf(i_rng) = int(modulo(int(s0, int64) + 104729_int64 * (i_rng - 1), int(huge(0), int64)))
         end do
         call random_seed(put=seed_buf)
         deallocate(seed_buf)
      end subroutine seed_rng

      function py_time() result(t)
         real(kind=dp) :: t
         integer :: count, rate
         call system_clock(count, rate)
         if (rate > 0) then
            t = real(count, kind=dp) / real(rate, kind=dp)
         else
            t = 0.0_dp
         end if
      end function py_time

      ! OpenMP runtime routines for pyccel-style code (from pyccel.stdlib.
      ! internal.openmp import omp_get_thread_num, ...). The `!$ ` lines are
      ! compiled only with -fopenmp; otherwise these return what pyccel's
      ! pure-Python versions do (thread 0 of a team of 1).
      function py_omp_get_thread_num() result(r)
         !$ use omp_lib, only: omp_get_thread_num
         integer :: r
         r = 0
         !$ r = omp_get_thread_num()
      end function py_omp_get_thread_num

      function py_omp_get_num_threads() result(r)
         !$ use omp_lib, only: omp_get_num_threads
         integer :: r
         r = 1
         !$ r = omp_get_num_threads()
      end function py_omp_get_num_threads

      function py_omp_get_max_threads() result(r)
         !$ use omp_lib, only: omp_get_max_threads
         integer :: r
         r = 1
         !$ r = omp_get_max_threads()
      end function py_omp_get_max_threads

      subroutine py_omp_set_num_threads(n)
         !$ use omp_lib, only: omp_set_num_threads
         integer, intent(in) :: n
         !$ call omp_set_num_threads(n)
         if (n < 0) continue  ! n is unused without -fopenmp
      end subroutine py_omp_set_num_threads

      function py_ctime(t) result(s)
         real(kind=dp), intent(in), optional :: t
         character(len=:), allocatable :: s
         integer :: vals(8)
         character(len=32) :: buf
         call date_and_time(values=vals)
         if (present(t)) then
            write(buf, '(a,i0,a,i4.4,a,i2.2,a,i2.2,a,i2.2,a,i2.2,a,i2.2,a)') &
               't=', int(t), ' [', vals(1), '-', vals(2), '-', vals(3), ' ', vals(5), ':', vals(6), ':', vals(7), ']'
         else
            write(buf, '(i4.4,a,i2.2,a,i2.2,a,i2.2,a,i2.2,a,i2.2)') &
               vals(1), '-', vals(2), '-', vals(3), ' ', vals(5), ':', vals(6), ':', vals(7)
         end if
         s = trim(buf)
      end function py_ctime

      function loadtxt_real_2d(path, skiprows, max_rows, skip_footer, delimiter, comments, usecols) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows
         integer, intent(in), optional :: max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         integer, intent(in), optional :: usecols(:)
         real(kind=dp), allocatable :: x(:,:)
         integer :: u, ios, nskip, nrow, ncol, irow, i, ntok, j
         integer :: i1, i2, max_col0
         integer :: max_rows_loc, skip_footer_loc, nvalid, nkeep
         integer :: valid_seen
         character(len=4096) :: line, work, delim_txt, comm_txt, open_message
         real(kind=dp), allocatable :: vals(:)
         logical :: usecols_present

         nskip = optval(skiprows, 0)
         max_rows_loc = optval(max_rows, huge(1))
         skip_footer_loc = max(0, optval(skip_footer, 0))
         delim_txt = ""
         comm_txt = "#"
         if (present(delimiter)) delim_txt = delimiter
         if (present(comments)) comm_txt = comments
         usecols_present = present(usecols)
         max_col0 = -1
         if (usecols_present) then
            ncol = size(usecols)
            if (ncol <= 0) then
               allocate(x(0,0))
               return
            end if
            max_col0 = maxval(usecols)
         end if

         open(newunit=u, file=trim(path), status="old", action="read", iostat=ios, iomsg=open_message)
         if (ios /= 0) then
            error stop 'loadtxt: cannot open "' // trim(path) // '": ' // trim(open_message)
         end if
         do i = 1, nskip
            read(u, "(A)", iostat=ios) line
            if (ios /= 0) exit
         end do

         nrow = 0
          nvalid = 0
         if (.not. usecols_present) ncol = 0
         do
            read(u, "(A)", iostat=ios) line
            if (ios /= 0) exit
            work = preprocess_line(line, delim_txt, comm_txt)
            if (len_trim(work) == 0) cycle
            ntok = count_tokens(work)
            if (ntok <= 0) cycle
            if (usecols_present) then
               if (max_col0 + 1 > ntok) cycle
            else
               if (ncol == 0) ncol = ntok
            end if
            nvalid = nvalid + 1
         end do

         nkeep = max(0, nvalid - skip_footer_loc)
         nrow = min(nkeep, max(0, max_rows_loc))
         if (nrow <= 0 .or. ncol <= 0) then
            close(u)
            allocate(x(0,0))
            return
         end if

         rewind(u)
         do i = 1, nskip
            read(u, "(A)", iostat=ios) line
            if (ios /= 0) exit
         end do

         allocate(x(nrow, ncol))
         irow = 0
         valid_seen = 0
         do
            read(u, "(A)", iostat=ios) line
            if (ios /= 0) exit
            work = preprocess_line(line, delim_txt, comm_txt)
            if (len_trim(work) == 0) cycle
            ntok = count_tokens(work)
            if (ntok <= 0) cycle
            if (usecols_present) then
               if (max_col0 + 1 > ntok) cycle
            end if
            valid_seen = valid_seen + 1
            if (valid_seen > nkeep) exit
            if (irow >= nrow) exit
            irow = irow + 1
            allocate(vals(max(1, ntok)))
            vals = 0.0_dp
            read(work, *, iostat=ios) vals(1:ntok)
            if (ios /= 0) then
               x(irow, :) = 0.0_dp
            else
               if (usecols_present) then
                  do j = 1, ncol
                     i1 = usecols(j) + 1
                     if (i1 >= 1 .and. i1 <= ntok) then
                        x(irow, j) = vals(i1)
                     else
                        x(irow, j) = 0.0_dp
                     end if
                  end do
               else
                  i2 = min(ncol, ntok)
                  if (i2 > 0) x(irow, 1:i2) = vals(1:i2)
                  if (i2 < ncol) x(irow, i2+1:ncol) = 0.0_dp
               end if
            end if
            deallocate(vals)
         end do
         close(u)
       contains
         pure function preprocess_line(s, delim, cmt) result(out)
            character(len=*), intent(in) :: s, delim, cmt
            character(len=4096) :: out
            integer :: ipos
            out = s
            if (len_trim(cmt) > 0) then
               ipos = index(out, cmt(1:1))
               if (ipos > 0) out = out(:ipos-1)
            end if
            if (len_trim(delim) > 0) then
               do
                  ipos = index(out, delim(1:1))
                  if (ipos <= 0) exit
                  out(ipos:ipos) = " "
               end do
            end if
         end function preprocess_line

         pure integer function count_tokens(s) result(n)
            character(len=*), intent(in) :: s
            integer :: i
            logical :: in_tok
            n = 0
            in_tok = .false.
            do i = 1, len_trim(s)
               if (s(i:i) /= " " .and. s(i:i) /= achar(9)) then
                  if (.not. in_tok) then
                     n = n + 1
                     in_tok = .true.
                  end if
               else
                  in_tok = .false.
               end if
            end do
         end function count_tokens
      end function loadtxt_real_2d

      function loadtxt_real_vector(path, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         real(dp), allocatable :: x(:), matrix(:,:)
         matrix = loadtxt_real_2d(path, skiprows=skiprows, max_rows=max_rows, &
            skip_footer=skip_footer, delimiter=delimiter, comments=comments)
         if (size(matrix,1) > 1 .and. size(matrix,2) > 1) then
            error stop 'loadtxt: vector required by program context, but file contains a matrix: ' // trim(path)
         end if
         if (size(matrix) == 1) then
            error stop 'loadtxt: vector required by program context, but NumPy would return a scalar: ' // trim(path)
         end if
         x = reshape(matrix, [size(matrix)])
      end function loadtxt_real_vector

      function loadtxt_int_vector(path, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         integer, allocatable :: x(:)
         x = int(loadtxt_real_vector(path, skiprows=skiprows, max_rows=max_rows, &
            skip_footer=skip_footer, delimiter=delimiter, comments=comments))
      end function loadtxt_int_vector

      function loadtxt_logical_vector(path, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         logical, allocatable :: x(:)
         x = loadtxt_real_vector(path, skiprows=skiprows, max_rows=max_rows, &
            skip_footer=skip_footer, delimiter=delimiter, comments=comments) /= 0.0_dp
      end function loadtxt_logical_vector

      function loadtxt_real_1d(path, usecol, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in) :: usecol
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         real(kind=dp), allocatable :: x(:)
         integer :: ucs(1)
         real(kind=dp), allocatable :: tmp(:,:)
         ucs(1) = usecol
         tmp = loadtxt_real_2d(path, skiprows=skiprows, max_rows=max_rows, skip_footer=skip_footer, &
            delimiter=delimiter, comments=comments, usecols=ucs)
         allocate(x(size(tmp,1)))
         if (size(tmp,2) >= 1) then
            x = tmp(:,1)
         else
            x = 0.0_dp
         end if
      end function loadtxt_real_1d

      function loadtxt_int_2d(path, skiprows, max_rows, skip_footer, delimiter, comments, usecols) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         integer, intent(in), optional :: usecols(:)
         integer, allocatable :: x(:,:)
         real(kind=dp), allocatable :: tmp(:,:)
         tmp = loadtxt_real_2d(path, skiprows=skiprows, max_rows=max_rows, skip_footer=skip_footer, &
            delimiter=delimiter, comments=comments, usecols=usecols)
         allocate(x(size(tmp,1), size(tmp,2)))
         x = int(tmp)
      end function loadtxt_int_2d

      function loadtxt_int_1d(path, usecol, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in) :: usecol
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         integer, allocatable :: x(:)
         real(kind=dp), allocatable :: tmp(:)
         tmp = loadtxt_real_1d(path, usecol, skiprows=skiprows, max_rows=max_rows, skip_footer=skip_footer, &
            delimiter=delimiter, comments=comments)
         allocate(x(size(tmp)))
         x = int(tmp)
      end function loadtxt_int_1d

      function loadtxt_logical_2d(path, skiprows, max_rows, skip_footer, delimiter, comments, usecols) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         integer, intent(in), optional :: usecols(:)
         logical, allocatable :: x(:,:)
         real(kind=dp), allocatable :: tmp(:,:)
         tmp = loadtxt_real_2d(path, skiprows=skiprows, max_rows=max_rows, skip_footer=skip_footer, &
            delimiter=delimiter, comments=comments, usecols=usecols)
         allocate(x(size(tmp,1), size(tmp,2)))
         x = (tmp /= 0.0_dp)
      end function loadtxt_logical_2d

      function loadtxt_logical_1d(path, usecol, skiprows, max_rows, skip_footer, delimiter, comments) result(x)
         character(len=*), intent(in) :: path
         integer, intent(in) :: usecol
         integer, intent(in), optional :: skiprows, max_rows, skip_footer
         character(len=*), intent(in), optional :: delimiter, comments
         logical, allocatable :: x(:)
         real(kind=dp), allocatable :: tmp(:)
         tmp = loadtxt_real_1d(path, usecol, skiprows=skiprows, max_rows=max_rows, skip_footer=skip_footer, &
            delimiter=delimiter, comments=comments)
         allocate(x(size(tmp)))
         x = (tmp /= 0.0_dp)
      end function loadtxt_logical_1d

      function np_fmt_number(x, spec) result(s)
         ! x formatted like Python's `spec % x` for the printf specs numpy's
         ! savetxt uses: %[width][.prec]{e,f,g,d,i} (default %.18e).
         real(kind=dp), intent(in) :: x
         character(len=*), intent(in) :: spec
         character(len=:), allocatable :: s
         character(len=64) :: buf, wf
         character(len=1) :: conv
         integer :: width, prec, ipos, ios, k, e
         character(len=:), allocatable :: body
         conv = spec(len_trim(spec):len_trim(spec))
         body = spec(2:len_trim(spec) - 1)
         width = 0
         prec = 6
         ipos = index(body, ".")
         if (ipos > 0) then
            read(body(ipos + 1:), *, iostat=ios) prec
            if (ios /= 0) prec = 6
            if (ipos > 1) read(body(1:ipos - 1), *, iostat=ios) width
         else if (len(body) > 0) then
            read(body, *, iostat=ios) width
         end if
         select case (conv)
         case ("d", "i")
            ! Python's %d truncates a float toward zero.
            write(buf, "(i0)") int(x)
         case ("f", "F")
            write(wf, "(a,i0,a)") "(f0.", prec, ")"
            write(buf, wf) x
            buf = adjustl(buf)
            ! Fortran leaves out the zero before the decimal point.
            if (buf(1:1) == ".") buf = "0" // buf
            if (buf(1:2) == "-.") buf = "-0" // buf(2:)
         case ("g", "G")
            write(buf, "(g0)") x
         case default
            ! %e: d.ddd...e+XX, at least two exponent digits.
            write(wf, "(a,i0,a,i0,a)") "(es", prec + 10, ".", prec, "e3)"
            write(buf, wf) x
            buf = adjustl(buf)
            k = index(buf, "E")
            if (k > 0) then
               read(buf(k + 1:), *, iostat=ios) e
               if (ios == 0) then
                  if (abs(e) < 100) then
                     write(buf(k:), "(a,sp,i3.2)") "e", e
                  else
                     write(buf(k:), "(a,sp,i0)") "e", e
                  end if
               end if
            end if
         end select
         s = trim(adjustl(buf))
         if (len(s) < width) s = repeat(" ", width - len(s)) // s
      end function np_fmt_number

      subroutine savetxt_real_2d(path, x, delimiter, fmt, header, footer, comments)
         ! np.savetxt(path, x, fmt, delimiter, header=, footer=, comments=).
         character(len=*), intent(in) :: path
         real(kind=dp), intent(in) :: x(:,:)
         character(len=*), intent(in), optional :: delimiter, fmt, header, footer, comments
         character(len=:), allocatable :: dsep, spec, cmt
         integer :: u, i, j
         dsep = " "
         if (present(delimiter)) dsep = delimiter
         spec = "%.18e"
         if (present(fmt)) spec = trim(adjustl(fmt))
         cmt = "# "
         if (present(comments)) cmt = comments
         open(newunit=u, file=trim(path), status="replace", action="write")
         if (present(header)) then
            if (len(header) > 0) call write_commented(header)
         end if
         do i = 1, size(x, 1)
            do j = 1, size(x, 2)
               if (j > 1) write(u, "(a)", advance="no") dsep
               write(u, "(a)", advance="no") np_fmt_number(x(i, j), spec)
            end do
            write(u, "(a)") ""
         end do
         if (present(footer)) then
            if (len(footer) > 0) call write_commented(footer)
         end if
         close(u)
      contains
         subroutine write_commented(text)
            ! Each line of text with the comment prefix, as numpy writes them.
            character(len=*), intent(in) :: text
            integer :: a, b
            a = 1
            do
               b = index(text(a:), new_line("a"))
               if (b == 0) then
                  write(u, "(a)") cmt // text(a:)
                  exit
               end if
               write(u, "(a)") cmt // text(a:a + b - 2)
               a = a + b
            end do
         end subroutine write_commented
      end subroutine savetxt_real_2d

      pure integer function optval_int(x, default) result(v)
         integer, intent(in), optional :: x
         integer, intent(in) :: default
         if (present(x)) then
            v = x
         else
            v = default
         end if
      end function optval_int

      pure real(kind=dp) function optval_real(x, default) result(v)
         real(kind=dp), intent(in), optional :: x
         real(kind=dp), intent(in) :: default
         if (present(x)) then
            v = x
         else
            v = default
         end if
      end function optval_real

      pure complex(kind=dp) function optval_complex(x, default) result(v)
         complex(kind=dp), intent(in), optional :: x
         complex(kind=dp), intent(in) :: default
         if (present(x)) then
            v = x
         else
            v = default
         end if
      end function optval_complex

      pure logical function optval_logical(x, default) result(v)
         logical, intent(in), optional :: x
         logical, intent(in) :: default
         if (present(x)) then
            v = x
         else
            v = default
         end if
      end function optval_logical

      pure function optval_char(x, default) result(v)
         character(len=*), intent(in), optional :: x
         character(len=*), intent(in) :: default
         character(len=:), allocatable :: v
         if (present(x)) then
            v = x
         else
            v = default
         end if
      end function optval_char

      function exec_cmd_status(cmd) result(status)
         character(len=*), intent(in) :: cmd
         integer :: status
         integer :: cmdstat
         call execute_command_line(cmd, wait=.true., exitstat=status, cmdstat=cmdstat)
         if (cmdstat /= 0) status = cmdstat
      end function exec_cmd_status

      subroutine rng_replay_maybe_init()
         implicit none
         integer :: stat, nlen
         character(len=4096) :: stem_buf
         if (rng_replay_checked) return
         rng_replay_checked = .true.
         call get_environment_variable("XP2F_RNG_REPLAY_STEM", value=stem_buf, length=nlen, status=stat)
         if (stat /= 0 .or. nlen <= 0) return
         rng_replay_stem = stem_buf(:nlen)
         open(newunit=rng_replay_meta_u, file=trim(rng_replay_stem) // ".meta", status="old", action="read", iostat=stat)
         if (stat /= 0) stop "rng replay: could not open metadata file"
         open(newunit=rng_replay_bin_u, file=trim(rng_replay_stem) // ".bin", status="old", access="stream", form="unformatted", action="read", iostat=stat)
         if (stat /= 0) stop "rng replay: could not open binary file"
         rng_replay_enabled = .true.
         rng_replay_call_index = 0
      end subroutine rng_replay_maybe_init

      subroutine rng_replay_expect(op_name, rank_expected, n0_expected, n1_expected)
         implicit none
         character(len=*), intent(in) :: op_name
         integer, intent(in) :: rank_expected
         integer, intent(in) :: n0_expected
         integer, intent(in) :: n1_expected
         integer :: ios, call_id, rank_file, n0_file, n1_file
         character(len=32) :: op_file
         call rng_replay_maybe_init()
         if (.not. rng_replay_enabled) return
         read(rng_replay_meta_u, *, iostat=ios) call_id, op_file, rank_file, n0_file, n1_file
         if (ios /= 0) stop "rng replay: metadata exhausted or unreadable"
         if (trim(op_file) /= trim(op_name)) stop "rng replay: operation mismatch"
         if (rank_file /= rank_expected) stop "rng replay: rank mismatch"
         if (n0_file /= n0_expected) stop "rng replay: first extent mismatch"
         if (n1_file /= n1_expected) stop "rng replay: second extent mismatch"
         rng_replay_call_index = rng_replay_call_index + 1
      end subroutine rng_replay_expect

      subroutine random_normal_vec(x)
         ! fill x with N(0,1) variates using Box-Muller
         implicit none
         real(kind=dp), intent(out) :: x(:)
         integer :: i, n
         real(kind=dp) :: u1, u2, rad, theta
         real(kind=dp), parameter :: two_pi = 2.0_dp * acos(-1.0_dp)
         n = size(x)
         i = 1
         do while (i <= n)
            call random_number(u1)
            call random_number(u2)
            if (u1 <= tiny(1.0_dp)) cycle
            rad = sqrt(-2.0_dp * log(u1))
            theta = two_pi * u2
            x(i) = rad * cos(theta)
            if (i + 1 <= n) x(i + 1) = rad * sin(theta)
            i = i + 2
         end do
      end subroutine random_normal_vec

      function runif0() result(x)
         real(kind=dp) :: x
         call rng_replay_expect("uniform", 0, -1, -1)
         if (rng_replay_enabled) then
            read(rng_replay_bin_u) x
         else
            call random_number(x)
         end if
      end function runif0

      function runif1(n) result(x)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: x(:)
         if (n < 0) stop "runif: n must be >= 0"
         allocate(x(n))
         call rng_replay_expect("uniform", 1, n, -1)
         if (rng_replay_enabled) then
            if (n > 0) read(rng_replay_bin_u) x
         else
            if (n > 0) call random_number(x)
         end if
      end function runif1

      function runif2(n, m) result(x)
         integer, intent(in) :: n, m
         real(kind=dp), allocatable :: x(:,:)
         if (n < 0 .or. m < 0) stop "runif: n,m must be >= 0"
         allocate(x(n, m))
         call rng_replay_expect("uniform", 2, n, m)
         if (rng_replay_enabled) then
            if (n > 0 .and. m > 0) read(rng_replay_bin_u) x
         else
            if (n > 0 .and. m > 0) call random_number(x)
         end if
      end function runif2

      function runif3(n, m, l) result(x)
         integer, intent(in) :: n, m, l
         real(kind=dp), allocatable :: x(:,:,:)
         if (n < 0 .or. m < 0 .or. l < 0) stop "runif: n,m,l must be >= 0"
         allocate(x(n, m, l))
         call rng_replay_maybe_init()
         if (rng_replay_enabled) stop "rng replay: rank-3 uniform draws are not supported"
         if (n > 0 .and. m > 0 .and. l > 0) call random_number(x)
      end function runif3

      integer function random_randrange_int(start, stop, step)
         integer, intent(in) :: start, stop, step
         integer :: n
         real(kind=dp) :: u
         if (step == 0) error stop "randrange: step must not be zero"
         if (step > 0) then
            if (start >= stop) error stop "randrange: empty range"
            n = 1 + (stop - 1 - start) / step
         else
            if (start <= stop) error stop "randrange: empty range"
            n = 1 + (start - 1 - stop) / (-step)
         end if
         call random_number(u)
         random_randrange_int = start + step * int(u * real(n, kind=dp))
      end function random_randrange_int

      function random_choice_char(a) result(x)
         character(len=*), intent(in) :: a(:)
         character(len=len(a)) :: x
         real(kind=dp) :: u
         integer :: j
         if (size(a) <= 0) error stop "random.choice: empty sequence"
         call random_number(u)
         j = 1 + int(u * real(size(a), kind=dp))
         if (j < 1) j = 1
         if (j > size(a)) j = size(a)
         x = a(j)
      end function random_choice_char

      function random_choices_char(a, k) result(x)
         character(len=*), intent(in) :: a(:)
         integer, intent(in) :: k
         character(len=len(a)), allocatable :: x(:)
         integer :: i
         if (size(a) <= 0 .and. k > 0) error stop "random.choices: empty sequence"
         if (k < 0) error stop "random.choices: k must be nonnegative"
         allocate(x(k))
         do i = 1, k
            x(i) = random_choice_char(a)
         end do
      end function random_choices_char

      function random_sample_char(a, k) result(x)
         character(len=*), intent(in) :: a(:)
         integer, intent(in) :: k
         character(len=len(a)), allocatable :: x(:)
         integer, allocatable :: idx(:)
         integer :: i, j, tmp
         real(kind=dp) :: u
         if (k < 0 .or. k > size(a)) error stop "random.sample: invalid sample size"
         allocate(x(k))
         allocate(idx(size(a)))
         do i = 1, size(a)
            idx(i) = i
         end do
         do i = size(idx), 2, -1
            call random_number(u)
            j = 1 + int(u * real(i, kind=dp))
            if (j < 1) j = 1
            if (j > i) j = i
            tmp = idx(i)
            idx(i) = idx(j)
            idx(j) = tmp
         end do
         do i = 1, k
            x(i) = a(idx(i))
         end do
      end function random_sample_char

      function rnorm0() result(x)
         real(kind=dp) :: x
         real(kind=dp) :: tmp(1)
         call rng_replay_expect("normal", 0, -1, -1)
         if (rng_replay_enabled) then
            read(rng_replay_bin_u) x
         else
            call random_normal_vec(tmp)
            x = tmp(1)
         end if
      end function rnorm0

      function rnorm1(n) result(x)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: x(:)
         if (n < 0) stop "rnorm: n must be >= 0"
         allocate(x(n))
         call rng_replay_expect("normal", 1, n, -1)
         if (rng_replay_enabled) then
            if (n > 0) read(rng_replay_bin_u) x
         else
            if (n > 0) call random_normal_vec(x)
         end if
      end function rnorm1

      function rnorm2(n, m) result(x)
         integer, intent(in) :: n, m
         real(kind=dp), allocatable :: x(:,:)
         real(kind=dp), allocatable :: tmp(:)
         if (n < 0 .or. m < 0) stop "rnorm: n,m must be >= 0"
         allocate(x(n, m))
         call rng_replay_expect("normal", 2, n, m)
         if (rng_replay_enabled) then
            if (n > 0 .and. m > 0) read(rng_replay_bin_u) x
         else
            if (n > 0 .and. m > 0) then
               allocate(tmp(n * m))
               call random_normal_vec(tmp)
               x = reshape(tmp, [n, m])
               deallocate(tmp)
            end if
         end if
      end function rnorm2

      function rnorm3(n, m, l) result(x)
         integer, intent(in) :: n, m, l
         real(kind=dp), allocatable :: x(:,:,:)
         real(kind=dp), allocatable :: tmp(:)
         if (n < 0 .or. m < 0 .or. l < 0) stop "rnorm: n,m,l must be >= 0"
         allocate(x(n, m, l))
         call rng_replay_maybe_init()
         if (rng_replay_enabled) stop "rng replay: rank-3 normal draws are not supported"
         if (n > 0 .and. m > 0 .and. l > 0) then
            allocate(tmp(n * m * l))
            call random_normal_vec(tmp)
            x = reshape(tmp, [n, m, l])
            deallocate(tmp)
         end if
      end function rnorm3

      real(kind=dp) function random_exponential(scale)
         real(kind=dp), intent(in), optional :: scale
         real(kind=dp) :: u, s
         s = 1.0_dp
         if (present(scale)) s = scale
         call random_number(u)
         if (u <= tiny(1.0_dp)) u = tiny(1.0_dp)
         random_exponential = -log(u) * s
      end function random_exponential

      subroutine random_exponential_vec(x, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: scale
         integer :: i
         do i = 1, size(x)
            if (present(scale)) then
               x(i) = random_exponential(scale)
            else
               x(i) = random_exponential()
            end if
         end do
      end subroutine random_exponential_vec

      recursive real(kind=dp) function random_gamma(shape, scale) result(g)
         real(kind=dp), intent(in) :: shape
         real(kind=dp), intent(in), optional :: scale
         real(kind=dp) :: sc, d, c, u, v, z
         real(kind=dp) :: tmpn(1)
         if (shape <= 0.0_dp) stop "random_gamma: shape must be > 0"
         sc = 1.0_dp
         if (present(scale)) sc = scale
         if (sc <= 0.0_dp) stop "random_gamma: scale must be > 0"
         if (shape < 1.0_dp) then
            call random_number(u)
            if (u <= tiny(1.0_dp)) u = tiny(1.0_dp)
            g = random_gamma(shape + 1.0_dp, sc) * u**(1.0_dp / shape)
            return
         end if
         d = shape - 1.0_dp / 3.0_dp
         c = 1.0_dp / sqrt(9.0_dp * d)
         do
            call random_normal_vec(tmpn)
            z = tmpn(1)
            v = (1.0_dp + c * z)**3
            if (v <= 0.0_dp) cycle
            call random_number(u)
            if (u <= tiny(1.0_dp)) u = tiny(1.0_dp)
            if (log(u) < 0.5_dp * z**2 + d - d * v + d * log(v)) then
               g = d * v * sc
               return
            end if
         end do
      end function random_gamma

      subroutine random_gamma_vec(x, shape, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: shape
         real(kind=dp), intent(in), optional :: scale
         integer :: i
         do i = 1, size(x)
            if (present(scale)) then
               x(i) = random_gamma(shape, scale)
            else
               x(i) = random_gamma(shape)
            end if
         end do
      end subroutine random_gamma_vec

      real(kind=dp) function random_student_t(df)
         real(kind=dp), intent(in) :: df
         real(kind=dp) :: z(1), v
         if (df <= 0.0_dp) stop "random_student_t: df must be > 0"
         call random_normal_vec(z)
         v = random_gamma(df / 2.0_dp, 2.0_dp)
         random_student_t = z(1) / sqrt(v / df)
      end function random_student_t

      subroutine random_student_t_vec(x, df)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: df
         integer :: i
         do i = 1, size(x)
            x(i) = random_student_t(df)
         end do
      end subroutine random_student_t_vec

      real(kind=dp) function random_f(dfnum, dfden)
         real(kind=dp), intent(in) :: dfnum, dfden
         real(kind=dp) :: x1, x2
         if (dfnum <= 0.0_dp .or. dfden <= 0.0_dp) stop "random_f: dfs must be > 0"
         x1 = random_gamma(dfnum / 2.0_dp, 2.0_dp) / dfnum
         x2 = random_gamma(dfden / 2.0_dp, 2.0_dp) / dfden
         random_f = x1 / x2
      end function random_f

      subroutine random_f_vec(x, dfnum, dfden)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: dfnum, dfden
         integer :: i
         do i = 1, size(x)
            x(i) = random_f(dfnum, dfden)
         end do
      end subroutine random_f_vec

      integer function random_poisson(mu)
         real(kind=dp), intent(in) :: mu
         real(kind=dp) :: l, p, u
         integer :: k
         if (mu < 0.0_dp) stop "random_poisson: mu must be >= 0"
         l = exp(-mu)
         k = 0
         p = 1.0_dp
         do
            k = k + 1
            call random_number(u)
            p = p * u
            if (p <= l) exit
         end do
         random_poisson = k - 1
      end function random_poisson

      subroutine random_poisson_vec(x, mu)
         integer, intent(out) :: x(:)
         real(kind=dp), intent(in) :: mu
         integer :: i
         do i = 1, size(x)
            x(i) = random_poisson(mu)
         end do
      end subroutine random_poisson_vec

      integer function random_geometric(p)
         ! Source: John Burkardt, prob.f90, geometric_sample/geometric_cdf_inv.
         real(kind=dp), intent(in) :: p
         real(kind=dp) :: u
         if (p < 0.0_dp .or. p > 1.0_dp) stop "random_geometric: p must be in [0,1]"
         if (p == 1.0_dp) then
            random_geometric = 1
            return
         end if
         if (p == 0.0_dp) then
            random_geometric = huge(1)
            return
         end if
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_geometric = 1 + int(log(1.0_dp - u) / log(1.0_dp - p))
      end function random_geometric

      subroutine random_geometric_vec(x, p)
         integer, intent(out) :: x(:)
         real(kind=dp), intent(in) :: p
         integer :: i
         do i = 1, size(x)
            x(i) = random_geometric(p)
         end do
      end subroutine random_geometric_vec

      integer function random_binomial(n, p)
         integer, intent(in) :: n
         real(kind=dp), intent(in) :: p
         integer :: i
         real(kind=dp) :: u
         if (n < 0) stop "random_binomial: n must be >= 0"
         if (p < 0.0_dp .or. p > 1.0_dp) stop "random_binomial: p must be in [0,1]"
         random_binomial = 0
         do i = 1, n
            call random_number(u)
            if (u < p) random_binomial = random_binomial + 1
         end do
      end function random_binomial

      subroutine random_binomial_vec(x, n, p)
         integer, intent(out) :: x(:)
         integer, intent(in) :: n
         real(kind=dp), intent(in) :: p
         integer :: i
         do i = 1, size(x)
            x(i) = random_binomial(n, p)
         end do
      end subroutine random_binomial_vec

      integer function random_hypergeometric(ngood, nbad, nsample)
         integer, intent(in) :: ngood, nbad, nsample
         integer :: gg, nn, i
         real(kind=dp) :: pr, u
         if (ngood < 0 .or. nbad < 0 .or. nsample < 0) stop "random_hypergeometric: args must be >= 0"
         if (nsample > ngood + nbad) stop "random_hypergeometric: nsample too large"
         gg = ngood
         nn = ngood + nbad
         random_hypergeometric = 0
         do i = 1, nsample
            if (gg <= 0) exit
            pr = real(gg, kind=dp) / real(nn, kind=dp)
            call random_number(u)
            if (u < pr) then
               random_hypergeometric = random_hypergeometric + 1
               gg = gg - 1
            end if
            nn = nn - 1
         end do
      end function random_hypergeometric

      subroutine random_hypergeometric_vec(x, ngood, nbad, nsample)
         integer, intent(out) :: x(:)
         integer, intent(in) :: ngood, nbad, nsample
         integer :: i
         do i = 1, size(x)
            x(i) = random_hypergeometric(ngood, nbad, nsample)
         end do
      end subroutine random_hypergeometric_vec

      integer function random_zipf(a)
         real(kind=dp), intent(in) :: a
         real(kind=dp) :: b, const, t, u, v
         real(kind=dp), parameter :: one = 1.0_dp
         if (a <= 1.0_dp) stop "random_zipf: a must be > 1"
         b = 2.0_dp**(a - one)
         const = -one / (a - one)
         do
            call random_number(u)
            call random_number(v)
            random_zipf = int(floor(u**const))
            if (random_zipf < 1) cycle
            t = (one + one / real(random_zipf, kind=dp))**(a - one)
            if (v * real(random_zipf, kind=dp) * (t - one) / (b - one) <= t / b) exit
         end do
      end function random_zipf

      subroutine random_zipf_vec(x, a)
         integer, intent(out) :: x(:)
         real(kind=dp), intent(in) :: a
         integer :: i
         do i = 1, size(x)
            x(i) = random_zipf(a)
         end do
      end subroutine random_zipf_vec

      real(kind=dp) function random_beta(a, b)
         real(kind=dp), intent(in) :: a, b
         real(kind=dp) :: x1, x2
         if (a <= 0.0_dp .or. b <= 0.0_dp) stop "random_beta: a,b must be > 0"
         x1 = random_gamma(a, 1.0_dp)
         x2 = random_gamma(b, 1.0_dp)
         random_beta = x1 / (x1 + x2)
      end function random_beta

      subroutine random_beta_vec(x, a, b)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: a, b
         integer :: i
         do i = 1, size(x)
            x(i) = random_beta(a, b)
         end do
      end subroutine random_beta_vec

      real(kind=dp) function random_lognormal(meanlog, sdlog)
         real(kind=dp), intent(in), optional :: meanlog, sdlog
         real(kind=dp) :: mu, sig, z(1)
         mu = 0.0_dp
         sig = 1.0_dp
         if (present(meanlog)) mu = meanlog
         if (present(sdlog)) sig = sdlog
         call random_normal_vec(z)
         random_lognormal = exp(mu + sig * z(1))
      end function random_lognormal

      subroutine random_lognormal_vec(x, meanlog, sdlog)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: meanlog, sdlog
         integer :: i
         do i = 1, size(x)
            if (present(meanlog) .and. present(sdlog)) then
               x(i) = random_lognormal(meanlog, sdlog)
            elseif (present(meanlog)) then
               x(i) = random_lognormal(meanlog=meanlog)
            elseif (present(sdlog)) then
               x(i) = random_lognormal(sdlog=sdlog)
            else
               x(i) = random_lognormal()
            end if
         end do
      end subroutine random_lognormal_vec

      real(kind=dp) function random_chisquare(df)
         real(kind=dp), intent(in) :: df
         if (df <= 0.0_dp) stop "random_chisquare: df must be > 0"
         random_chisquare = random_gamma(df / 2.0_dp, 2.0_dp)
      end function random_chisquare

      subroutine random_chisquare_vec(x, df)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: df
         integer :: i
         do i = 1, size(x)
            x(i) = random_chisquare(df)
         end do
      end subroutine random_chisquare_vec

      real(kind=dp) function random_laplace(loc, scale)
         real(kind=dp), intent(in), optional :: loc, scale
         real(kind=dp) :: u, mu, b
         mu = 0.0_dp
         b = 1.0_dp
         if (present(loc)) mu = loc
         if (present(scale)) b = scale
         if (b <= 0.0_dp) stop "random_laplace: scale must be > 0"
         call random_number(u)
         if (u < 0.5_dp) then
            random_laplace = mu + b * log(max(2.0_dp * u, tiny(1.0_dp)))
         else
            random_laplace = mu - b * log(max(2.0_dp * (1.0_dp - u), tiny(1.0_dp)))
         end if
      end function random_laplace

      subroutine random_laplace_vec(x, loc, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: loc, scale
         integer :: i
         do i = 1, size(x)
            if (present(loc) .and. present(scale)) then
               x(i) = random_laplace(loc, scale)
            elseif (present(loc)) then
               x(i) = random_laplace(loc=loc)
            elseif (present(scale)) then
               x(i) = random_laplace(scale=scale)
            else
               x(i) = random_laplace()
            end if
         end do
      end subroutine random_laplace_vec

      real(kind=dp) function random_logistic(loc, scale)
         real(kind=dp), intent(in), optional :: loc, scale
         real(kind=dp) :: u, mu, s
         mu = 0.0_dp
         s = 1.0_dp
         if (present(loc)) mu = loc
         if (present(scale)) s = scale
         if (s <= 0.0_dp) stop "random_logistic: scale must be > 0"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_logistic = mu + s * log(u / (1.0_dp - u))
      end function random_logistic

      subroutine random_logistic_vec(x, loc, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: loc, scale
         integer :: i
         do i = 1, size(x)
            if (present(loc) .and. present(scale)) then
               x(i) = random_logistic(loc, scale)
            elseif (present(loc)) then
               x(i) = random_logistic(loc=loc)
            elseif (present(scale)) then
               x(i) = random_logistic(scale=scale)
            else
               x(i) = random_logistic()
            end if
         end do
      end subroutine random_logistic_vec

      real(kind=dp) function random_cauchy(loc, scale)
         real(kind=dp), intent(in), optional :: loc, scale
         real(kind=dp) :: u, mu, s
         mu = 0.0_dp
         s = 1.0_dp
         if (present(loc)) mu = loc
         if (present(scale)) s = scale
         if (s <= 0.0_dp) stop "random_cauchy: scale must be > 0"
         call random_number(u)
         random_cauchy = mu + s * tan(acos(-1.0_dp) * (u - 0.5_dp))
      end function random_cauchy

      subroutine random_cauchy_vec(x, loc, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: loc, scale
         integer :: i
         do i = 1, size(x)
            if (present(loc) .and. present(scale)) then
               x(i) = random_cauchy(loc, scale)
            elseif (present(loc)) then
               x(i) = random_cauchy(loc=loc)
            elseif (present(scale)) then
               x(i) = random_cauchy(scale=scale)
            else
               x(i) = random_cauchy()
            end if
         end do
      end subroutine random_cauchy_vec

      real(kind=dp) function random_weibull(a)
         ! Source: Alan Miller, amiller_mirror/random.f90 (Weibull sampler).
         real(kind=dp), intent(in) :: a
         if (a <= 0.0_dp) stop "random_weibull: a must be > 0"
         random_weibull = random_exponential()**(1.0_dp / a)
      end function random_weibull

      subroutine random_weibull_vec(x, a)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: a
         integer :: i
         do i = 1, size(x)
            x(i) = random_weibull(a)
         end do
      end subroutine random_weibull_vec

      integer function random_neg_binomial(sk, p)
         ! Source: Alan Miller, amiller_mirror/random.f90 (negative binomial sampler).
         real(kind=dp), intent(in) :: sk, p
         real(kind=dp), parameter :: h = 0.7_dp
         real(kind=dp) :: p_alg, q, x, st, uln, v, r, s, y, g
         integer :: k, i, n
         if (sk <= 0.0_dp .or. p <= 0.0_dp .or. p >= 1.0_dp) stop "random_neg_binomial: invalid params"
         ! NumPy parameterization: p is success probability.
         ! Alan Miller routine expects the opposite probability in its recurrence.
         p_alg = 1.0_dp - p
         q = 1.0_dp - p_alg
         x = 0.0_dp
         st = sk
         if (p_alg > h) then
            v = 1.0_dp / log(p_alg)
            k = int(st)
            do i = 1, k
               do
                  call random_number(r)
                  if (r > 0.0_dp) exit
               end do
               n = int(v * log(r))
               x = x + real(n, kind=dp)
            end do
            st = st - real(k, kind=dp)
         end if
         s = 0.0_dp
         uln = -log(tiny(1.0_dp))
         if (st > -uln / log(q)) stop "random_neg_binomial: p too large for sk"
         y = q**st
         g = st
         call random_number(r)
         do
            if (y > r) exit
            r = r - y
            s = s + 1.0_dp
            y = y * p_alg * g / s
            g = g + 1.0_dp
         end do
         random_neg_binomial = int(x + s + 0.5_dp)
      end function random_neg_binomial

      subroutine random_neg_binomial_vec(x, sk, p)
         integer, intent(out) :: x(:)
         real(kind=dp), intent(in) :: sk, p
         integer :: i
         do i = 1, size(x)
            x(i) = random_neg_binomial(sk, p)
         end do
      end subroutine random_neg_binomial_vec

      real(kind=dp) function random_von_mises(kappa)
         ! Source: Alan Miller, amiller_mirror/random.f90 (von Mises sampler).
         real(kind=dp), intent(in) :: kappa
         integer :: j, n, nk
         real(kind=dp) :: sump, r, th, lambda, rlast
         real(kind=dp), save :: p(20), theta(0:20)
         real(kind=dp), save :: last_kappa = -1.0_dp
         logical, save :: initialized = .false.
         if (kappa < 0.0_dp) stop "random_von_mises: kappa must be >= 0"
         if ((.not. initialized) .or. abs(kappa - last_kappa) > 0.0_dp) then
            nk = int(kappa + kappa + 1.0_dp)
            if (nk > 20) stop "random_von_mises: kappa too large for table"
            theta(0) = 0.0_dp
            if (kappa > 0.5_dp) then
               sump = 0.0_dp
               do j = 1, nk
                  if (j < nk) then
                     theta(j) = acos(1.0_dp - real(j, kind=dp) / kappa)
                  else
                     theta(nk) = acos(-1.0_dp)
                  end if
                  call vm_integral(theta(j-1), theta(j), p(j), kappa)
                  sump = sump + p(j)
               end do
               p(1:nk) = p(1:nk) / sump
            else
               p(1) = 1.0_dp
               theta(1) = acos(-1.0_dp)
               nk = 1
            end if
            last_kappa = kappa
            initialized = .true.
         else
            nk = int(kappa + kappa + 1.0_dp)
            if (kappa <= 0.5_dp) nk = 1
         end if
         call random_number(r)
         do j = 1, nk
            r = r - p(j)
            if (r < 0.0_dp) exit
         end do
         r = -r / p(j)
         do
            th = theta(j-1) + r * (theta(j) - theta(j-1))
            lambda = kappa - real(j, kind=dp) + 1.0_dp - kappa * cos(th)
            n = 1
            rlast = lambda
            do
               call random_number(r)
               if (r > rlast) exit
               n = n + 1
               rlast = r
            end do
            if (mod(n, 2) /= 0) exit
            call random_number(r)
         end do
         random_von_mises = sign(th, (r - rlast) / (1.0_dp - rlast) - 0.5_dp)
      end function random_von_mises

      subroutine random_von_mises_vec(x, kappa)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: kappa
         integer :: i
         do i = 1, size(x)
            x(i) = random_von_mises(kappa)
         end do
      end subroutine random_von_mises_vec

      real(kind=dp) function random_pareto(a)
         ! Source: John Burkardt, prob.f90, pareto_sample/pareto_cdf_inv.
         ! NumPy convention: support x >= 0 with shape a.
         real(kind=dp), intent(in) :: a
         real(kind=dp) :: u
         if (a <= 0.0_dp) stop "random_pareto: a must be > 0"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_pareto = (1.0_dp - u)**(-1.0_dp / a) - 1.0_dp
      end function random_pareto

      subroutine random_pareto_vec(x, a)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: a
         integer :: i
         do i = 1, size(x)
            x(i) = random_pareto(a)
         end do
      end subroutine random_pareto_vec

      real(kind=dp) function random_power(a)
         ! Source: John Burkardt, prob.f90, power_sample/power_cdf_inv.
         ! NumPy convention on [0,1], shape a.
         real(kind=dp), intent(in) :: a
         real(kind=dp) :: u
         if (a <= 0.0_dp) stop "random_power: a must be > 0"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_power = u**(1.0_dp / a)
      end function random_power

      subroutine random_power_vec(x, a)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: a
         integer :: i
         do i = 1, size(x)
            x(i) = random_power(a)
         end do
      end subroutine random_power_vec

      real(kind=dp) function random_rayleigh(scale)
         ! Source: John Burkardt, prob.f90, rayleigh_sample/rayleigh_cdf_inv.
         real(kind=dp), intent(in), optional :: scale
         real(kind=dp) :: s, u
         s = 1.0_dp
         if (present(scale)) s = scale
         if (s <= 0.0_dp) stop "random_rayleigh: scale must be > 0"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_rayleigh = s * sqrt(-2.0_dp * log(1.0_dp - u))
      end function random_rayleigh

      subroutine random_rayleigh_vec(x, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: scale
         integer :: i
         do i = 1, size(x)
            if (present(scale)) then
               x(i) = random_rayleigh(scale)
            else
               x(i) = random_rayleigh()
            end if
         end do
      end subroutine random_rayleigh_vec

      real(kind=dp) function random_gumbel(loc, scale)
         ! Source: John Burkardt, prob.f90, gumbel_sample/gumbel_cdf_inv.
         real(kind=dp), intent(in), optional :: loc, scale
         real(kind=dp) :: mu, b, u
         mu = 0.0_dp
         b = 1.0_dp
         if (present(loc)) mu = loc
         if (present(scale)) b = scale
         if (b <= 0.0_dp) stop "random_gumbel: scale must be > 0"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_gumbel = mu - b * log(-log(u))
      end function random_gumbel

      subroutine random_gumbel_vec(x, loc, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in), optional :: loc, scale
         integer :: i
         do i = 1, size(x)
            if (present(loc) .and. present(scale)) then
               x(i) = random_gumbel(loc, scale)
            elseif (present(loc)) then
               x(i) = random_gumbel(loc=loc)
            elseif (present(scale)) then
               x(i) = random_gumbel(scale=scale)
            else
               x(i) = random_gumbel()
            end if
         end do
      end subroutine random_gumbel_vec

      real(kind=dp) function random_wald(mean, scale)
         ! Source: John Burkardt, prob.f90, inverse_gaussian_sample.
         real(kind=dp), intent(in) :: mean, scale
         real(kind=dp) :: phi, z(1), y, t, u
         if (mean <= 0.0_dp .or. scale <= 0.0_dp) stop "random_wald: mean,scale must be > 0"
         phi = scale / mean
         call random_normal_vec(z)
         y = z(1) * z(1)
         t = 1.0_dp + 0.5_dp * (y - sqrt(4.0_dp * phi * y + y * y)) / phi
         call random_number(u)
         if (u * (1.0_dp + t) <= 1.0_dp) then
            random_wald = mean * t
         else
            random_wald = mean / t
         end if
      end function random_wald

      subroutine random_wald_vec(x, mean, scale)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: mean, scale
         integer :: i
         do i = 1, size(x)
            x(i) = random_wald(mean, scale)
         end do
      end subroutine random_wald_vec

      real(kind=dp) function random_noncentral_chisquare(df, nonc)
         ! Source: John Burkardt, prob.f90, chi_square_noncentral_sample.
         real(kind=dp), intent(in) :: df, nonc
         real(kind=dp) :: x1, x2n(1), mu
         if (df < 1.0_dp .or. nonc < 0.0_dp) stop "random_noncentral_chisquare: invalid parameters"
         x1 = random_chisquare(df - 1.0_dp)
         call random_normal_vec(x2n)
         mu = sqrt(max(nonc, 0.0_dp))
         random_noncentral_chisquare = x1 + (mu + x2n(1))**2
      end function random_noncentral_chisquare

      subroutine random_noncentral_chisquare_vec(x, df, nonc)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: df, nonc
         integer :: i
         do i = 1, size(x)
            x(i) = random_noncentral_chisquare(df, nonc)
         end do
      end subroutine random_noncentral_chisquare_vec

      real(kind=dp) function random_noncentral_f(dfnum, dfden, nonc)
         real(kind=dp), intent(in) :: dfnum, dfden, nonc
         real(kind=dp) :: xn, xd
         if (dfnum <= 0.0_dp .or. dfden <= 0.0_dp .or. nonc < 0.0_dp) stop "random_noncentral_f: invalid parameters"
         xn = random_noncentral_chisquare(dfnum, nonc) / dfnum
         xd = random_chisquare(dfden) / dfden
         random_noncentral_f = xn / xd
      end function random_noncentral_f

      subroutine random_noncentral_f_vec(x, dfnum, dfden, nonc)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: dfnum, dfden, nonc
         integer :: i
         do i = 1, size(x)
            x(i) = random_noncentral_f(dfnum, dfden, nonc)
         end do
      end subroutine random_noncentral_f_vec

      real(kind=dp) function random_triangular(left, mode, right)
         ! Source: John Burkardt, prob.f90, triangle_sample/triangle_cdf_inv.
         real(kind=dp), intent(in) :: left, mode, right
         real(kind=dp) :: u, cut
         if (left > mode .or. mode > right .or. left == right) stop "random_triangular: require left<=mode<=right and left<right"
         call random_number(u)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         cut = (mode - left) / (right - left)
         if (u <= cut) then
            random_triangular = left + sqrt(u * (right - left) * (mode - left))
         else
            random_triangular = right - sqrt((1.0_dp - u) * (right - left) * (right - mode))
         end if
      end function random_triangular

      subroutine random_triangular_vec(x, left, mode, right)
         real(kind=dp), intent(out) :: x(:)
         real(kind=dp), intent(in) :: left, mode, right
         integer :: i
         do i = 1, size(x)
            x(i) = random_triangular(left, mode, right)
         end do
      end subroutine random_triangular_vec

      integer function random_logseries(p)
         ! Source: John Burkardt, prob.f90, log_series_sample.
         real(kind=dp), intent(in) :: p
         real(kind=dp) :: u, v
         if (p <= 0.0_dp .or. p >= 1.0_dp) stop "random_logseries: p must be in (0,1)"
         call random_number(u)
         call random_number(v)
         u = min(max(u, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         v = min(max(v, tiny(1.0_dp)), 1.0_dp - tiny(1.0_dp))
         random_logseries = int(1.0_dp + log(v) / log(1.0_dp - (1.0_dp - p)**u))
      end function random_logseries

      subroutine random_logseries_vec(x, p)
         integer, intent(out) :: x(:)
         real(kind=dp), intent(in) :: p
         integer :: i
         do i = 1, size(x)
            x(i) = random_logseries(p)
         end do
      end subroutine random_logseries_vec

      subroutine random_dirichlet(alpha, x)
         ! Source: John Burkardt, prob.f90, dirichlet_sample.
         real(kind=dp), intent(in) :: alpha(:)
         real(kind=dp), intent(out) :: x(:)
         integer :: i, n
         real(kind=dp) :: s
         n = size(alpha)
         if (size(x) /= n) stop "random_dirichlet: size mismatch"
         do i = 1, n
            if (alpha(i) <= 0.0_dp) stop "random_dirichlet: alpha entries must be > 0"
            x(i) = random_gamma(alpha(i), 1.0_dp)
         end do
         s = sum(x)
         if (s <= tiny(1.0_dp)) stop "random_dirichlet: invalid sample sum"
         x = x / s
      end subroutine random_dirichlet

      subroutine random_dirichlet_samples(alpha, x)
         real(kind=dp), intent(in) :: alpha(:)
         real(kind=dp), intent(out) :: x(:,:)
         integer :: i
         if (size(x, 2) /= size(alpha)) stop "random_dirichlet_samples: second dim must equal len(alpha)"
         do i = 1, size(x, 1)
            call random_dirichlet(alpha, x(i, :))
         end do
      end subroutine random_dirichlet_samples

      subroutine random_multinomial(n, p, x)
         ! Source: John Burkardt, prob.f90, multinomial_sample.
         integer, intent(in) :: n
         real(kind=dp), intent(in) :: p(:)
         integer, intent(out) :: x(:)
         integer :: b, ifactor, ntot
         real(kind=dp), allocatable :: q(:)
         real(kind=dp) :: sum2, prob
         b = size(p)
         if (size(x) /= b) stop "random_multinomial: size mismatch"
         if (n < 0) stop "random_multinomial: n must be >= 0"
         allocate(q(1:b))
         q = max(p, 0.0_dp)
         sum2 = sum(q)
         if (sum2 <= tiny(1.0_dp)) stop "random_multinomial: probabilities must sum to > 0"
         q = q / sum2
         x = 0
         ntot = n
         sum2 = 1.0_dp
         do ifactor = 1, b - 1
            if (ntot <= 0) exit
            prob = q(ifactor) / sum2
            prob = min(max(prob, 0.0_dp), 1.0_dp)
            x(ifactor) = random_binomial(ntot, prob)
            ntot = ntot - x(ifactor)
            sum2 = sum2 - q(ifactor)
            if (sum2 <= tiny(1.0_dp)) exit
         end do
         x(b) = ntot
       end subroutine random_multinomial

      subroutine random_multinomial_samples(n, p, x)
         integer, intent(in) :: n
         real(kind=dp), intent(in) :: p(:)
         integer, intent(out) :: x(:,:)
         integer :: i
         if (size(x, 2) /= size(p)) stop "random_multinomial_samples: second dim must equal len(p)"
         do i = 1, size(x, 1)
            call random_multinomial(n, p, x(i, :))
         end do
      end subroutine random_multinomial_samples

      subroutine random_multivariate_hypergeometric(ngood, nsample, x)
         ! Source: reduction to sequential univariate hypergeometric draws.
         integer, intent(in) :: ngood(:)
         integer, intent(in) :: nsample
         integer, intent(out) :: x(:)
         integer :: i, k, rem_draw, rem_total, rem_bad
         k = size(ngood)
         if (size(x) /= k) stop "random_multivariate_hypergeometric: size mismatch"
         if (k <= 0) stop "random_multivariate_hypergeometric: ngood must be nonempty"
         if (any(ngood < 0)) stop "random_multivariate_hypergeometric: ngood entries must be >= 0"
         rem_total = sum(ngood)
         if (nsample < 0 .or. nsample > rem_total) stop "random_multivariate_hypergeometric: invalid nsample"
         rem_draw = nsample
         x = 0
         do i = 1, k - 1
            rem_bad = rem_total - ngood(i)
            if (rem_draw <= 0) then
               x(i) = 0
            else
               x(i) = random_hypergeometric(ngood(i), rem_bad, rem_draw)
            end if
            rem_draw = rem_draw - x(i)
            rem_total = rem_total - ngood(i)
         end do
         x(k) = rem_draw
      end subroutine random_multivariate_hypergeometric

      subroutine random_multivariate_hypergeometric_samples(ngood, nsample, x)
         integer, intent(in) :: ngood(:)
         integer, intent(in) :: nsample
         integer, intent(out) :: x(:,:)
         integer :: i
         if (size(x,2) /= size(ngood)) stop "random_multivariate_hypergeometric_samples: second dim mismatch"
         do i = 1, size(x,1)
            call random_multivariate_hypergeometric(ngood, nsample, x(i,:))
         end do
      end subroutine random_multivariate_hypergeometric_samples

      pure subroutine vm_integral(a, b, result, dk)
         ! Source: Alan Miller, amiller_mirror/random.f90 (quadrature helper for von Mises).
         real(kind=dp), intent(in) :: a, b, dk
         real(kind=dp), intent(out) :: result
         real(kind=dp) :: xmid, range, x1, x2
         real(kind=dp), parameter :: x(3) = (/ &
            0.238619186083197_dp, 0.661209386466265_dp, 0.932469514203152_dp /)
         real(kind=dp), parameter :: w(3) = (/ &
            0.467913934572691_dp, 0.360761573048139_dp, 0.171324492379170_dp /)
         integer :: i
         xmid = 0.5_dp * (a + b)
         range = 0.5_dp * (b - a)
         result = 0.0_dp
         do i = 1, 3
            x1 = xmid + range * x(i)
            x2 = xmid - range * x(i)
            result = result + w(i) * (exp(dk * cos(x1)) + exp(dk * cos(x2)))
         end do
         result = result * range
      end subroutine vm_integral

      subroutine random_mvn_samples(mean, cov, x)
         real(kind=dp), intent(in) :: mean(:)
         real(kind=dp), intent(in) :: cov(:,:)
         real(kind=dp), intent(out) :: x(:,:)
         integer :: n, p, i, j, info
         real(kind=dp), allocatable :: l(:,:), z(:,:), y(:,:)
         interface
            subroutine dpotrf(uplo, n, a, lda, info)
               character(len=1), intent(in) :: uplo
               integer, intent(in) :: n, lda
               double precision, intent(inout) :: a(lda,*)
               integer, intent(out) :: info
            end subroutine dpotrf
         end interface
         n = size(x, 1)
         p = size(mean)
         if (size(x, 2) /= p) stop "random_mvn_samples: output shape mismatch"
         if (size(cov, 1) /= p .or. size(cov, 2) /= p) stop "random_mvn_samples: covariance shape mismatch"
         allocate(l(p, p))
         l = cov
         call dpotrf('L', p, l, p, info)
         if (info /= 0) stop "random_mvn_samples: covariance not positive definite"
         do i = 1, p
            do j = i + 1, p
               l(i, j) = 0.0_dp
            end do
         end do
         allocate(z(p, n), y(p, n))
         do i = 1, n
            call random_normal_vec(z(:, i))
         end do
         y = matmul(l, z)
         do i = 1, n
            x(i, :) = mean + y(:, i)
         end do
      end subroutine random_mvn_samples

      subroutine random_choice2(p, n, z)
         ! sample n labels in {0,1} with probabilities p(1:2)
         implicit none
         real(kind=dp), intent(in) :: p(:)
         integer, intent(in) :: n
         integer, intent(out) :: z(:)
         integer :: i
         real(kind=dp) :: u, p1, s
         if (size(z) < n) stop "random_choice2: output array too small"
         if (size(p) < 2) stop "random_choice2: p must have at least 2 elements"
         p1 = max(0.0_dp, p(1))
         s = max(0.0_dp, p(1)) + max(0.0_dp, p(2))
         if (s > tiny(1.0_dp)) then
            p1 = p1 / s
         else
            p1 = 0.5_dp
         end if
         do i = 1, n
            call random_number(u)
            if (u < p1) then
               z(i) = 0
            else
               z(i) = 1
            end if
         end do
      end subroutine random_choice2

      subroutine random_choice_norep(npop, nsamp, z)
         integer, intent(in) :: npop, nsamp
         integer, intent(out) :: z(:)
         integer :: i, j, tmp
         real(kind=dp) :: u
         integer, allocatable :: pool(:)
         if (npop < 0 .or. nsamp < 0) stop "random_choice_norep: invalid sizes"
         if (nsamp > npop) stop "random_choice_norep: nsamp > npop"
         if (size(z) < nsamp) stop "random_choice_norep: output array too small"
         if (nsamp == 0) return
         allocate(pool(1:npop))
         do i = 1, npop
            pool(i) = i - 1
         end do
         do i = 1, nsamp
            call random_number(u)
            j = i + int(u * real(npop - i + 1, kind=dp))
            if (j < i) j = i
            if (j > npop) j = npop
            tmp = pool(i)
            pool(i) = pool(j)
            pool(j) = tmp
            z(i) = pool(i)
         end do
         if (allocated(pool)) deallocate(pool)
      end subroutine random_choice_norep

      ! Inverse-CDF weighted sampling against Fortran's own random_number()
      ! stream -- a different algorithm from numpy's Generator.choice(p=...),
      ! so draws are NOT bit-identical to numpy for the same seed. Documented
      ! approximation, same category as this project's BFGS/least_squares/
      ! L-BFGS-B solvers: correct distributionally, not reproducible bit-for-bit.
      subroutine random_choice_prob(p, n, z)
         real(kind=dp), intent(in) :: p(:)
         integer, intent(in) :: n
         integer, intent(out) :: z(:)
         integer :: i, j, k
         real(kind=dp) :: u, s
         real(kind=dp), allocatable :: cdf(:)
         k = size(p)
         if (k <= 0) stop "random_choice_prob: empty probability vector"
         if (size(z) < n) stop "random_choice_prob: output array too small"
         allocate(cdf(1:k))
         s = 0.0_dp
         do j = 1, k
            s = s + max(0.0_dp, p(j))
            cdf(j) = s
         end do
         if (s <= tiny(1.0_dp)) then
            do j = 1, k
               cdf(j) = real(j, kind=dp) / real(k, kind=dp)
            end do
         else
            cdf = cdf / s
         end if
         do i = 1, n
            call random_number(u)
            z(i) = k - 1
            do j = 1, k
               if (u <= cdf(j)) then
                  z(i) = j - 1
                  exit
               end if
            end do
         end do
         if (allocated(cdf)) deallocate(cdf)
      end subroutine random_choice_prob

      pure subroutine sort_real_vec(x)
         ! sort real vector x in ascending order, NaN last (as numpy does).
         real(kind=dp), intent(inout) :: x(:)
         integer :: nn, n
         n = size(x)
         nn = count(ieee_is_nan(x))
         if (nn > 0) then
            x(1:n - nn) = pack(x, .not. ieee_is_nan(x))
            x(n - nn + 1:) = ieee_value(1.0_dp, ieee_quiet_nan)
         end if
         call sort_real_vec_nonan(x(1:n - nn))
      end subroutine sort_real_vec

      pure subroutine sort_real_vec_nonan(x)
         ! sort real vector x (no NaN) in ascending order -- bottom-up iterative
         ! merge sort (O(n log n) worst case). Previously a plain
         ! insertion sort (O(n^2)): fine for the small arrays it was
         ! first written against, but a severe bottleneck for the sizes
         ! quantile_linear/median/unique/etc. actually see in practice
         ! (e.g. ~2.5e9 compare/shift operations sorting a 100,000-
         ! element array, vs ~1.7e6 for this merge sort).
         implicit none
         real(kind=dp), intent(inout) :: x(:)
         real(kind=dp), allocatable :: buf(:)
         integer :: n, width, lo, mid, hi, i, j, k
         n = size(x)
         if (n <= 1) return
         allocate(buf(n))
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n - width)
               mid = lo + width - 1
               hi = min(lo + 2 * width - 1, n)
               i = lo
               j = mid + 1
               k = lo
               do while (i <= mid .and. j <= hi)
                  if (x(i) <= x(j)) then
                     buf(k) = x(i)
                     i = i + 1
                  else
                     buf(k) = x(j)
                     j = j + 1
                  end if
                  k = k + 1
               end do
               do while (i <= mid)
                  buf(k) = x(i)
                  i = i + 1
                  k = k + 1
               end do
               do while (j <= hi)
                  buf(k) = x(j)
                  j = j + 1
                  k = k + 1
               end do
               x(lo:hi) = buf(lo:hi)
               lo = lo + 2 * width
            end do
            width = width * 2
         end do
      end subroutine sort_real_vec_nonan

      pure subroutine sort_int_vec(x)
         ! sort integer vector x in ascending order -- see sort_real_vec
         ! just above for why this is a bottom-up merge sort now, not an
         ! insertion sort.
         implicit none
         integer, intent(inout) :: x(:)
         integer, allocatable :: buf(:)
         integer :: n, width, lo, mid, hi, i, j, k
         n = size(x)
         if (n <= 1) return
         allocate(buf(n))
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n - width)
               mid = lo + width - 1
               hi = min(lo + 2 * width - 1, n)
               i = lo
               j = mid + 1
               k = lo
               do while (i <= mid .and. j <= hi)
                  if (x(i) <= x(j)) then
                     buf(k) = x(i)
                     i = i + 1
                  else
                     buf(k) = x(j)
                     j = j + 1
                  end if
                  k = k + 1
               end do
               do while (i <= mid)
                  buf(k) = x(i)
                  i = i + 1
                  k = k + 1
               end do
               do while (j <= hi)
                  buf(k) = x(j)
                  j = j + 1
                  k = k + 1
               end do
               x(lo:hi) = buf(lo:hi)
               lo = lo + 2 * width
            end do
            width = width * 2
         end do
      end subroutine sort_int_vec

      pure subroutine sort_char_vec(x)
         ! sort character vector x in ascending order -- see
         ! sort_real_vec above for why this is a bottom-up merge sort
         ! now, not an insertion sort.
         implicit none
         character(len=*), intent(inout) :: x(:)
         character(len=len(x)), allocatable :: buf(:)
         integer :: n, width, lo, mid, hi, i, j, k
         n = size(x)
         if (n <= 1) return
         allocate(buf(n))
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n - width)
               mid = lo + width - 1
               hi = min(lo + 2 * width - 1, n)
               i = lo
               j = mid + 1
               k = lo
               do while (i <= mid .and. j <= hi)
                  if (x(i) <= x(j)) then
                     buf(k) = x(i)
                     i = i + 1
                  else
                     buf(k) = x(j)
                     j = j + 1
                  end if
                  k = k + 1
               end do
               do while (i <= mid)
                  buf(k) = x(i)
                  i = i + 1
                  k = k + 1
               end do
               do while (j <= hi)
                  buf(k) = x(j)
                  j = j + 1
                  k = k + 1
               end do
               x(lo:hi) = buf(lo:hi)
               lo = lo + 2 * width
            end do
            width = width * 2
         end do
      end subroutine sort_char_vec

      pure subroutine argsort_real(x, idx)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(out) :: idx(:)
         integer :: i, n
         integer, allocatable :: tmp(:)
         n = size(x)
         if (size(idx) < n) error stop "argsort_real: output array too small"
         do i = 1, n
            idx(i) = i - 1
         end do
         if (n > 1) then
            allocate(tmp(n))
            call argsort_msort_real(x, idx, tmp, 1, n)
         end if
      end subroutine argsort_real

      pure logical function le_nan_last(a, b)
         ! a <= b with NaN after every number (and NaN <= NaN, for stability).
         real(kind=dp), intent(in) :: a, b
         if (ieee_is_nan(b)) then
            le_nan_last = .true.
         else if (ieee_is_nan(a)) then
            le_nan_last = .false.
         else
            le_nan_last = a <= b
         end if
      end function le_nan_last

      pure recursive subroutine argsort_msort_real(x, idx, tmp, lo, hi)
         ! O(n log n) stable merge sort of idx by x(idx(:)+1); insertion
         ! sort here previously made argsort O(n**2), catastrophic for
         ! large n (e.g. sorting a 10**5-element array to seed EM means).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(inout) :: idx(:), tmp(:)
         integer, intent(in) :: lo, hi
         integer :: mid, i, j, k
         if (hi - lo < 1) return
         mid = (lo + hi) / 2
         call argsort_msort_real(x, idx, tmp, lo, mid)
         call argsort_msort_real(x, idx, tmp, mid + 1, hi)
         i = lo
         j = mid + 1
         k = lo
         do while (i <= mid .and. j <= hi)
            if (le_nan_last(x(idx(i) + 1), x(idx(j) + 1))) then
               tmp(k) = idx(i)
               i = i + 1
            else
               tmp(k) = idx(j)
               j = j + 1
            end if
            k = k + 1
         end do
         do while (i <= mid)
            tmp(k) = idx(i)
            i = i + 1
            k = k + 1
         end do
         do while (j <= hi)
            tmp(k) = idx(j)
            j = j + 1
            k = k + 1
         end do
         idx(lo:hi) = tmp(lo:hi)
      end subroutine argsort_msort_real

      pure subroutine argsort_int(x, idx)
         integer, intent(in) :: x(:)
         integer, intent(out) :: idx(:)
         integer :: i, n
         integer, allocatable :: tmp(:)
         n = size(x)
         if (size(idx) < n) error stop "argsort_int: output array too small"
         do i = 1, n
            idx(i) = i - 1
         end do
         if (n > 1) then
            allocate(tmp(n))
            call argsort_msort_int(x, idx, tmp, 1, n)
         end if
      end subroutine argsort_int

      pure recursive subroutine argsort_msort_int(x, idx, tmp, lo, hi)
         ! O(n log n) stable merge sort -- see argsort_msort_real.
         integer, intent(in) :: x(:)
         integer, intent(inout) :: idx(:), tmp(:)
         integer, intent(in) :: lo, hi
         integer :: mid, i, j, k
         if (hi - lo < 1) return
         mid = (lo + hi) / 2
         call argsort_msort_int(x, idx, tmp, lo, mid)
         call argsort_msort_int(x, idx, tmp, mid + 1, hi)
         i = lo
         j = mid + 1
         k = lo
         do while (i <= mid .and. j <= hi)
            if (x(idx(i)+1) <= x(idx(j)+1)) then
               tmp(k) = idx(i)
               i = i + 1
            else
               tmp(k) = idx(j)
               j = j + 1
            end if
            k = k + 1
         end do
         do while (i <= mid)
            tmp(k) = idx(i)
            i = i + 1
            k = k + 1
         end do
         do while (j <= hi)
            tmp(k) = idx(j)
            j = j + 1
            k = k + 1
         end do
         idx(lo:hi) = tmp(lo:hi)
      end subroutine argsort_msort_int

      pure function argsort_idx_real(x) result(idx)
         real(kind=dp), intent(in) :: x(:)
         integer, allocatable :: idx(:)
         allocate(idx(size(x)))
         call argsort_real(x, idx)
      end function argsort_idx_real

      pure function argsort_idx_int(x) result(idx)
         integer, intent(in) :: x(:)
         integer, allocatable :: idx(:)
         allocate(idx(size(x)))
         call argsort_int(x, idx)
      end function argsort_idx_int

      pure function reversed_real_vec(x) result(y)
         ! x[::-1] / np.flip(x) of a vector expression (a function result
         ! can't be subscripted in Fortran).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         y = x(size(x):1:-1)
      end function reversed_real_vec

      pure function reversed_int_vec(x) result(y)
         ! x[::-1] / np.flip(x) of a vector expression (a function result
         ! can't be subscripted in Fortran).
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         y = x(size(x):1:-1)
      end function reversed_int_vec

      pure function reversed_logical_vec(x) result(y)
         ! x[::-1] / np.flip(x) of a vector expression (a function result
         ! can't be subscripted in Fortran).
         logical, intent(in) :: x(:)
         logical, allocatable :: y(:)
         y = x(size(x):1:-1)
      end function reversed_logical_vec

      pure function np_amin_r1(x) result(r)
         ! np.min: NaN if x holds a NaN (numpy propagates it).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: r
         if (any(ieee_is_nan(x))) then
            r = ieee_value(1.0_dp, ieee_quiet_nan)
         else
            r = minval(x)
         end if
      end function np_amin_r1

      pure function np_amin_r2(x) result(r)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp) :: r
         if (any(ieee_is_nan(x))) then
            r = ieee_value(1.0_dp, ieee_quiet_nan)
         else
            r = minval(x)
         end if
      end function np_amin_r2

      pure function np_amin_r2_dim(x, dim) result(r)
         ! Along dimension dim, NaN where that column (row) holds a NaN.
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = np_amin_r1(x(:, i))
            else
               r(i) = np_amin_r1(x(i, :))
            end if
         end do
      end function np_amin_r2_dim

      pure function np_amax_r1(x) result(r)
         ! np.max: NaN if x holds a NaN (numpy propagates it).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: r
         if (any(ieee_is_nan(x))) then
            r = ieee_value(1.0_dp, ieee_quiet_nan)
         else
            r = maxval(x)
         end if
      end function np_amax_r1

      pure function np_amax_r2(x) result(r)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp) :: r
         if (any(ieee_is_nan(x))) then
            r = ieee_value(1.0_dp, ieee_quiet_nan)
         else
            r = maxval(x)
         end if
      end function np_amax_r2

      pure function np_amax_r2_dim(x, dim) result(r)
         ! Along dimension dim, NaN where that column (row) holds a NaN.
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = np_amax_r1(x(:, i))
            else
               r(i) = np_amax_r1(x(i, :))
            end if
         end do
      end function np_amax_r2_dim

      pure function np_argmin_r1(x) result(r)
         ! np.argmin (0-based): the first NaN if x holds one, as numpy does.
         real(kind=dp), intent(in) :: x(:)
         integer :: r
         if (any(ieee_is_nan(x))) then
            r = findloc(ieee_is_nan(x), .true., dim=1) - 1
         else
            r = minloc(x, dim=1) - 1
         end if
      end function np_argmin_r1

      pure function np_argmin_r2_dim(x, dim) result(r)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = np_argmin_r1(x(:, i))
            else
               r(i) = np_argmin_r1(x(i, :))
            end if
         end do
      end function np_argmin_r2_dim

      pure function np_argmax_r1(x) result(r)
         ! np.argmax (0-based): the first NaN if x holds one, as numpy does.
         real(kind=dp), intent(in) :: x(:)
         integer :: r
         if (any(ieee_is_nan(x))) then
            r = findloc(ieee_is_nan(x), .true., dim=1) - 1
         else
            r = maxloc(x, dim=1) - 1
         end if
      end function np_argmax_r1

      pure function np_argmax_r2_dim(x, dim) result(r)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = np_argmax_r1(x(:, i))
            else
               r(i) = np_argmax_r1(x(i, :))
            end if
         end do
      end function np_argmax_r2_dim

      elemental function np_maximum(a, b) result(r)
         ! np.maximum: NaN if either is NaN.
         real(kind=dp), intent(in) :: a, b
         real(kind=dp) :: r
         if (ieee_is_nan(a)) then
            r = a
         else if (ieee_is_nan(b)) then
            r = b
         else
            r = max(a, b)
         end if
      end function np_maximum

      elemental function np_minimum(a, b) result(r)
         ! np.minimum: NaN if either is NaN.
         real(kind=dp), intent(in) :: a, b
         real(kind=dp) :: r
         if (ieee_is_nan(a)) then
            r = a
         else if (ieee_is_nan(b)) then
            r = b
         else
            r = min(a, b)
         end if
      end function np_minimum

      elemental function np_clip(x, lo, hi) result(r)
         ! np.clip: NaN stays NaN.
         real(kind=dp), intent(in) :: x, lo, hi
         real(kind=dp) :: r
         if (ieee_is_nan(x)) then
            r = x
         else
            r = min(max(x, lo), hi)
         end if
      end function np_clip

      elemental function np_floor(x) result(r)
         ! np.floor of a float: NaN and infinities unchanged, no integer
         ! conversion (which overflows for large values).
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: r
         r = x
         if (ieee_is_nan(x)) return
         if (.not. ieee_is_finite(x)) return
         r = aint(x)
         if (r > x) r = r - 1.0_dp
      end function np_floor

      elemental function np_ceil(x) result(r)
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: r
         r = x
         if (ieee_is_nan(x)) return
         if (.not. ieee_is_finite(x)) return
         r = aint(x)
         if (r < x) r = r + 1.0_dp
      end function np_ceil

      elemental function np_sign(x) result(r)
         ! np.sign of a float: -1, 0 or 1, NaN for NaN.
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: r
         if (ieee_is_nan(x)) then
            r = x
         else if (x > 0.0_dp) then
            r = 1.0_dp
         else if (x < 0.0_dp) then
            r = -1.0_dp
         else
            r = 0.0_dp
         end if
      end function np_sign

      pure function sort_axis_3d_real(x, dim) result(out)
         ! np.sort(x, axis=dim-1) of a rank-3 array: sorted_vec along dim.
         real(kind=dp), intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = sorted_vec(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = sorted_vec(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = sorted_vec(x(i, j, :))
               end do
            end do
         end select
      end function sort_axis_3d_real

      pure function sort_axis_3d_int(x, dim) result(out)
         ! np.sort(x, axis=dim-1) of a rank-3 array: sorted_vec along dim.
         integer, intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = sorted_vec(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = sorted_vec(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = sorted_vec(x(i, j, :))
               end do
            end do
         end select
      end function sort_axis_3d_int

      pure function argsort_axis_3d_real(x, dim) result(out)
         ! np.argsort(x, axis=dim-1) of a rank-3 array: argsort_idx along dim.
         real(kind=dp), intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = argsort_idx(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = argsort_idx(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = argsort_idx(x(i, j, :))
               end do
            end do
         end select
      end function argsort_axis_3d_real

      pure function argsort_axis_3d_int(x, dim) result(out)
         ! np.argsort(x, axis=dim-1) of a rank-3 array: argsort_idx along dim.
         integer, intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = argsort_idx(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = argsort_idx(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = argsort_idx(x(i, j, :))
               end do
            end do
         end select
      end function argsort_axis_3d_int

      pure function cumsum_axis_3d_real(x, dim) result(out)
         ! np.cumsum(x, axis=dim-1) of a rank-3 array: cumsum_real along dim.
         real(kind=dp), intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = cumsum_real(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = cumsum_real(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = cumsum_real(x(i, j, :))
               end do
            end do
         end select
      end function cumsum_axis_3d_real

      pure function cumsum_axis_3d_int(x, dim) result(out)
         ! np.cumsum(x, axis=dim-1) of a rank-3 array: cumsum_int along dim.
         integer, intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = cumsum_int(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = cumsum_int(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = cumsum_int(x(i, j, :))
               end do
            end do
         end select
      end function cumsum_axis_3d_int

      pure function cumprod_axis_3d_real(x, dim) result(out)
         ! np.cumprod(x, axis=dim-1) of a rank-3 array: cumprod_real along dim.
         real(kind=dp), intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = cumprod_real(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = cumprod_real(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = cumprod_real(x(i, j, :))
               end do
            end do
         end select
      end function cumprod_axis_3d_real

      pure function cumprod_axis_3d_int(x, dim) result(out)
         ! np.cumprod(x, axis=dim-1) of a rank-3 array: cumprod_int along dim.
         integer, intent(in) :: x(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: i, j
         allocate(out(size(x,1), size(x,2), size(x,3)))
         select case (dim)
         case (1)
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(:, i, j) = cumprod_int(x(:, i, j))
               end do
            end do
         case (2)
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, :, j) = cumprod_int(x(i, :, j))
               end do
            end do
         case default
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j, :) = cumprod_int(x(i, j, :))
               end do
            end do
         end select
      end function cumprod_axis_3d_int

      pure function trace_3d_real(x) result(out)
         ! np.trace of a rank-3 array: sum of x[i, i, :] over i.
         real(kind=dp), intent(in) :: x(:,:,:)
         real(kind=dp), allocatable :: out(:)
         integer :: i
         allocate(out(size(x,3)))
         out = 0
         do i = 1, min(size(x,1), size(x,2))
            out = out + x(i, i, :)
         end do
      end function trace_3d_real

      pure function trace_3d_int(x) result(out)
         ! np.trace of a rank-3 array: sum of x[i, i, :] over i.
         integer, intent(in) :: x(:,:,:)
         integer, allocatable :: out(:)
         integer :: i
         allocate(out(size(x,3)))
         out = 0
         do i = 1, min(size(x,1), size(x,2))
            out = out + x(i, i, :)
         end do
      end function trace_3d_int

      pure function concat_3d_real(a, b, dim) result(out)
         ! np.concatenate([a, b], axis=dim-1) of rank-3 arrays.
         real(kind=dp), intent(in) :: a(:,:,:), b(:,:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:,:)
         integer :: n(3)
         n = shape(a)
         n(dim) = n(dim) + size(b, dim)
         allocate(out(n(1), n(2), n(3)))
         select case (dim)
         case (1)
            out(:size(a,1), :, :) = a
            out(size(a,1)+1:, :, :) = b
         case (2)
            out(:, :size(a,2), :) = a
            out(:, size(a,2)+1:, :) = b
         case default
            out(:, :, :size(a,3)) = a
            out(:, :, size(a,3)+1:) = b
         end select
      end function concat_3d_real

      pure function concat_3d_int(a, b, dim) result(out)
         ! np.concatenate([a, b], axis=dim-1) of rank-3 arrays.
         integer, intent(in) :: a(:,:,:), b(:,:,:)
         integer, intent(in) :: dim
         integer, allocatable :: out(:,:,:)
         integer :: n(3)
         n = shape(a)
         n(dim) = n(dim) + size(b, dim)
         allocate(out(n(1), n(2), n(3)))
         select case (dim)
         case (1)
            out(:size(a,1), :, :) = a
            out(size(a,1)+1:, :, :) = b
         case (2)
            out(:, :size(a,2), :) = a
            out(:, size(a,2)+1:, :) = b
         case default
            out(:, :, :size(a,3)) = a
            out(:, :, size(a,3)+1:) = b
         end select
      end function concat_3d_int

      pure function nonzero_3d(mask, k) result(idx)
         ! np.nonzero(x)[k-1] of a rank-3 array (mask = x /= 0): the
         ! 0-based axis-k indices of the true elements, in C (row-major) order.
         logical, intent(in) :: mask(:,:,:)
         integer, intent(in) :: k
         integer, allocatable :: idx(:)
         integer :: i, j, l, m
         allocate(idx(count(mask)))
         m = 0
         do i = 1, size(mask,1)
            do j = 1, size(mask,2)
               do l = 1, size(mask,3)
                  if (mask(i, j, l)) then
                     m = m + 1
                     select case (k)
                     case (1)
                        idx(m) = i - 1
                     case (2)
                        idx(m) = j - 1
                     case default
                        idx(m) = l - 1
                     end select
                  end if
               end do
            end do
         end do
      end function nonzero_3d

      elemental logical function c_lt(a, b)
         ! numpy's ordering of complex numbers: by real part, then imaginary part.
         complex(kind=dp), intent(in) :: a, b
         if (real(a, kind=dp) == real(b, kind=dp)) then
            c_lt = aimag(a) < aimag(b)
         else
            c_lt = real(a, kind=dp) < real(b, kind=dp)
         end if
      end function c_lt

      elemental logical function c_le(a, b)
         ! numpy's ordering of complex numbers: by real part, then imaginary
         ! part, a NaN after every number (as np.sort places them).
         complex(kind=dp), intent(in) :: a, b
         real(kind=dp) :: ra, rb, ia, ib
         ra = real(a, kind=dp)
         rb = real(b, kind=dp)
         ia = aimag(a)
         ib = aimag(b)
         if (ieee_is_nan(ra) .neqv. ieee_is_nan(rb)) then
            c_le = ieee_is_nan(rb)
         else if (.not. ieee_is_nan(ra) .and. ra /= rb) then
            c_le = ra < rb
         else if (ieee_is_nan(ia) .neqv. ieee_is_nan(ib)) then
            c_le = ieee_is_nan(ib)
         else if (ieee_is_nan(ia)) then
            c_le = .true.
         else
            c_le = ia <= ib
         end if
      end function c_le

      elemental logical function c_gt(a, b)
         ! numpy's ordering of complex numbers: by real part, then imaginary part.
         complex(kind=dp), intent(in) :: a, b
         if (real(a, kind=dp) == real(b, kind=dp)) then
            c_gt = aimag(a) > aimag(b)
         else
            c_gt = real(a, kind=dp) > real(b, kind=dp)
         end if
      end function c_gt

      elemental logical function c_ge(a, b)
         ! numpy's ordering of complex numbers: by real part, then imaginary part.
         complex(kind=dp), intent(in) :: a, b
         if (real(a, kind=dp) == real(b, kind=dp)) then
            c_ge = aimag(a) >= aimag(b)
         else
            c_ge = real(a, kind=dp) > real(b, kind=dp)
         end if
      end function c_ge

      elemental function c_maximum(a, b) result(r)
         ! np.maximum of complex numbers (lexicographic).
         complex(kind=dp), intent(in) :: a, b
         complex(kind=dp) :: r
         r = merge(b, a, c_lt(a, b))
      end function c_maximum

      elemental function c_minimum(a, b) result(r)
         complex(kind=dp), intent(in) :: a, b
         complex(kind=dp) :: r
         r = merge(b, a, c_gt(a, b))
      end function c_minimum

      elemental function c_round(z, d) result(r)
         ! np.round of a complex number: both parts, half to even.
         complex(kind=dp), intent(in) :: z
         integer, intent(in) :: d
         complex(kind=dp) :: r
         real(kind=dp) :: s
         s = 10.0_dp**d
         r = cmplx(anint_even(real(z, kind=dp) * s) / s, anint_even(aimag(z) * s) / s, kind=dp)
      contains
         elemental real(kind=dp) function anint_even(x)
            real(kind=dp), intent(in) :: x
            anint_even = anint(x)
            if (abs(x - aint(x)) == 0.5_dp) anint_even = 2.0_dp * anint(x / 2.0_dp)
         end function anint_even
      end function c_round

      pure function c_amin_r1(x) result(r)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp) :: r
         integer :: i
         r = x(1)
         do i = 2, size(x)
            if (c_lt(x(i), r)) r = x(i)
         end do
      end function c_amin_r1

      pure function c_amin_r2(x) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         complex(kind=dp) :: r
         r = c_amin_r1(reshape(x, [size(x)]))
      end function c_amin_r2

      pure function c_amin_r2_dim(x, dim) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = c_amin_r1(x(:, i))
            else
               r(i) = c_amin_r1(x(i, :))
            end if
         end do
      end function c_amin_r2_dim

      pure function c_amax_r1(x) result(r)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp) :: r
         integer :: i
         r = x(1)
         do i = 2, size(x)
            if (c_gt(x(i), r)) r = x(i)
         end do
      end function c_amax_r1

      pure function c_amax_r2(x) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         complex(kind=dp) :: r
         r = c_amax_r1(reshape(x, [size(x)]))
      end function c_amax_r2

      pure function c_amax_r2_dim(x, dim) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = c_amax_r1(x(:, i))
            else
               r(i) = c_amax_r1(x(i, :))
            end if
         end do
      end function c_amax_r2_dim

      pure function c_argmin_r1(x) result(r)
         ! np.argmin (0-based) of complex numbers, the first extreme value.
         complex(kind=dp), intent(in) :: x(:)
         integer :: r, i
         r = 1
         do i = 2, size(x)
            if (c_lt(x(i), x(r))) r = i
         end do
         r = r - 1
      end function c_argmin_r1

      pure function c_argmin_r2_dim(x, dim) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = c_argmin_r1(x(:, i))
            else
               r(i) = c_argmin_r1(x(i, :))
            end if
         end do
      end function c_argmin_r2_dim

      pure function c_argmax_r1(x) result(r)
         ! np.argmax (0-based) of complex numbers, the first extreme value.
         complex(kind=dp), intent(in) :: x(:)
         integer :: r, i
         r = 1
         do i = 2, size(x)
            if (c_gt(x(i), x(r))) r = i
         end do
         r = r - 1
      end function c_argmax_r1

      pure function c_argmax_r2_dim(x, dim) result(r)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: r(:)
         integer :: i
         allocate(r(size(x, 3 - dim)))
         do i = 1, size(r)
            if (dim == 1) then
               r(i) = c_argmax_r1(x(:, i))
            else
               r(i) = c_argmax_r1(x(i, :))
            end if
         end do
      end function c_argmax_r2_dim

      pure function cumsum_complex(x) result(y)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x)))
         if (size(x) == 0) return
         y(1) = x(1)
         do i = 2, size(x)
            y(i) = y(i - 1) + x(i)
         end do
      end function cumsum_complex

      pure function cumsum_complex_2d(x, dim) result(y)
         ! np.cumsum(x, axis=dim-1) of a complex matrix.
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: y(:,:)
         integer :: i
         allocate(y(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               y(:, i) = cumsum_complex(x(:, i))
            end do
         else
            do i = 1, size(x,1)
               y(i, :) = cumsum_complex(x(i, :))
            end do
         end if
      end function cumsum_complex_2d

      pure function cumprod_complex(x) result(y)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x)))
         if (size(x) == 0) return
         y(1) = x(1)
         do i = 2, size(x)
            y(i) = y(i - 1) * x(i)
         end do
      end function cumprod_complex

      pure function cumprod_complex_2d(x, dim) result(y)
         ! np.cumprod(x, axis=dim-1) of a complex matrix.
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: y(:,:)
         integer :: i
         allocate(y(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               y(:, i) = cumprod_complex(x(:, i))
            end do
         else
            do i = 1, size(x,1)
               y(i, :) = cumprod_complex(x(i, :))
            end do
         end if
      end function cumprod_complex_2d

      pure function argsort_complex_vec(x) result(idx)
         ! np.argsort (0-based, stable) of complex numbers in numpy's
         ! lexicographic order -- an insertion-free bottom-up merge sort.
         complex(kind=dp), intent(in) :: x(:)
         integer, allocatable :: idx(:)
         integer, allocatable :: tmp(:)
         integer :: n, width, lo, mid, hi, i, j, k
         n = size(x)
         allocate(idx(n), tmp(n))
         idx = [(i, i = 1, n)]
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n)
               mid = min(lo + width - 1, n)
               hi = min(lo + 2 * width - 1, n)
               i = lo
               j = mid + 1
               k = lo
               do while (i <= mid .and. j <= hi)
                  if (c_le(x(idx(i)), x(idx(j)))) then
                     tmp(k) = idx(i)
                     i = i + 1
                  else
                     tmp(k) = idx(j)
                     j = j + 1
                  end if
                  k = k + 1
               end do
               do while (i <= mid)
                  tmp(k) = idx(i)
                  i = i + 1
                  k = k + 1
               end do
               do while (j <= hi)
                  tmp(k) = idx(j)
                  j = j + 1
                  k = k + 1
               end do
               lo = lo + 2 * width
            end do
            idx = tmp
            width = 2 * width
         end do
         idx = idx - 1
      end function argsort_complex_vec

      pure function sorted_complex_vec(x) result(y)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         y = x(argsort_complex_vec(x) + 1)
      end function sorted_complex_vec

      pure subroutine sort_complex_vec(x)
         ! x.sort() of a complex vector.
         complex(kind=dp), intent(inout) :: x(:)
         x = x(argsort_complex_vec(x) + 1)
      end subroutine sort_complex_vec

      pure function sorted_complex_2d(x, dim) result(y)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: y(:,:)
         integer :: i
         allocate(y(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               y(:, i) = sorted_complex_vec(x(:, i))
            end do
         else
            do i = 1, size(x,1)
               y(i, :) = sorted_complex_vec(x(i, :))
            end do
         end if
      end function sorted_complex_2d

      pure function argsort_complex_2d(x, dim) result(idx)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: idx(:,:)
         integer :: i
         allocate(idx(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               idx(:, i) = argsort_complex_vec(x(:, i))
            end do
         else
            do i = 1, size(x,1)
               idx(i, :) = argsort_complex_vec(x(i, :))
            end do
         end if
      end function argsort_complex_2d

      pure function unique_complex(x) result(y)
         ! np.unique of complex numbers: sorted, duplicates removed.
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: s(:)
         logical, allocatable :: keep(:)
         s = sorted_complex_vec(x)
         allocate(keep(size(s)))
         if (size(s) > 0) keep(1) = .true.
         if (size(s) > 1) keep(2:) = s(2:) /= s(:size(s)-1)
         y = pack(s, keep)
      end function unique_complex

      pure function median_complex(x) result(m)
         ! np.median of complex numbers: the middle of the lexicographic
         ! order (the mean of the two middle values for an even count).
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp) :: m
         complex(kind=dp), allocatable :: s(:)
         integer :: n
         n = size(x)
         s = sorted_complex_vec(x)
         if (mod(n, 2) == 1) then
            m = s((n + 1) / 2)
         else
            m = (s(n / 2) + s(n / 2 + 1)) / 2.0_dp
         end if
      end function median_complex

      pure function median_complex_2d(x, dim) result(m)
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: m(:)
         integer :: i
         allocate(m(size(x, 3 - dim)))
         do i = 1, size(m)
            if (dim == 1) then
               m(i) = median_complex(x(:, i))
            else
               m(i) = median_complex(x(i, :))
            end if
         end do
      end function median_complex_2d

      pure function reversed_complex_vec(x) result(y)
         ! x[::-1] of a complex vector expression.
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         y = x(size(x):1:-1)
      end function reversed_complex_vec

      pure function reversed_real_mat(x, dim) result(y)
         ! np.flip(x, axis) of a matrix expression: dim 1 reverses the rows
         ! (axis=0), 2 the columns (axis=1), 0 both (axis=None).
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: y(:,:)
         select case (dim)
         case (1)
            y = x(size(x, 1):1:-1, :)
         case (2)
            y = x(:, size(x, 2):1:-1)
         case default
            y = x(size(x, 1):1:-1, size(x, 2):1:-1)
         end select
      end function reversed_real_mat

      pure function reversed_int_mat(x, dim) result(y)
         ! np.flip(x, axis) of a matrix expression: dim 1 reverses the rows
         ! (axis=0), 2 the columns (axis=1), 0 both (axis=None).
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: y(:,:)
         select case (dim)
         case (1)
            y = x(size(x, 1):1:-1, :)
         case (2)
            y = x(:, size(x, 2):1:-1)
         case default
            y = x(size(x, 1):1:-1, size(x, 2):1:-1)
         end select
      end function reversed_int_mat

      pure function reversed_logical_mat(x, dim) result(y)
         ! np.flip(x, axis) of a matrix expression: dim 1 reverses the rows
         ! (axis=0), 2 the columns (axis=1), 0 both (axis=None).
         logical, intent(in) :: x(:,:)
         integer, intent(in) :: dim
         logical, allocatable :: y(:,:)
         select case (dim)
         case (1)
            y = x(size(x, 1):1:-1, :)
         case (2)
            y = x(:, size(x, 2):1:-1)
         case default
            y = x(size(x, 1):1:-1, size(x, 2):1:-1)
         end select
      end function reversed_logical_mat

      pure function reversed_complex_mat(x, dim) result(y)
         ! np.flip(x, axis) of a matrix expression: dim 1 reverses the rows
         ! (axis=0), 2 the columns (axis=1), 0 both (axis=None).
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         complex(kind=dp), allocatable :: y(:,:)
         select case (dim)
         case (1)
            y = x(size(x, 1):1:-1, :)
         case (2)
            y = x(:, size(x, 2):1:-1)
         case default
            y = x(size(x, 1):1:-1, size(x, 2):1:-1)
         end select
      end function reversed_complex_mat

      pure function repeat_complex(x, reps) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: reps
         complex(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x) * reps))
         do i = 1, size(x)
            y((i - 1) * reps + 1:i * reps) = x(i)
         end do
      end function repeat_complex

      pure function tile_complex(x, reps) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: reps
         complex(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x) * reps))
         do i = 1, reps
            y((i - 1) * size(x) + 1:i * size(x)) = x
         end do
      end function tile_complex

      pure function diag_k_vec_complex(v, k) result(a)
         ! np.diag(v, k) of a complex vector.
         complex(kind=dp), intent(in) :: v(:)
         integer, intent(in) :: k
         complex(kind=dp), allocatable :: a(:,:)
         integer :: n, i
         n = size(v) + abs(k)
         allocate(a(n, n))
         a = (0.0_dp, 0.0_dp)
         do i = 1, size(v)
            if (k >= 0) then
               a(i, i + k) = v(i)
            else
               a(i - k, i) = v(i)
            end if
         end do
      end function diag_k_vec_complex

      pure function diag_k_mat_complex(a, k) result(v)
         ! np.diag(a, k) of a complex matrix: its k-th diagonal.
         complex(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: k
         complex(kind=dp), allocatable :: v(:)
         integer :: n, i
         if (k >= 0) then
            n = max(0, min(size(a,1), size(a,2) - k))
         else
            n = max(0, min(size(a,1) + k, size(a,2)))
         end if
         allocate(v(n))
         do i = 1, n
            if (k >= 0) then
               v(i) = a(i, i + k)
            else
               v(i) = a(i - k, i)
            end if
         end do
      end function diag_k_mat_complex

      pure function np_searchsorted_real(a, v, right) result(idx)
         ! np.searchsorted(a, v, side): 0-based insertion index of v in the
         ! sorted vector a (before equal values, or after them if right);
         ! NaN sorts after every number, as in numpy.
         real(kind=dp), intent(in) :: a(:), v
         logical, intent(in) :: right
         integer :: idx, lo, hi, mid
         logical :: goes_before
         lo = 0
         hi = size(a)
         do while (lo < hi)
            mid = (lo + hi) / 2
            if (ieee_is_nan(a(mid + 1))) then
               goes_before = right .and. ieee_is_nan(v)
            else if (ieee_is_nan(v)) then
               goes_before = .true.
            else
               goes_before = a(mid + 1) < v .or. (right .and. a(mid + 1) == v)
            end if
            if (goes_before) then
               lo = mid + 1
            else
               hi = mid
            end if
         end do
         idx = lo
      end function np_searchsorted_real

      pure function np_searchsorted_real_vec(a, v, right) result(idx)
         real(kind=dp), intent(in) :: a(:), v(:)
         logical, intent(in) :: right
         integer, allocatable :: idx(:)
         integer :: i
         allocate(idx(size(v)))
         do i = 1, size(v)
            idx(i) = np_searchsorted_real(a, v(i), right)
         end do
      end function np_searchsorted_real_vec

      pure function np_isin1_real(a, b) result(mask)
         ! a(i) in b for each element of the vector a.
         real(kind=dp), intent(in) :: a(:), b(:)
         logical, allocatable :: mask(:)
         integer :: i
         allocate(mask(size(a)))
         do i = 1, size(a)
            mask(i) = any(b == a(i))
         end do
      end function np_isin1_real

      pure function np_union1d_real(a, b) result(c)
         ! np.union1d of vectors: sorted, without duplicates.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         c = unique_real([a, b])
      end function np_union1d_real

      pure function np_intersect1d_real(a, b) result(c)
         ! np.intersect1d of vectors: sorted, without duplicates.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         c = unique_real(pack(a, np_isin1_real(a, b)))
      end function np_intersect1d_real

      pure function np_setdiff1d_real(a, b) result(c)
         ! np.setdiff1d of vectors: sorted, without duplicates.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         c = unique_real(pack(a, .not. np_isin1_real(a, b)))
      end function np_setdiff1d_real

      pure function np_setxor1d_real(a, b) result(c)
         ! np.setxor1d of vectors: sorted, without duplicates.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         c = unique_real([a, b])
         c = pack(c, .not. (np_isin1_real(c, a) .and. np_isin1_real(c, b)))
      end function np_setxor1d_real

      elemental logical function eq_nan_real(a, b)
         ! a == b, with every NaN equal to every NaN (numpy's unique).
         real(kind=dp), intent(in) :: a, b
         if (ieee_is_nan(a) .or. ieee_is_nan(b)) then
            eq_nan_real = ieee_is_nan(a) .and. ieee_is_nan(b)
         else
            eq_nan_real = a == b
         end if
      end function eq_nan_real

      pure function np_unique_counts_real(x) result(r)
         ! np.unique(x, return_counts=True)[1] of a vector (0-based indices).
         real(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         real(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_real(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = count(eq_nan_real(x, u(i)))
         end do
      end function np_unique_counts_real

      pure function np_unique_index_real(x) result(r)
         ! np.unique(x, return_index=True)[1] of a vector (0-based indices).
         real(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         real(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_real(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = findloc(eq_nan_real(x, u(i)), .true., dim=1) - 1
         end do
      end function np_unique_index_real

      pure function np_unique_inverse_real(x) result(r)
         ! np.unique(x, return_inverse=True)[1] of a vector (0-based indices).
         real(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         real(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_real(x)
         allocate(r(size(x)))
         do i = 1, size(x)
            r(i) = findloc(eq_nan_real(u, x(i)), .true., dim=1) - 1
         end do
      end function np_unique_inverse_real

      pure function np_searchsorted_int(a, v, right) result(idx)
         ! np.searchsorted(a, v, side): 0-based insertion index of v in the
         ! sorted vector a (before equal values, or after them if right).
         integer, intent(in) :: a(:), v
         logical, intent(in) :: right
         integer :: idx, lo, hi, mid
         lo = 0
         hi = size(a)
         do while (lo < hi)
            mid = (lo + hi) / 2
            if (a(mid + 1) < v .or. (right .and. a(mid + 1) == v)) then
               lo = mid + 1
            else
               hi = mid
            end if
         end do
         idx = lo
      end function np_searchsorted_int

      pure function np_searchsorted_int_vec(a, v, right) result(idx)
         integer, intent(in) :: a(:), v(:)
         logical, intent(in) :: right
         integer, allocatable :: idx(:)
         integer :: i
         allocate(idx(size(v)))
         do i = 1, size(v)
            idx(i) = np_searchsorted_int(a, v(i), right)
         end do
      end function np_searchsorted_int_vec

      pure function np_isin1_int(a, b) result(mask)
         ! a(i) in b for each element of the vector a.
         integer, intent(in) :: a(:), b(:)
         logical, allocatable :: mask(:)
         integer :: i
         allocate(mask(size(a)))
         do i = 1, size(a)
            mask(i) = any(b == a(i))
         end do
      end function np_isin1_int

      pure function np_union1d_int(a, b) result(c)
         ! np.union1d of vectors: sorted, without duplicates.
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         c = unique_int([a, b])
      end function np_union1d_int

      pure function np_intersect1d_int(a, b) result(c)
         ! np.intersect1d of vectors: sorted, without duplicates.
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         c = unique_int(pack(a, np_isin1_int(a, b)))
      end function np_intersect1d_int

      pure function np_setdiff1d_int(a, b) result(c)
         ! np.setdiff1d of vectors: sorted, without duplicates.
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         c = unique_int(pack(a, .not. np_isin1_int(a, b)))
      end function np_setdiff1d_int

      pure function np_setxor1d_int(a, b) result(c)
         ! np.setxor1d of vectors: sorted, without duplicates.
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         c = unique_int([a, b])
         c = pack(c, .not. (np_isin1_int(c, a) .and. np_isin1_int(c, b)))
      end function np_setxor1d_int

      pure function np_unique_counts_int(x) result(r)
         ! np.unique(x, return_counts=True)[1] of a vector (0-based indices).
         integer, intent(in) :: x(:)
         integer, allocatable :: r(:)
         integer, allocatable :: u(:)
         integer :: i
         u = unique_int(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = count(x == u(i))
         end do
      end function np_unique_counts_int

      pure function np_unique_index_int(x) result(r)
         ! np.unique(x, return_index=True)[1] of a vector (0-based indices).
         integer, intent(in) :: x(:)
         integer, allocatable :: r(:)
         integer, allocatable :: u(:)
         integer :: i
         u = unique_int(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = findloc(x, u(i), dim=1) - 1
         end do
      end function np_unique_index_int

      pure function np_unique_inverse_int(x) result(r)
         ! np.unique(x, return_inverse=True)[1] of a vector (0-based indices).
         integer, intent(in) :: x(:)
         integer, allocatable :: r(:)
         integer, allocatable :: u(:)
         integer :: i
         u = unique_int(x)
         allocate(r(size(x)))
         do i = 1, size(x)
            r(i) = findloc(u, x(i), dim=1) - 1
         end do
      end function np_unique_inverse_int

      pure function np_gather2d_real(m, i, j) result(r)
         ! m[i, j] with integer index vectors i, j (0-based, negative from
         ! the end): [m[i[0], j[0]], m[i[1], j[1]], ...].
         real(kind=dp), intent(in) :: m(:,:)
         integer, intent(in) :: i(:), j(:)
         real(kind=dp), allocatable :: r(:)
         integer :: k, ii, jj
         allocate(r(size(i)))
         do k = 1, size(i)
            ii = i(k)
            jj = j(k)
            if (ii < 0) ii = ii + size(m, 1)
            if (jj < 0) jj = jj + size(m, 2)
            r(k) = m(ii + 1, jj + 1)
         end do
      end function np_gather2d_real

      pure function np_gather2d_int(m, i, j) result(r)
         ! m[i, j] with integer index vectors i, j (0-based, negative from
         ! the end): [m[i[0], j[0]], m[i[1], j[1]], ...].
         integer, intent(in) :: m(:,:)
         integer, intent(in) :: i(:), j(:)
         integer, allocatable :: r(:)
         integer :: k, ii, jj
         allocate(r(size(i)))
         do k = 1, size(i)
            ii = i(k)
            jj = j(k)
            if (ii < 0) ii = ii + size(m, 1)
            if (jj < 0) jj = jj + size(m, 2)
            r(k) = m(ii + 1, jj + 1)
         end do
      end function np_gather2d_int

      pure function np_gather2d_log(m, i, j) result(r)
         ! m[i, j] with integer index vectors i, j (0-based, negative from
         ! the end): [m[i[0], j[0]], m[i[1], j[1]], ...].
         logical, intent(in) :: m(:,:)
         integer, intent(in) :: i(:), j(:)
         logical, allocatable :: r(:)
         integer :: k, ii, jj
         allocate(r(size(i)))
         do k = 1, size(i)
            ii = i(k)
            jj = j(k)
            if (ii < 0) ii = ii + size(m, 1)
            if (jj < 0) jj = jj + size(m, 2)
            r(k) = m(ii + 1, jj + 1)
         end do
      end function np_gather2d_log

      pure function np_gather2d_complex(m, i, j) result(r)
         ! m[i, j] with integer index vectors i, j (0-based, negative from
         ! the end): [m[i[0], j[0]], m[i[1], j[1]], ...].
         complex(kind=dp), intent(in) :: m(:,:)
         integer, intent(in) :: i(:), j(:)
         complex(kind=dp), allocatable :: r(:)
         integer :: k, ii, jj
         allocate(r(size(i)))
         do k = 1, size(i)
            ii = i(k)
            jj = j(k)
            if (ii < 0) ii = ii + size(m, 1)
            if (jj < 0) jj = jj + size(m, 2)
            r(k) = m(ii + 1, jj + 1)
         end do
      end function np_gather2d_complex

      pure function np_bincount_weights(x, w, minlength) result(c)
         ! np.bincount(x, weights=w, minlength=...): c(v+1) = sum of w where x == v.
         integer, intent(in) :: x(:)
         real(kind=dp), intent(in) :: w(:)
         integer, intent(in) :: minlength
         real(kind=dp), allocatable :: c(:)
         integer :: i, n
         n = minlength
         if (size(x) > 0) n = max(n, maxval(x) + 1)
         allocate(c(n))
         c = 0.0_dp
         do i = 1, size(x)
            c(x(i) + 1) = c(x(i) + 1) + w(i)
         end do
      end function np_bincount_weights

      pure integer function np_digitize_scalar(x, bins, right) result(r)
         ! np.digitize(x, bins, right): for increasing bins the i with
         ! bins[i-1] <= x < bins[i] (bins[i-1] < x <= bins[i] if right), for
         ! decreasing bins numpy's len(bins) - searchsorted(bins[::-1], x);
         ! bins that are neither are an error, as in numpy.
         real(kind=dp), intent(in) :: x
         real(kind=dp), intent(in) :: bins(:)
         logical, intent(in) :: right
         integer :: n, k
         logical :: incr
         n = size(bins)
         incr = .true.
         if (n > 1) then
            if (all(bins(2:) >= bins(:n - 1))) then
               incr = .true.
            else if (all(bins(2:) <= bins(:n - 1))) then
               incr = .false.
            else
               error stop "np.digitize: bins must be monotonically increasing or decreasing"
            end if
         end if
         if (ieee_is_nan(x)) then
            ! NaN sorts after every bin edge.
            k = n
         else if (right) then
            k = count(bins < x)
         else
            k = count(bins <= x)
         end if
         if (incr) then
            r = k
         else
            r = n - k
         end if
      end function np_digitize_scalar

      elemental function np_spacing(x) result(s)
         ! np.spacing(x): the distance from x to the next float away from 0,
         ! with the sign of x (spacing(0) is the smallest subnormal; NaN for
         ! inf and NaN).
         use, intrinsic :: ieee_arithmetic, only: ieee_next_after
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: s
         if (ieee_is_nan(x) .or. .not. ieee_is_finite(x)) then
            s = ieee_value(1.0_dp, ieee_quiet_nan)
         else if (x < 0.0_dp) then
            s = ieee_next_after(x, -huge(x)) - x
         else
            s = ieee_next_after(x, huge(x)) - x
         end if
      end function np_spacing

      elemental integer function np_pad_index(i, n, mode) result(j)
         ! The 0-based index into a vector of size n that position i (0 is
         ! its first element, i < 0 before it, i >= n after it) of np.pad
         ! takes: mode 1 'edge', 2 'wrap', 3 'reflect' (mirror without the
         ! edge element), 4 'symmetric' (mirror with it).
         integer, intent(in) :: i, n, mode
         integer :: per
         select case (mode)
         case (1)
            j = min(max(i, 0), n - 1)
         case (2)
            j = modulo(i, n)
         case (3)
            if (n == 1) then
               j = 0
            else
               per = 2 * n - 2
               j = modulo(i, per)
               if (j >= n) j = per - j
            end if
         case default
            per = 2 * n
            j = modulo(i, per)
            if (j >= n) j = per - 1 - j
         end select
      end function np_pad_index

      pure function np_pad_indices(n, before, after, mode) result(idx)
         ! The 1-based indices into a vector of size n that np.pad(x,
         ! (before, after), mode) takes (mode as for np_pad_index).
         integer, intent(in) :: n, before, after, mode
         integer, allocatable :: idx(:)
         integer :: i
         allocate(idx(n + before + after))
         do i = 1, size(idx)
            idx(i) = np_pad_index(i - 1 - before, n, mode) + 1
         end do
      end function np_pad_indices

      pure function np_pad_vec_real(x, before, after, mode) result(y)
         ! np.pad(x, (before, after), mode) of a vector (mode as for
         ! np_pad_index).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: before, after, mode
         real(kind=dp), allocatable :: y(:)
         y = x(np_pad_indices(size(x), before, after, mode))
      end function np_pad_vec_real

      pure function np_pad_vec_int(x, before, after, mode) result(y)
         ! np.pad(x, (before, after), mode) of a vector (mode as for
         ! np_pad_index).
         integer, intent(in) :: x(:)
         integer, intent(in) :: before, after, mode
         integer, allocatable :: y(:)
         y = x(np_pad_indices(size(x), before, after, mode))
      end function np_pad_vec_int

      pure function np_pad_vec_complex(x, before, after, mode) result(y)
         ! np.pad(x, (before, after), mode) of a vector (mode as for
         ! np_pad_index).
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: before, after, mode
         complex(kind=dp), allocatable :: y(:)
         y = x(np_pad_indices(size(x), before, after, mode))
      end function np_pad_vec_complex

      pure function np_pad_vec_logical(x, before, after, mode) result(y)
         ! np.pad(x, (before, after), mode) of a vector (mode as for
         ! np_pad_index).
         logical, intent(in) :: x(:)
         integer, intent(in) :: before, after, mode
         logical, allocatable :: y(:)
         y = x(np_pad_indices(size(x), before, after, mode))
      end function np_pad_vec_logical

      pure function np_packbits(bits, little) result(y)
         ! np.packbits of a flat logical array: groups of 8 bits as integers
         ! 0..255, the first bit the most significant (the least if
         ! little), the last group padded with zero bits.
         logical, intent(in) :: bits(:)
         logical, intent(in) :: little
         integer, allocatable :: y(:)
         integer :: i, b
         allocate(y((size(bits) + 7) / 8), source=0)
         do i = 1, size(bits)
            if (.not. bits(i)) cycle
            b = mod(i - 1, 8)
            if (.not. little) b = 7 - b
            y((i - 1) / 8 + 1) = ibset(y((i - 1) / 8 + 1), b)
         end do
      end function np_packbits

      pure function np_unpackbits(x, little, count) result(bits)
         ! np.unpackbits of a flat array of integers 0..255: 8 bits each
         ! (0 or 1), the most significant first (the least if little);
         ! count keeps the first count bits (count < 0: drops -count; more
         ! than 8*size(x) pads with zeros).
         integer, intent(in) :: x(:)
         logical, intent(in) :: little
         integer, intent(in), optional :: count
         integer, allocatable :: bits(:)
         integer :: i, j, n, b
         n = 8 * size(x)
         if (present(count)) then
            if (count >= 0) then
               n = count
            else
               n = max(0, n + count)
            end if
         end if
         allocate(bits(n), source=0)
         do i = 1, min(n, 8 * size(x))
            j = (i - 1) / 8 + 1
            b = mod(i - 1, 8)
            if (.not. little) b = 7 - b
            if (btest(x(j), b)) bits(i) = 1
         end do
      end function np_unpackbits

      elemental function np_nan_to_num(x, nan, posinf, neginf) result(y)
         ! np.nan_to_num(x, nan=, posinf=, neginf=): NaN, +inf and -inf
         ! replaced (no ordered comparison of a NaN, which would raise the
         ! invalid-operation flag).
         real(kind=dp), intent(in) :: x, nan, posinf, neginf
         real(kind=dp) :: y
         if (ieee_is_nan(x)) then
            y = nan
         else if (ieee_is_finite(x)) then
            y = x
         else if (x > 0.0_dp) then
            y = posinf
         else
            y = neginf
         end if
      end function np_nan_to_num

      elemental function np_heaviside(x, h0) result(y)
         ! np.heaviside(x, h0): 0 for x < 0, h0 at 0, 1 for x > 0, NaN at NaN.
         real(kind=dp), intent(in) :: x, h0
         real(kind=dp) :: y
         if (ieee_is_nan(x)) then
            y = x
         else if (x < 0.0_dp) then
            y = 0.0_dp
         else if (x > 0.0_dp) then
            y = 1.0_dp
         else
            y = h0
         end if
      end function np_heaviside

      pure function np_corrcoef_1(x) result(r)
         ! np.corrcoef of one vector: 1, or NaN for a constant or non-finite
         ! vector (var / sqrt(var * var)).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: r
         r = ieee_value(1.0_dp, ieee_quiet_nan)
         if (size(x) == 0) return
         if (.not. all(ieee_is_finite(x))) return
         if (maxval(x) > minval(x)) r = 1.0_dp
      end function np_corrcoef_1

      elemental function np_chkfinite(x) result(y)
         ! np.asarray_chkfinite(x): x, or an error if it is inf or NaN.
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y
         if (.not. ieee_is_finite(x)) error stop "array must not contain infs or NaNs"
         y = x
      end function np_chkfinite

      pure function np_digitize_vec(x, bins, right) result(r)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in) :: bins(:)
         logical, intent(in) :: right
         integer, allocatable :: r(:)
         integer :: i
         allocate(r(size(x)))
         do i = 1, size(x)
            r(i) = np_digitize_scalar(x(i), bins, right)
         end do
      end function np_digitize_vec

      pure function np_isin1_complex(a, b) result(mask)
         complex(kind=dp), intent(in) :: a(:), b(:)
         logical, allocatable :: mask(:)
         integer :: i
         allocate(mask(size(a)))
         do i = 1, size(a)
            mask(i) = any(b == a(i))
         end do
      end function np_isin1_complex

      pure function np_union1d_complex(a, b) result(c)
         complex(kind=dp), intent(in) :: a(:), b(:)
         complex(kind=dp), allocatable :: c(:)
         c = unique_complex([a, b])
      end function np_union1d_complex

      pure function np_intersect1d_complex(a, b) result(c)
         complex(kind=dp), intent(in) :: a(:), b(:)
         complex(kind=dp), allocatable :: c(:)
         c = unique_complex(pack(a, np_isin1_complex(a, b)))
      end function np_intersect1d_complex

      pure function np_setdiff1d_complex(a, b) result(c)
         complex(kind=dp), intent(in) :: a(:), b(:)
         complex(kind=dp), allocatable :: c(:)
         c = unique_complex(pack(a, .not. np_isin1_complex(a, b)))
      end function np_setdiff1d_complex

      pure function np_setxor1d_complex(a, b) result(c)
         complex(kind=dp), intent(in) :: a(:), b(:)
         complex(kind=dp), allocatable :: c(:)
         c = unique_complex([a, b])
         c = pack(c, .not. (np_isin1_complex(c, a) .and. np_isin1_complex(c, b)))
      end function np_setxor1d_complex

      pure function np_unique_counts_complex(x) result(r)
         complex(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         complex(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_complex(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = count(x == u(i))
         end do
      end function np_unique_counts_complex

      pure function np_unique_index_complex(x) result(r)
         complex(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         complex(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_complex(x)
         allocate(r(size(u)))
         do i = 1, size(u)
            r(i) = findloc(x == u(i), .true., dim=1) - 1
         end do
      end function np_unique_index_complex

      pure function np_unique_inverse_complex(x) result(r)
         complex(kind=dp), intent(in) :: x(:)
         integer, allocatable :: r(:)
         complex(kind=dp), allocatable :: u(:)
         integer :: i
         u = unique_complex(x)
         allocate(r(size(x)))
         do i = 1, size(x)
            r(i) = findloc(u == x(i), .true., dim=1) - 1
         end do
      end function np_unique_inverse_complex

      pure function np_kron2_int(a, b) result(r)
         ! np.kron of two matrices.
         integer, intent(in) :: a(:,:), b(:,:)
         integer, allocatable :: r(:,:)
         integer :: i, j, rb, cb
         rb = size(b, 1)
         cb = size(b, 2)
         allocate(r(size(a, 1) * rb, size(a, 2) * cb))
         r = 0
         do j = 1, size(a, 2)
            do i = 1, size(a, 1)
               r((i - 1) * rb + 1:i * rb, (j - 1) * cb + 1:j * cb) = a(i, j) * b
            end do
         end do
      end function np_kron2_int

      pure function np_cross3_int(a, b) result(c)
         ! np.cross of two 3-vectors.
         integer, intent(in) :: a(:), b(:)
         integer :: c(3)
         c = [a(2) * b(3) - a(3) * b(2), a(3) * b(1) - a(1) * b(3), a(1) * b(2) - a(2) * b(1)]
      end function np_cross3_int

      pure function np_kron2_real(a, b) result(r)
         ! np.kron of two matrices.
         real(kind=dp), intent(in) :: a(:,:), b(:,:)
         real(kind=dp), allocatable :: r(:,:)
         integer :: i, j, rb, cb
         rb = size(b, 1)
         cb = size(b, 2)
         allocate(r(size(a, 1) * rb, size(a, 2) * cb))
         r = 0.0_dp
         do j = 1, size(a, 2)
            do i = 1, size(a, 1)
               r((i - 1) * rb + 1:i * rb, (j - 1) * cb + 1:j * cb) = a(i, j) * b
            end do
         end do
      end function np_kron2_real

      pure function np_cross3_real(a, b) result(c)
         ! np.cross of two 3-vectors.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp) :: c(3)
         c = [a(2) * b(3) - a(3) * b(2), a(3) * b(1) - a(1) * b(3), a(1) * b(2) - a(2) * b(1)]
      end function np_cross3_real

      pure function np_kron2_complex(a, b) result(r)
         ! np.kron of two matrices.
         complex(kind=dp), intent(in) :: a(:,:), b(:,:)
         complex(kind=dp), allocatable :: r(:,:)
         integer :: i, j, rb, cb
         rb = size(b, 1)
         cb = size(b, 2)
         allocate(r(size(a, 1) * rb, size(a, 2) * cb))
         r = (0.0_dp, 0.0_dp)
         do j = 1, size(a, 2)
            do i = 1, size(a, 1)
               r((i - 1) * rb + 1:i * rb, (j - 1) * cb + 1:j * cb) = a(i, j) * b
            end do
         end do
      end function np_kron2_complex

      pure function np_cross3_complex(a, b) result(c)
         ! np.cross of two 3-vectors.
         complex(kind=dp), intent(in) :: a(:), b(:)
         complex(kind=dp) :: c(3)
         c = [a(2) * b(3) - a(3) * b(2), a(3) * b(1) - a(1) * b(3), a(1) * b(2) - a(2) * b(1)]
      end function np_cross3_complex

      function matrix_normm2_real(a) result(value)
         ! np.linalg.norm(a, -2): the smallest singular value.
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp) :: value
         real(kind=dp), allocatable :: u(:,:), s(:), vt(:,:)
         if (min(size(a,1), size(a,2)) == 0) error stop "matrix_norm: empty matrix"
         call linalg_svd_econ(a, u, s, vt)
         value = minval(s)
      end function matrix_normm2_real

      function stack_inv(a) result(r)
         ! numpy's stacked (batched) linear algebra: linalg_inv(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:), m(:,:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, size(a, 3), size(a, 2)))
            return
         end if
         do b = 1, size(a, 1)
            m = linalg_inv(a(b, :, :))
            if (b == 1) allocate(r(size(a, 1), size(m, 1), size(m, 2)))
            r(b, :, :) = m
         end do
      end function stack_inv

      function stack_cholesky(a) result(r)
         ! numpy's stacked (batched) linear algebra: linalg_cholesky(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:), m(:,:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, size(a, 3), size(a, 2)))
            return
         end if
         do b = 1, size(a, 1)
            m = linalg_cholesky(a(b, :, :))
            if (b == 1) allocate(r(size(a, 1), size(m, 1), size(m, 2)))
            r(b, :, :) = m
         end do
      end function stack_cholesky

      function stack_pinv(a) result(r)
         ! numpy's stacked (batched) linear algebra: linalg_pinv(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:), m(:,:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, size(a, 3), size(a, 2)))
            return
         end if
         do b = 1, size(a, 1)
            m = linalg_pinv(a(b, :, :))
            if (b == 1) allocate(r(size(a, 1), size(m, 1), size(m, 2)))
            r(b, :, :) = m
         end do
      end function stack_pinv

      function stack_matrix_power(a, p) result(r)
         ! numpy's stacked (batched) linear algebra: linalg_matrix_power(A, p) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         integer, intent(in) :: p
         real(kind=dp), allocatable :: r(:,:,:), m(:,:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, size(a, 3), size(a, 2)))
            return
         end if
         do b = 1, size(a, 1)
            m = linalg_matrix_power(a(b, :, :), p)
            if (b == 1) allocate(r(size(a, 1), size(m, 1), size(m, 2)))
            r(b, :, :) = m
         end do
      end function stack_matrix_power

      function stack_det(a) result(r)
         ! numpy's stacked linear algebra: linalg_det(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = linalg_det(a(b, :, :))
         end do
      end function stack_det

      function stack_cond(a) result(r)
         ! numpy's stacked linear algebra: linalg_cond(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = linalg_cond(a(b, :, :))
         end do
      end function stack_cond

      function stack_matrix_rank(a) result(r)
         ! numpy's stacked linear algebra: linalg_matrix_rank(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         integer, allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = linalg_matrix_rank(a(b, :, :))
         end do
      end function stack_matrix_rank

      function stack_norm2(a) result(r)
         ! numpy's stacked linear algebra: matrix_norm2_real(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = matrix_norm2_real(a(b, :, :))
         end do
      end function stack_norm2

      function stack_normm2(a) result(r)
         ! numpy's stacked linear algebra: matrix_normm2_real(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = matrix_normm2_real(a(b, :, :))
         end do
      end function stack_normm2

      function stack_eigvalsh(a) result(r)
         ! numpy's stacked linear algebra: linalg_eigvalsh(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:,:), w(:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, min(size(a, 2), size(a, 3))))
            return
         end if
         do b = 1, size(a, 1)
            w = linalg_eigvalsh(a(b, :, :))
            if (b == 1) allocate(r(size(a, 1), size(w)))
            r(b, :) = w
         end do
      end function stack_eigvalsh

      function stack_eigvals(a) result(r)
         ! numpy's stacked linear algebra: linalg_eigvals_real(A) of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         complex(kind=dp), allocatable :: r(:,:), w(:)
         integer :: b
         if (size(a, 1) == 0) then
            allocate(r(0, min(size(a, 2), size(a, 3))))
            return
         end if
         do b = 1, size(a, 1)
            w = linalg_eigvals_real(a(b, :, :))
            if (b == 1) allocate(r(size(a, 1), size(w)))
            r(b, :) = w
         end do
      end function stack_eigvals

      pure function stack_trace(a) result(r)
         ! np.linalg.trace of a stack: the trace of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b, i
         allocate(r(size(a, 1)))
         r = 0.0_dp
         do b = 1, size(a, 1)
            do i = 1, min(size(a, 2), size(a, 3))
               r(b) = r(b) + a(b, i, i)
            end do
         end do
      end function stack_trace

      pure function stack_diagonal(a) result(r)
         ! np.linalg.diagonal of a stack: the diagonal of each a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:,:)
         integer :: b, i
         allocate(r(size(a, 1), min(size(a, 2), size(a, 3))))
         do b = 1, size(a, 1)
            do i = 1, size(r, 2)
               r(b, i) = a(b, i, i)
            end do
         end do
      end function stack_diagonal

      pure function stack_fro(a) result(r)
         ! The Frobenius norm of each a(b,:,:) (norm(a, axis=(-2, -1))).
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable :: r(:)
         integer :: b
         allocate(r(size(a, 1)))
         do b = 1, size(a, 1)
            r(b) = sqrt(sum(a(b, :, :)**2))
         end do
      end function stack_fro

      function stack_solve_v(a, x) result(r)
         ! np.linalg.solve(a, x) with a 1-D x: solve each a(b,:,:) y = x.
         real(kind=dp), intent(in) :: a(:,:,:), x(:)
         real(kind=dp), allocatable :: r(:,:)
         integer :: b
         allocate(r(size(a, 1), size(x)))
         do b = 1, size(a, 1)
            r(b, :) = linalg_solve_vec(a(b, :, :), x)
         end do
      end function stack_solve_v

      function stack_solve_m(a, x) result(r)
         ! np.linalg.solve(a, x) with a matrix x, used for every a(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:), x(:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         integer :: b
         allocate(r(size(a, 1), size(x, 1), size(x, 2)))
         do b = 1, size(a, 1)
            r(b, :, :) = linalg_solve_mat(a(b, :, :), x)
         end do
      end function stack_solve_m

      function stack_solve_s(a, x) result(r)
         ! np.linalg.solve(a, x) of two stacks: a(b,:,:) y = x(b,:,:).
         real(kind=dp), intent(in) :: a(:,:,:), x(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         integer :: b
         allocate(r(size(x, 1), size(x, 2), size(x, 3)))
         do b = 1, size(a, 1)
            r(b, :, :) = linalg_solve_mat(a(b, :, :), x(b, :, :))
         end do
      end function stack_solve_s

      pure function stack_matmul_ss(a, x) result(r)
         ! a @ x of two stacks of matrices.
         real(kind=dp), intent(in) :: a(:,:,:), x(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         integer :: b
         allocate(r(size(a, 1), size(a, 2), size(x, 3)))
         do b = 1, size(a, 1)
            r(b, :, :) = matmul(a(b, :, :), x(b, :, :))
         end do
      end function stack_matmul_ss

      pure function stack_matmul_sm(a, x) result(r)
         ! a @ x of a stack and a matrix.
         real(kind=dp), intent(in) :: a(:,:,:), x(:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         integer :: b
         allocate(r(size(a, 1), size(a, 2), size(x, 2)))
         do b = 1, size(a, 1)
            r(b, :, :) = matmul(a(b, :, :), x)
         end do
      end function stack_matmul_sm

      pure function stack_matmul_ms(a, x) result(r)
         ! a @ x of a matrix and a stack.
         real(kind=dp), intent(in) :: a(:,:), x(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         integer :: b
         allocate(r(size(x, 1), size(a, 1), size(x, 3)))
         do b = 1, size(x, 1)
            r(b, :, :) = matmul(a, x(b, :, :))
         end do
      end function stack_matmul_ms

      pure function stack_matmul_sv(a, x) result(r)
         ! a @ x of a stack and a vector.
         real(kind=dp), intent(in) :: a(:,:,:), x(:)
         real(kind=dp), allocatable :: r(:,:)
         integer :: b
         allocate(r(size(a, 1), size(a, 2)))
         do b = 1, size(a, 1)
            r(b, :) = matmul(a(b, :, :), x)
         end do
      end function stack_matmul_sv

      pure function stack_matmul_vs(a, x) result(r)
         ! a @ x of a vector and a stack.
         real(kind=dp), intent(in) :: a(:), x(:,:,:)
         real(kind=dp), allocatable :: r(:,:)
         integer :: b
         allocate(r(size(x, 1), size(x, 3)))
         do b = 1, size(x, 1)
            r(b, :) = matmul(a, x(b, :, :))
         end do
      end function stack_matmul_vs

      subroutine stack_eigh(a, w, v)
         ! w, v = np.linalg.eigh(a) of a stack.
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable, intent(out) :: w(:,:), v(:,:,:)
         real(kind=dp), allocatable :: wb(:), vb(:,:)
         integer :: b
         allocate(w(size(a, 1), size(a, 2)), v(size(a, 1), size(a, 2), size(a, 3)))
         do b = 1, size(a, 1)
            call linalg_eigh(a(b, :, :), wb, vb)
            w(b, :) = wb
            v(b, :, :) = vb
         end do
      end subroutine stack_eigh

      subroutine stack_eig(a, w, v)
         ! w, v = np.linalg.eig(a) of a stack.
         real(kind=dp), intent(in) :: a(:,:,:)
         complex(kind=dp), allocatable, intent(out) :: w(:,:), v(:,:,:)
         complex(kind=dp), allocatable :: wb(:), vb(:,:)
         integer :: b
         allocate(w(size(a, 1), size(a, 2)), v(size(a, 1), size(a, 2), size(a, 3)))
         do b = 1, size(a, 1)
            call linalg_eig(a(b, :, :), wb, vb)
            w(b, :) = wb
            v(b, :, :) = vb
         end do
      end subroutine stack_eig

      subroutine stack_qr(a, q, r)
         ! q, r = np.linalg.qr(a) (reduced) of a stack.
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable, intent(out) :: q(:,:,:), r(:,:,:)
         real(kind=dp), allocatable :: qb(:,:), rb(:,:)
         integer :: b, k
         k = min(size(a, 2), size(a, 3))
         allocate(q(size(a, 1), size(a, 2), k), r(size(a, 1), k, size(a, 3)))
         do b = 1, size(a, 1)
            call linalg_qr_reduced(a(b, :, :), qb, rb)
            q(b, :, :) = qb
            r(b, :, :) = rb
         end do
      end subroutine stack_qr

      subroutine stack_svd(a, u, s, vt)
         ! u, s, vt = np.linalg.svd(a) of a stack.
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable, intent(out) :: u(:,:,:), s(:,:), vt(:,:,:)
         real(kind=dp), allocatable :: ub(:,:), sb(:), vtb(:,:)
         integer :: b, k
         k = min(size(a, 2), size(a, 3))
         allocate(u(size(a, 1), size(a, 2), size(a, 2)), s(size(a, 1), k), vt(size(a, 1), size(a, 3), size(a, 3)))
         do b = 1, size(a, 1)
            call linalg_svd(a(b, :, :), ub, sb, vtb)
            u(b, :, :) = ub
            s(b, :) = sb
            vt(b, :, :) = vtb
         end do
      end subroutine stack_svd

      subroutine stack_svd_econ(a, u, s, vt)
         ! u, s, vt = np.linalg.svd(a, full_matrices=False) of a stack.
         real(kind=dp), intent(in) :: a(:,:,:)
         real(kind=dp), allocatable, intent(out) :: u(:,:,:), s(:,:), vt(:,:,:)
         real(kind=dp), allocatable :: ub(:,:), sb(:), vtb(:,:)
         integer :: b, k
         k = min(size(a, 2), size(a, 3))
         allocate(u(size(a, 1), size(a, 2), k), s(size(a, 1), k), vt(size(a, 1), k, size(a, 3)))
         do b = 1, size(a, 1)
            call linalg_svd_econ(a(b, :, :), ub, sb, vtb)
            u(b, :, :) = ub
            s(b, :) = sb
            vt(b, :, :) = vtb
         end do
      end subroutine stack_svd_econ

      logical function rng_take_values(rank, n0, n1, x)
         ! Under RNG replay, read the next recorded "values" call (numpy's
         ! own results) into x and return .true.; otherwise .false.
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), intent(out) :: x(:)
         call rng_replay_expect("values", rank, n0, n1)
         rng_take_values = rng_replay_enabled
         if (rng_replay_enabled .and. size(x) > 0) read(rng_replay_bin_u) x
      end function rng_take_values

      function rng_unit_uniform() result(u)
         ! One uniform draw in [0, 1) from Fortran's generator.
         real(kind=dp) :: u
         call random_number(u)
      end function rng_unit_uniform

      function rng_std_normal1() result(z)
         real(kind=dp) :: z
         real(kind=dp) :: v(1)
         call random_normal_vec(v)
         z = v(1)
      end function rng_std_normal1

      recursive function rng_std_gamma1(k) result(g)
         ! Marsaglia-Tsang; k < 1 by boosting.
         real(kind=dp), intent(in) :: k
         real(kind=dp) :: g, d, c, z, v, u
         if (k <= 0.0_dp) then
            g = 0.0_dp
            return
         end if
         if (k < 1.0_dp) then
            call random_number(u)
            g = rng_std_gamma1(k + 1.0_dp) * u**(1.0_dp / k)
            return
         end if
         d = k - 1.0_dp / 3.0_dp
         c = 1.0_dp / sqrt(9.0_dp * d)
         do
            z = rng_std_normal1()
            v = (1.0_dp + c * z)**3
            if (v <= 0.0_dp) cycle
            call random_number(u)
            if (log(max(u, tiny(1.0_dp))) < 0.5_dp * z * z + d - d * v + d * log(v)) exit
         end do
         g = d * v
      end function rng_std_gamma1

      function rng_integers_v(lo, hi, rank, n0, n1) result(x)
         ! integers in [lo, hi): numpy's rng.integers / np.random.randint.
         integer, intent(in) :: lo, hi, rank, n0, n1
         integer, allocatable :: x(:)
         real(kind=dp), allocatable :: v(:)
         integer :: i
         if (hi <= lo) error stop "integers: low >= high"
         allocate(v(max(n0, 1) * max(n1, 1)))
         if (rank == 1) deallocate(v)
         if (rank == 1) allocate(v(n0))
         if (rank == 2) deallocate(v)
         if (rank == 2) allocate(v(n0 * n1))
         allocate(x(size(v)))
         if (rng_take_values(rank, n0, n1, v)) then
            x = nint(v)
            return
         end if
         call random_number(v)
         do i = 1, size(x)
            x(i) = lo + min(int(v(i) * real(hi - lo, kind=dp)), hi - lo - 1)
         end do
      end function rng_integers_v

      function rng_choice_idx(npop, rank, n0, n1, replace) result(idx)
         ! 0-based indices of rng.choice(npop, size, replace).
         integer, intent(in) :: npop, rank, n0, n1
         logical, intent(in) :: replace
         integer, allocatable :: idx(:), pool(:)
         real(kind=dp), allocatable :: v(:)
         integer :: i, j, n, tmp
         n = merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)
         allocate(v(n), idx(n))
         if (rng_take_values(rank, n0, n1, v)) then
            idx = nint(v)
            return
         end if
         if (replace) then
            call random_number(v)
            do i = 1, n
               idx(i) = min(int(v(i) * real(npop, kind=dp)), npop - 1)
            end do
         else
            if (n > npop) error stop "choice: cannot take a larger sample than population when replace=False"
            allocate(pool(npop))
            pool = [(i - 1, i = 1, npop)]
            do i = 1, n
               call random_number(v(i))
               j = i + min(int(v(i) * real(npop - i + 1, kind=dp)), npop - i)
               tmp = pool(i)
               pool(i) = pool(j)
               pool(j) = tmp
            end do
            idx = pool(1:n)
         end if
      end function rng_choice_idx

      function rng_choice_idx_p(pr, rank, n0, n1, replace) result(idx)
         ! 0-based indices of rng.choice(len(p), size, replace, p=pr).
         real(kind=dp), intent(in) :: pr(:)
         integer, intent(in) :: rank, n0, n1
         logical, intent(in) :: replace
         integer, allocatable :: idx(:)
         real(kind=dp), allocatable :: v(:), w(:)
         real(kind=dp) :: u, acc, tot
         integer :: i, j, n
         n = merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)
         allocate(v(n), idx(n))
         if (rng_take_values(rank, n0, n1, v)) then
            idx = nint(v)
            return
         end if
         w = pr
         do i = 1, n
            tot = sum(w)
            if (tot <= 0.0_dp) error stop "choice: probabilities exhausted"
            call random_number(u)
            u = u * tot
            acc = 0.0_dp
            idx(i) = size(w) - 1
            do j = 1, size(w)
               acc = acc + w(j)
               if (u < acc) then
                  idx(i) = j - 1
                  exit
               end if
            end do
            if (.not. replace) w(idx(i) + 1) = 0.0_dp
         end do
      end function rng_choice_idx_p

      function rng_permutation_idx(n) result(idx)
         ! A random permutation of 0 .. n-1 (rng.permutation / shuffle order).
         integer, intent(in) :: n
         integer, allocatable :: idx(:)
         real(kind=dp), allocatable :: v(:)
         integer :: i, j, tmp
         real(kind=dp) :: u
         allocate(v(n), idx(n))
         if (rng_take_values(1, n, -1, v)) then
            idx = nint(v)
            return
         end if
         idx = [(i - 1, i = 1, n)]
         do i = n, 2, -1
            call random_number(u)
            j = 1 + min(int(u * real(i, kind=dp)), i - 1)
            tmp = idx(i)
            idx(i) = idx(j)
            idx(j) = tmp
         end do
      end function rng_permutation_idx

      function rng_mvnormal(mean, cov, n) result(x)
         ! rng.multivariate_normal(mean, cov, size=n): row i is mean + L z.
         real(kind=dp), intent(in) :: mean(:), cov(:,:)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: x(:,:), l(:,:), z(:), flat(:)
         integer :: i, d
         d = size(mean)
         allocate(x(n, d), z(d), flat(n * d))
         if (rng_take_values(2, n, d, flat)) then
            x = reshape(flat, [n, d])
            return
         end if
         l = linalg_cholesky(cov)
         do i = 1, n
            call random_normal_vec(z)
            x(i, :) = mean + matmul(l, z)
         end do
      end function rng_mvnormal

      function rng_exponential_v(scale, rank, n0, n1) result(x)
         ! numpy's exponential draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: scale
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = -scale * log(1.0_dp - u)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_exponential_v

      function rng_lognormal_v(mean, sigma, rank, n0, n1) result(x)
         ! numpy's lognormal draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: mean, sigma
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = exp(mean + sigma * rng_std_normal1())
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_lognormal_v

      function rng_gamma_v(shape, scale, rank, n0, n1) result(x)
         ! numpy's gamma draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: shape, scale
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = scale * rng_std_gamma1(shape)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_gamma_v

      function rng_beta_v(a, b, rank, n0, n1) result(x)
         ! numpy's beta draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: a, b
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = beta_draw(a, b)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_beta_v

      function rng_chisquare_v(df, rank, n0, n1) result(x)
         ! numpy's chisquare draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: df
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = 2.0_dp * rng_std_gamma1(0.5_dp * df)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_chisquare_v

      function rng_laplace_v(loc, scale, rank, n0, n1) result(x)
         ! numpy's laplace draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: loc, scale
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = loc - scale * sign(1.0_dp, u - 0.5_dp) * log(1.0_dp - 2.0_dp * abs(u - 0.5_dp))
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_laplace_v

      function rng_logistic_v(loc, scale, rank, n0, n1) result(x)
         ! numpy's logistic draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: loc, scale
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = loc + scale * log(max(u, tiny(1.0_dp)) / (1.0_dp - u))
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_logistic_v

      function rng_standard_t_v(df, rank, n0, n1) result(x)
         ! numpy's standard_t draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: df
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = rng_std_normal1() / sqrt(2.0_dp * rng_std_gamma1(0.5_dp * df) / df)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_standard_t_v

      function rng_triangular_v(left, mode, right, rank, n0, n1) result(x)
         ! numpy's triangular draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: left, mode, right
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = triangular_draw(left, mode, right, u)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_triangular_v

      function rng_weibull_v(a, rank, n0, n1) result(x)
         ! numpy's weibull draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: a
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = (-log(1.0_dp - u))**(1.0_dp / a)
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_weibull_v

      function rng_pareto_v(a, rank, n0, n1) result(x)
         ! numpy's pareto draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: a
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = (1.0_dp - u)**(-1.0_dp / a) - 1.0_dp
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_pareto_v

      function rng_rayleigh_v(scale, rank, n0, n1) result(x)
         ! numpy's rayleigh draws (rank 0/1/2 of n0 x n1, flattened column-major).
         real(kind=dp), intent(in) :: scale
         integer, intent(in) :: rank, n0, n1
         real(kind=dp), allocatable :: x(:)
         real(kind=dp) :: u
         integer :: i
         allocate(x(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         if (rng_take_values(rank, n0, n1, x)) return
         do i = 1, size(x)
            call random_number(u)
            x(i) = scale * sqrt(-2.0_dp * log(1.0_dp - u))
         end do
      contains
         function beta_draw(aa, bb) result(r)
            real(kind=dp), intent(in) :: aa, bb
            real(kind=dp) :: r, g1, g2
            g1 = rng_std_gamma1(aa)
            g2 = rng_std_gamma1(bb)
            r = g1 / (g1 + g2)
         end function beta_draw
         function triangular_draw(lft, md, rgt, uu) result(r)
            real(kind=dp), intent(in) :: lft, md, rgt, uu
            real(kind=dp) :: r
            if (uu < (md - lft) / (rgt - lft)) then
               r = lft + sqrt(uu * (rgt - lft) * (md - lft))
            else
               r = rgt - sqrt((1.0_dp - uu) * (rgt - lft) * (rgt - md))
            end if
         end function triangular_draw
      end function rng_rayleigh_v

      function rng_poisson_v(lam, rank, n0, n1) result(x)
         ! numpy's poisson draws: Knuth for small lam, otherwise a normal
         ! approximation-free inversion by summing exponential gaps.
         real(kind=dp), intent(in) :: lam
         integer, intent(in) :: rank, n0, n1
         integer, allocatable :: x(:)
         real(kind=dp), allocatable :: v(:)
         real(kind=dp) :: s, u
         integer :: i, k
         allocate(v(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         allocate(x(size(v)))
         if (rng_take_values(rank, n0, n1, v)) then
            x = nint(v)
            return
         end if
         do i = 1, size(x)
            k = 0
            s = 0.0_dp
            do
               call random_number(u)
               s = s - log(1.0_dp - u)
               if (s > lam) exit
               k = k + 1
            end do
            x(i) = k
         end do
      end function rng_poisson_v

      function rng_binomial_v(nt, pp, rank, n0, n1) result(x)
         ! numpy's binomial draws (sum of nt Bernoulli trials).
         integer, intent(in) :: nt
         real(kind=dp), intent(in) :: pp
         integer, intent(in) :: rank, n0, n1
         integer, allocatable :: x(:)
         real(kind=dp), allocatable :: v(:), u(:)
         integer :: i
         allocate(v(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)), u(max(nt, 0)))
         allocate(x(size(v)))
         if (rng_take_values(rank, n0, n1, v)) then
            x = nint(v)
            return
         end if
         do i = 1, size(x)
            call random_number(u)
            x(i) = count(u < pp)
         end do
      end function rng_binomial_v

      function rng_geometric_v(pp, rank, n0, n1) result(x)
         ! numpy's geometric draws (trials to the first success, >= 1).
         real(kind=dp), intent(in) :: pp
         integer, intent(in) :: rank, n0, n1
         integer, allocatable :: x(:)
         real(kind=dp), allocatable :: v(:)
         real(kind=dp) :: u
         integer :: i
         allocate(v(merge(1, n0 * merge(n1, 1, rank == 2), rank == 0)))
         allocate(x(size(v)))
         if (rng_take_values(rank, n0, n1, v)) then
            x = nint(v)
            return
         end if
         do i = 1, size(x)
            call random_number(u)
            if (pp >= 1.0_dp) then
               x(i) = 1
            else
               x(i) = max(1, ceiling(log(1.0_dp - u) / log(1.0_dp - pp)))
            end if
         end do
      end function rng_geometric_v

      pure function rng_pick_real(a, idx) result(r)
         ! a[idx] of a vector expression (rng.choice of an array).
         real(kind=dp), intent(in) :: a(:)
         integer, intent(in) :: idx(:)
         real(kind=dp), allocatable :: r(:)
         r = a(idx + 1)
      end function rng_pick_real

      pure function rng_pick_int(a, idx) result(r)
         ! a[idx] of a vector expression (rng.choice of an array).
         integer, intent(in) :: a(:)
         integer, intent(in) :: idx(:)
         integer, allocatable :: r(:)
         r = a(idx + 1)
      end function rng_pick_int

      pure function rng_pick_log(a, idx) result(r)
         ! a[idx] of a vector expression (rng.choice of an array).
         logical, intent(in) :: a(:)
         integer, intent(in) :: idx(:)
         logical, allocatable :: r(:)
         r = a(idx + 1)
      end function rng_pick_log

      pure function rng_pick_complex(a, idx) result(r)
         ! a[idx] of a vector expression (rng.choice of an array).
         complex(kind=dp), intent(in) :: a(:)
         integer, intent(in) :: idx(:)
         complex(kind=dp), allocatable :: r(:)
         r = a(idx + 1)
      end function rng_pick_complex

      pure function diag_k_vec_real(v, k) result(a)
         ! np.diag(v, k) of a vector: a square matrix with v on diagonal k.
         real(kind=dp), intent(in) :: v(:)
         integer, intent(in) :: k
         real(kind=dp), allocatable :: a(:,:)
         integer :: n, i
         n = size(v) + abs(k)
         allocate(a(n, n), source=0.0_dp)
         do i = 1, size(v)
            if (k >= 0) then
               a(i, i + k) = v(i)
            else
               a(i - k, i) = v(i)
            end if
         end do
      end function diag_k_vec_real

      pure function diag_k_mat_real(a, k) result(v)
         ! np.diag(a, k) of a matrix: its diagonal k (above the main for k > 0).
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: k
         real(kind=dp), allocatable :: v(:)
         integer :: n, i
         if (k >= 0) then
            n = max(0, min(size(a,1), size(a,2) - k))
         else
            n = max(0, min(size(a,1) + k, size(a,2)))
         end if
         allocate(v(n))
         do i = 1, n
            if (k >= 0) then
               v(i) = a(i, i + k)
            else
               v(i) = a(i - k, i)
            end if
         end do
      end function diag_k_mat_real

      pure function triu_real(a, k) result(b)
         ! np.triu(a, k): zero below diagonal k.
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         real(kind=dp), allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i < kk) b(i, j) = 0.0_dp
            end do
         end do
      end function triu_real

      pure function triu_complex(a, k) result(b)
         ! np.triu(a, k): zero below diagonal k.
         complex(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         complex(kind=dp), allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i < kk) b(i, j) = (0.0_dp, 0.0_dp)
            end do
         end do
      end function triu_complex

      pure function tril_real(a, k) result(b)
         ! np.tril(a, k): zero above diagonal k.
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         real(kind=dp), allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i > kk) b(i, j) = 0.0_dp
            end do
         end do
      end function tril_real

      pure function tril_complex(a, k) result(b)
         ! np.tril(a, k): zero above diagonal k.
         complex(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         complex(kind=dp), allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i > kk) b(i, j) = (0.0_dp, 0.0_dp)
            end do
         end do
      end function tril_complex

      pure function diag_k_vec_int(v, k) result(a)
         ! np.diag(v, k) of a vector: a square matrix with v on diagonal k.
         integer, intent(in) :: v(:)
         integer, intent(in) :: k
         integer, allocatable :: a(:,:)
         integer :: n, i
         n = size(v) + abs(k)
         allocate(a(n, n), source=0)
         do i = 1, size(v)
            if (k >= 0) then
               a(i, i + k) = v(i)
            else
               a(i - k, i) = v(i)
            end if
         end do
      end function diag_k_vec_int

      pure function diag_k_mat_int(a, k) result(v)
         ! np.diag(a, k) of a matrix: its diagonal k (above the main for k > 0).
         integer, intent(in) :: a(:,:)
         integer, intent(in) :: k
         integer, allocatable :: v(:)
         integer :: n, i
         if (k >= 0) then
            n = max(0, min(size(a,1), size(a,2) - k))
         else
            n = max(0, min(size(a,1) + k, size(a,2)))
         end if
         allocate(v(n))
         do i = 1, n
            if (k >= 0) then
               v(i) = a(i, i + k)
            else
               v(i) = a(i - k, i)
            end if
         end do
      end function diag_k_mat_int

      pure function triu_int(a, k) result(b)
         ! np.triu(a, k): zero below diagonal k.
         integer, intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         integer, allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i < kk) b(i, j) = 0
            end do
         end do
      end function triu_int

      pure function tril_int(a, k) result(b)
         ! np.tril(a, k): zero above diagonal k.
         integer, intent(in) :: a(:,:)
         integer, intent(in), optional :: k
         integer, allocatable :: b(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         b = a
         do j = 1, size(a,2)
            do i = 1, size(a,1)
               if (j - i > kk) b(i, j) = 0
            end do
         end do
      end function tril_int

      pure function quantile_axis_3d(x, q, dim) result(out)
         ! np.quantile(x, q, axis=dim-1) of a rank-3 array (np.median with
         ! q = 0.5): one quantile per position along the other two axes.
         real(kind=dp), intent(in) :: x(:,:,:)
         real(kind=dp), intent(in) :: q
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:)
         integer :: i, j
         select case (dim)
         case (1)
            allocate(out(size(x,2), size(x,3)))
            do j = 1, size(x,3)
               do i = 1, size(x,2)
                  out(i, j) = quantile_linear(x(:, i, j), q)
               end do
            end do
         case (2)
            allocate(out(size(x,1), size(x,3)))
            do j = 1, size(x,3)
               do i = 1, size(x,1)
                  out(i, j) = quantile_linear(x(i, :, j), q)
               end do
            end do
         case default
            allocate(out(size(x,1), size(x,2)))
            do j = 1, size(x,2)
               do i = 1, size(x,1)
                  out(i, j) = quantile_linear(x(i, j, :), q)
               end do
            end do
         end select
      end function quantile_axis_3d

      pure function quantile_axis_2d(x, q, dim) result(out)
         ! np.quantile(x, q, axis=dim-1) of a matrix (np.median with q = 0.5).
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), intent(in) :: q
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:)
         integer :: i
         if (dim == 1) then
            allocate(out(size(x,2)))
            do i = 1, size(x,2)
               out(i) = quantile_linear(x(:,i), q)
            end do
         else
            allocate(out(size(x,1)))
            do i = 1, size(x,1)
               out(i) = quantile_linear(x(i,:), q)
            end do
         end if
      end function quantile_axis_2d

      pure function quantile_axis_2d_q(x, q, dim) result(out)
         ! np.quantile(x, q, axis=dim-1) of a matrix for a vector q: numpy's
         ! shape (size(q), the other extent), row k for q(k).
         real(kind=dp), intent(in) :: x(:,:), q(:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:)
         integer :: k
         allocate(out(size(q), size(x, 3 - dim)))
         do k = 1, size(q)
            out(k, :) = quantile_axis_2d(x, q(k), dim)
         end do
      end function quantile_axis_2d_q

      pure function sorted_real_vec(x) result(y)
         ! np.sort(x) of a vector: a sorted copy.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         y = x
         call sort_real_vec(y)
      end function sorted_real_vec

      pure function sorted_real_2d(x, dim) result(y)
         ! np.sort(x, axis) of a matrix: each column (dim = 1) or row
         ! (dim = 2) sorted.
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: y(:,:)
         real(kind=dp), allocatable :: v(:)
         integer :: i
         y = x
         if (dim == 1) then
            do i = 1, size(x,2)
               v = y(:,i)
               call sort_real_vec(v)
               y(:,i) = v
            end do
         else
            do i = 1, size(x,1)
               v = y(i,:)
               call sort_real_vec(v)
               y(i,:) = v
            end do
         end if
      end function sorted_real_2d

      pure function argsort_real_2d(x, dim) result(idx)
         ! np.argsort(x, axis) of a matrix: 0-based positions within each
         ! column (dim = 1) or row (dim = 2).
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: idx(:,:)
         integer :: i
         allocate(idx(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               idx(:,i) = argsort_idx_real(x(:,i))
            end do
         else
            do i = 1, size(x,1)
               idx(i,:) = argsort_idx_real(x(i,:))
            end do
         end if
      end function argsort_real_2d

      pure function sorted_int_vec(x) result(y)
         ! np.sort(x) of a vector: a sorted copy.
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         y = x
         call sort_int_vec(y)
      end function sorted_int_vec

      pure function sorted_int_2d(x, dim) result(y)
         ! np.sort(x, axis) of a matrix: each column (dim = 1) or row
         ! (dim = 2) sorted.
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: y(:,:)
         integer, allocatable :: v(:)
         integer :: i
         y = x
         if (dim == 1) then
            do i = 1, size(x,2)
               v = y(:,i)
               call sort_int_vec(v)
               y(:,i) = v
            end do
         else
            do i = 1, size(x,1)
               v = y(i,:)
               call sort_int_vec(v)
               y(i,:) = v
            end do
         end if
      end function sorted_int_2d

      pure function argsort_int_2d(x, dim) result(idx)
         ! np.argsort(x, axis) of a matrix: 0-based positions within each
         ! column (dim = 1) or row (dim = 2).
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, allocatable :: idx(:,:)
         integer :: i
         allocate(idx(size(x,1), size(x,2)))
         if (dim == 1) then
            do i = 1, size(x,2)
               idx(:,i) = argsort_idx_int(x(:,i))
            end do
         else
            do i = 1, size(x,1)
               idx(i,:) = argsort_idx_int(x(i,:))
            end do
         end if
      end function argsort_int_2d

      pure function arange_int(start, stop, step) result(x)
         integer, intent(in) :: start, stop, step
         integer, allocatable :: x(:)
         integer :: n, i, s
         s = step
         if (s == 0) error stop 'arange_int: step cannot be zero'
         if (s > 0) then
            if (stop <= start) then
               n = 0
            else
               n = (stop - start + s - 1) / s
            end if
         else
            if (stop >= start) then
               n = 0
            else
               n = (start - stop + (-s) - 1) / (-s)
            end if
         end if
         allocate(x(n))
         do i = 1, n
            x(i) = start + (i - 1) * s
         end do
      end function arange_int

      pure function np_insert_real_1d(a, idx, val) result(out)
         real(kind=dp), intent(in) :: a(:)
         integer, intent(in) :: idx
         real(kind=dp), intent(in) :: val
         real(kind=dp), allocatable :: out(:)
         integer :: n, pos
         n = size(a)
         pos = idx
         if (pos < 0) pos = n + pos
         if (pos < 0) pos = 0
         if (pos > n) pos = n
         allocate(out(n + 1))
         if (pos > 0) out(1:pos) = a(1:pos)
         out(pos + 1) = val
         if (pos < n) out(pos + 2:n + 1) = a(pos + 1:n)
      end function np_insert_real_1d

      function np_delete_real_1d(a, idx) result(out)
         real(kind=dp), intent(in) :: a(:)
         integer, intent(in) :: idx
         real(kind=dp), allocatable :: out(:)
         integer :: n, pos
         n = size(a)
         if (n <= 0) then
            allocate(out(0))
            return
         end if
         pos = idx
         if (pos < 0) pos = n + pos
         if (pos < 0 .or. pos >= n) stop "np.delete index out of range"
         allocate(out(max(0, n - 1)))
         if (n == 1) return
         if (pos > 0) out(1:pos) = a(1:pos)
         if (pos < n - 1) out(pos + 1:n - 1) = a(pos + 2:n)
      end function np_delete_real_1d

      pure function linspace(start, stop, num) result(x)
         real(kind=dp), intent(in) :: start, stop
         integer, intent(in) :: num
         real(kind=dp), allocatable :: x(:)
         integer :: n, i
         n = max(0, num)
         allocate(x(n))
         if (n <= 0) return
         if (n == 1) then
            x(1) = start
            return
         end if
         do i = 1, n
            x(i) = start + (stop - start) * real(i - 1, kind=dp) / real(n - 1, kind=dp)
         end do
      end function linspace

      function logspace(start, stop, num, endpoint, base) result(x)
         real(kind=dp), intent(in) :: start, stop
         integer, intent(in), optional :: num
         logical, intent(in), optional :: endpoint
         real(kind=dp), intent(in), optional :: base
         real(kind=dp), allocatable :: x(:)
         integer :: n, i
         logical :: ep
         real(kind=dp) :: b, dx
         n = 50
         if (present(num)) n = max(0, num)
         ep = .true.
         if (present(endpoint)) ep = endpoint
         b = 10.0_dp
         if (present(base)) b = base
         allocate(x(n))
         if (n <= 0) return
         if (n == 1) then
            if (ep) then
               x(1) = b**stop
            else
               x(1) = b**start
            end if
            return
         end if
         if (ep) then
            dx = (stop - start) / real(n - 1, kind=dp)
         else
            dx = (stop - start) / real(n, kind=dp)
         end if
         do i = 1, n
            x(i) = b**(start + dx * real(i - 1, kind=dp))
         end do
      end function logspace

      function geomspace(start, stop, num, endpoint) result(x)
         real(kind=dp), intent(in) :: start, stop
         integer, intent(in), optional :: num
         logical, intent(in), optional :: endpoint
         real(kind=dp), allocatable :: x(:)
         integer :: n, i
         logical :: ep
         real(kind=dp) :: sgn, la, lb, dx
         n = 50
         if (present(num)) n = max(0, num)
         ep = .true.
         if (present(endpoint)) ep = endpoint
         if (start == 0.0_dp .or. stop == 0.0_dp) error stop 'geomspace: start/stop must be non-zero'
         if (start * stop < 0.0_dp) error stop 'geomspace: start/stop must have same sign'
         sgn = 1.0_dp
         if (start < 0.0_dp) sgn = -1.0_dp
         la = log(abs(start))
         lb = log(abs(stop))
         allocate(x(n))
         if (n <= 0) return
         if (n == 1) then
            if (ep) then
               x(1) = stop
            else
               x(1) = start
            end if
            return
         end if
         if (ep) then
            dx = (lb - la) / real(n - 1, kind=dp)
         else
            dx = (lb - la) / real(n, kind=dp)
         end if
         do i = 1, n
            x(i) = sgn * exp(la + dx * real(i - 1, kind=dp))
         end do
      end function geomspace

      pure function bincount_int(x, minlength) result(c)
         integer, intent(in) :: x(:)
         integer, intent(in), optional :: minlength
         integer, allocatable :: c(:)
         integer :: i, nmax, nout, m
         if (present(minlength)) then
            m = max(0, minlength)
         else
            m = 0
         end if
         if (size(x) <= 0) then
            nout = m
            allocate(c(1:nout), source=0)
            return
         end if
         if (any(x < 0)) error stop 'bincount_int: negative values are not supported'
         nmax = maxval(x)
         nout = max(nmax + 1, m)
         allocate(c(1:nout), source=0)
         do i = 1, size(x)
            c(x(i) + 1) = c(x(i) + 1) + 1
         end do
      end function bincount_int

      pure function searchsorted_left_int(a, v) result(idx)
         integer, intent(in) :: a(:), v(:)
         integer, allocatable :: idx(:)
         integer :: i, lo, hi, mid, n
         n = size(a)
         allocate(idx(1:size(v)))
         do i = 1, size(v)
            lo = 1
            hi = n + 1
            do while (lo < hi)
               mid = (lo + hi) / 2
               if (mid <= n .and. a(mid) < v(i)) then
                  lo = mid + 1
               else
                  hi = mid
               end if
            end do
            idx(i) = lo - 1
         end do
      end function searchsorted_left_int

      pure function searchsorted_right_int(a, v) result(idx)
         integer, intent(in) :: a(:), v(:)
         integer, allocatable :: idx(:)
         integer :: i, lo, hi, mid, n
         n = size(a)
         allocate(idx(1:size(v)))
         do i = 1, size(v)
            lo = 1
            hi = n + 1
            do while (lo < hi)
               mid = (lo + hi) / 2
               if (mid <= n .and. a(mid) <= v(i)) then
                  lo = mid + 1
               else
                  hi = mid
               end if
            end do
            idx(i) = lo - 1
         end do
      end function searchsorted_right_int

      pure function searchsorted_left_int_scalar(a, v) result(idx)
         integer, intent(in) :: a(:), v
         integer :: idx
         integer :: lo, hi, mid, n
         n = size(a)
         lo = 1
         hi = n + 1
         do while (lo < hi)
            mid = (lo + hi) / 2
            if (mid <= n .and. a(mid) < v) then
               lo = mid + 1
            else
               hi = mid
            end if
         end do
         idx = lo - 1
      end function searchsorted_left_int_scalar

      pure function searchsorted_right_int_scalar(a, v) result(idx)
         integer, intent(in) :: a(:), v
         integer :: idx
         integer :: lo, hi, mid, n
         n = size(a)
         lo = 1
         hi = n + 1
         do while (lo < hi)
            mid = (lo + hi) / 2
            if (mid <= n .and. a(mid) <= v) then
               lo = mid + 1
            else
               hi = mid
            end if
         end do
         idx = lo - 1
      end function searchsorted_right_int_scalar

      pure function setdiff1d_int(a, b) result(c)
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         integer, allocatable :: ua(:), ub(:), tmp(:)
         integer :: i, j, nout
         ua = unique_int(a)
         ub = unique_int(b)
         allocate(tmp(1:size(ua)), source=0)
         nout = 0
         do i = 1, size(ua)
            do j = 1, size(ub)
               if (ua(i) == ub(j)) exit
            end do
            if (j > size(ub)) then
               nout = nout + 1
               tmp(nout) = ua(i)
            end if
         end do
         allocate(c(1:nout))
         if (nout > 0) c = tmp(1:nout)
      end function setdiff1d_int

      function intersect1d_int(a, b) result(c)
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         integer, allocatable :: ua(:), ub(:), tmp(:)
         integer :: i, j, nout
         ua = unique_int(a)
         ub = unique_int(b)
         allocate(tmp(1:min(size(ua), size(ub))), source=0)
         nout = 0
         do i = 1, size(ua)
            do j = 1, size(ub)
               if (ua(i) == ub(j)) then
                  nout = nout + 1
                  tmp(nout) = ua(i)
                  exit
               end if
            end do
         end do
         allocate(c(1:nout))
         if (nout > 0) c = tmp(1:nout)
      end function intersect1d_int

      function setdiff1d_char(a, b) result(c)
         character(len=*), intent(in) :: a(:), b(:)
         character(len=:), allocatable :: c(:)
         character(len=:), allocatable :: ua(:), ub(:), tmp(:)
         integer :: i, j, nout, llen
         ua = unique_char(a)
         ub = unique_char(b)
         llen = max(len(a), len(b))
         if (llen < 1) llen = 1
         allocate(character(len=llen) :: tmp(size(ua)))
         nout = 0
         do i = 1, size(ua)
            do j = 1, size(ub)
               if (ua(i) == ub(j)) exit
            end do
            if (j > size(ub)) then
               nout = nout + 1
               tmp(nout) = ua(i)
            end if
         end do
         allocate(character(len=llen) :: c(nout))
         if (nout > 0) c = tmp(1:nout)
      end function setdiff1d_char

      function intersect1d_char(a, b) result(c)
         character(len=*), intent(in) :: a(:), b(:)
         character(len=:), allocatable :: c(:)
         character(len=:), allocatable :: ua(:), ub(:), tmp(:)
         integer :: i, j, nout, llen
         ua = unique_char(a)
         ub = unique_char(b)
         llen = max(len(a), len(b))
         if (llen < 1) llen = 1
         allocate(character(len=llen) :: tmp(min(size(ua), size(ub))))
         nout = 0
         do i = 1, size(ua)
            do j = 1, size(ub)
               if (ua(i) == ub(j)) then
                  nout = nout + 1
                  tmp(nout) = ua(i)
                  exit
               end if
            end do
         end do
         allocate(character(len=llen) :: c(nout))
         if (nout > 0) c = tmp(1:nout)
      end function intersect1d_char

      subroutine unique_int_inv_counts(a, u, inv, cnt)
         integer, intent(in) :: a(:)
         integer, allocatable, intent(out) :: u(:), inv(:), cnt(:)
         integer :: i, j, n
         u = unique_int(a)
         n = size(a)
         allocate(inv(1:n), source=0)
         allocate(cnt(1:size(u)), source=0)
         do i = 1, n
            do j = 1, size(u)
               if (a(i) == u(j)) then
                  inv(i) = j - 1
                  cnt(j) = cnt(j) + 1
                  exit
               end if
            end do
         end do
      end subroutine unique_int_inv_counts

      pure function lexsort2_int(key0, key1) result(idx)
         integer, intent(in) :: key0(:), key1(:)
         integer, allocatable :: idx(:)
         integer :: i, j, n, t
         n = size(key0)
         if (size(key1) /= n) error stop 'lexsort2_int: key size mismatch'
         allocate(idx(1:n))
         do i = 1, n
            idx(i) = i - 1
         end do
         do i = 2, n
            t = idx(i)
            j = i - 1
            do while (j >= 1)
               if (key1(idx(j)+1) < key1(t+1)) exit
               if (key1(idx(j)+1) == key1(t+1) .and. key0(idx(j)+1) <= key0(t+1)) exit
               idx(j+1) = idx(j)
               j = j - 1
            end do
            idx(j+1) = t
         end do
      end function lexsort2_int

      pure function lexsort2_real(key0, key1) result(idx)
         real(kind=dp), intent(in) :: key0(:), key1(:)
         integer, allocatable :: idx(:)
         integer :: i, j, n, tmp

         n = size(key0)
         if (size(key1) /= n) error stop 'lexsort2_real: key size mismatch'
         allocate(idx(n))
         do i = 1, n
            idx(i) = i - 1
         end do
         do i = 1, n - 1
            do j = i + 1, n
               if (key1(idx(j) + 1) < key1(idx(i) + 1) .or. &
                   (key1(idx(j) + 1) == key1(idx(i) + 1) .and. key0(idx(j) + 1) < key0(idx(i) + 1))) then
                  tmp = idx(i)
                  idx(i) = idx(j)
                  idx(j) = tmp
               end if
            end do
         end do
      end function lexsort2_real

      pure function ravel_multi_index_2d(rc, shape, forder) result(i)
         ! np.ravel_multi_index(tuple(rc), shape): the flat index (C order, or
         ! Fortran order with forder) of the 0-based multi-index rc.
         integer, intent(in) :: rc(:), shape(:)
         logical, intent(in), optional :: forder
         integer :: i, k
         logical :: f
         f = .false.
         if (present(forder)) f = forder
         if (size(rc) /= size(shape)) error stop 'ravel_multi_index: parameter multi_index must be a sequence of length ndim'
         do k = 1, size(rc)
            if (rc(k) < 0 .or. rc(k) >= shape(k)) error stop 'ravel_multi_index: invalid entry in coordinates array'
         end do
         i = 0
         if (f) then
            do k = size(rc), 1, -1
               i = i * shape(k) + rc(k)
            end do
         else
            do k = 1, size(rc)
               i = i * shape(k) + rc(k)
            end do
         end if
      end function ravel_multi_index_2d

      pure function ravel_multi_index_vec(rc, shape, forder) result(i)
         ! np.ravel_multi_index of index arrays: rc(k, :) holds the k-th
         ! coordinate of each multi-index.
         integer, intent(in) :: rc(:,:), shape(:)
         logical, intent(in), optional :: forder
         integer :: i(size(rc, 2))
         integer :: j
         do j = 1, size(rc, 2)
            i(j) = ravel_multi_index_2d(rc(:, j), shape, forder)
         end do
      end function ravel_multi_index_vec

      pure function unravel_index_2d(i, shape, forder) result(rc)
         ! np.unravel_index(i, shape): the 0-based multi-index of flat index i
         ! (C order, or Fortran order with forder).
         integer, intent(in) :: i
         integer, intent(in) :: shape(:)
         logical, intent(in), optional :: forder
         integer, allocatable :: rc(:)
         integer :: k, r
         logical :: f
         f = .false.
         if (present(forder)) f = forder
         if (i < 0 .or. i >= product(shape)) error stop 'unravel_index: index is out of bounds for array with size'
         allocate(rc(size(shape)))
         r = i
         if (f) then
            do k = 1, size(shape)
               rc(k) = mod(r, shape(k))
               r = r / shape(k)
            end do
         else
            do k = size(shape), 1, -1
               rc(k) = mod(r, shape(k))
               r = r / shape(k)
            end do
         end if
      end function unravel_index_2d

      pure function unravel_index_vec(i, shape, forder) result(rc)
         ! np.unravel_index of a vector of flat indices: rc(k, :) is the
         ! k-th coordinate array.
         integer, intent(in) :: i(:), shape(:)
         logical, intent(in), optional :: forder
         integer :: rc(size(shape), size(i))
         integer :: j
         do j = 1, size(i)
            rc(:, j) = unravel_index_2d(i(j), shape, forder)
         end do
      end function unravel_index_vec

      pure function unravel_index_part(i, shape, k, forder) result(v)
         ! np.unravel_index(i, shape)[k-1] of a vector of flat indices.
         integer, intent(in) :: i(:), shape(:), k
         logical, intent(in), optional :: forder
         integer :: v(size(i))
         integer :: j
         integer, allocatable :: rc(:)
         do j = 1, size(i)
            rc = unravel_index_2d(i(j), shape, forder)
            v(j) = rc(k)
         end do
      end function unravel_index_part

      pure function kron_2d(a, b) result(k)
         integer, intent(in) :: a(:,:), b(:,:)
         integer, allocatable :: k(:,:)
         integer :: i, j, p, q, ra, ca, rb, cb
         ra = size(a,1); ca = size(a,2)
         rb = size(b,1); cb = size(b,2)
         allocate(k(1:ra*rb, 1:ca*cb), source=0)
         do i = 1, ra
            do j = 1, ca
               do p = 1, rb
                  do q = 1, cb
                     k((i-1)*rb+p, (j-1)*cb+q) = a(i,j) * b(p,q)
                  end do
               end do
            end do
         end do
      end function kron_2d

      pure subroutine histogram_real_edges(x, bins, h, edges)
         real(kind=dp), intent(in) :: x(:), bins(:)
         integer, allocatable, intent(out) :: h(:)
         real(kind=dp), allocatable, intent(out) :: edges(:)
         integer :: i, j, nb
         logical :: placed
         nb = size(bins) - 1
         if (nb < 1) error stop 'histogram_real_edges: bins must have at least 2 entries'
         allocate(h(1:nb), source=0)
         allocate(edges(1:size(bins)), source=bins)
         do i = 1, size(x)
            if (x(i) < bins(1)) cycle
            if (x(i) > bins(nb + 1)) cycle
            placed = .false.
            do j = 1, nb - 1
               if (x(i) >= bins(j) .and. x(i) < bins(j + 1)) then
                  h(j) = h(j) + 1
                  placed = .true.
                  exit
               end if
            end do
            if (.not. placed) then
               if (x(i) >= bins(nb) .and. x(i) <= bins(nb + 1)) h(nb) = h(nb) + 1
            end if
         end do
      end subroutine histogram_real_edges

      pure function histogram_counts(x, nbins) result(h)
         ! np.histogram(x, bins=nbins)[0]: nbins equal bins from min(x) to
         ! max(x) (widened by 0.5 each side when they are equal, as numpy does).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: nbins
         integer, allocatable :: h(:)
         real(kind=dp), allocatable :: edges(:), e_out(:)
         real(kind=dp) :: lo, hi
         integer :: i
         lo = 0.0_dp
         hi = 1.0_dp
         if (size(x) > 0) then
            lo = minval(x)
            hi = maxval(x)
         end if
         if (lo == hi) then
            lo = lo - 0.5_dp
            hi = hi + 0.5_dp
         end if
         allocate(edges(nbins + 1))
         do i = 1, nbins + 1
            edges(i) = lo + (hi - lo) * real(i - 1, kind=dp) / real(nbins, kind=dp)
         end do
         call histogram_real_edges(x, edges, h, e_out)
      end function histogram_counts

      pure function histogram_counts_edges(x, edges) result(h)
         ! np.histogram(x, bins=edges)[0].
         real(kind=dp), intent(in) :: x(:), edges(:)
         integer, allocatable :: h(:)
         real(kind=dp), allocatable :: e_out(:)
         call histogram_real_edges(x, edges, h, e_out)
      end function histogram_counts_edges

      pure subroutine histogram_int_edges(x, bins, h, edges)
         integer, intent(in) :: x(:), bins(:)
         integer, allocatable, intent(out) :: h(:), edges(:)
         integer :: i, j, nb
         logical :: placed
         nb = size(bins) - 1
         if (nb < 1) error stop 'histogram_int_edges: bins must have at least 2 entries'
         allocate(h(1:nb), source=0)
         allocate(edges(1:size(bins)), source=bins)
         do i = 1, size(x)
            if (x(i) < bins(1)) cycle
            if (x(i) > bins(nb + 1)) cycle
            placed = .false.
            do j = 1, nb - 1
               if (x(i) >= bins(j) .and. x(i) < bins(j + 1)) then
                  h(j) = h(j) + 1
                  placed = .true.
                  exit
               end if
            end do
            if (.not. placed) then
               if (x(i) >= bins(nb) .and. x(i) <= bins(nb + 1)) h(nb) = h(nb) + 1
            end if
         end do
      end subroutine histogram_int_edges

      pure function np_hist_edges(x, n, lo_in, hi_in) result(edges)
         ! n equal bins over [min(x), max(x)] (or [lo_in, hi_in]), widened by
         ! 0.5 each side when the ends are equal, with np.linspace's
         ! arithmetic (start + i * step, the last edge exactly the end).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: n
         real(kind=dp), intent(in), optional :: lo_in, hi_in
         real(kind=dp), allocatable :: edges(:)
         real(kind=dp) :: lo, hi, step
         integer :: i
         if (n < 1) error stop "np.histogram: bins must be positive"
         lo = 0.0_dp
         hi = 1.0_dp
         if (present(lo_in)) then
            lo = lo_in
            hi = hi_in
            if (lo > hi) error stop "np.histogram: max must be larger than min in range parameter"
         else if (size(x) > 0) then
            lo = minval(x)
            hi = maxval(x)
         end if
         if (lo == hi) then
            lo = lo - 0.5_dp
            hi = hi + 0.5_dp
         end if
         allocate(edges(n + 1))
         step = (hi - lo) / real(n, kind=dp)
         do i = 1, n
            edges(i) = real(i - 1, kind=dp) * step + lo
         end do
         edges(n + 1) = hi
      end function np_hist_edges

      pure subroutine histogram_np(x, bins, h, edges, weights, density)
         ! numpy.histogram(x, bins=edges, weights=, density=): float counts
         ! (or sums of weights) per bin, the last bin including its right
         ! edge; density divides by the bin widths and the total.
         real(kind=dp), intent(in) :: x(:), bins(:)
         real(kind=dp), allocatable, intent(out) :: h(:), edges(:)
         real(kind=dp), intent(in), optional :: weights(:)
         logical, intent(in), optional :: density
         integer :: i, j, nb
         real(kind=dp) :: s
         nb = size(bins) - 1
         if (nb < 1) error stop "np.histogram: bins must have at least 2 entries"
         if (present(weights)) then
            if (size(weights) /= size(x)) error stop "np.histogram: weights should have the same shape as a"
         end if
         allocate(h(nb), source=0.0_dp)
         edges = bins
         do i = 1, size(x)
            if (ieee_is_nan(x(i)) .or. x(i) < bins(1) .or. x(i) > bins(nb + 1)) cycle
            j = nb
            if (x(i) < bins(nb + 1)) j = count(bins(2:nb) <= x(i)) + 1
            if (present(weights)) then
               h(j) = h(j) + weights(i)
            else
               h(j) = h(j) + 1.0_dp
            end if
         end do
         if (present(density)) then
            if (density) then
               s = sum(h)
               h = h / (bins(2:) - bins(:nb)) / s
            end if
         end if
      end subroutine histogram_np

      pure integer function np_hist_bin_count(x, method, integer_data, lo_in, hi_in) result(n)
         ! The number of equal bins numpy's histogram estimator method
         ! ('auto', 'fd', 'doane', 'scott', 'rice', 'sturges', 'sqrt') picks
         ! for x (only the values in [lo_in, hi_in] if given); integer_data:
         ! x holds integers (the width is then at least 1).
         real(kind=dp), intent(in) :: x(:)
         character(len=*), intent(in) :: method
         logical, intent(in) :: integer_data
         real(kind=dp), intent(in), optional :: lo_in, hi_in
         real(kind=dp), allocatable :: a(:), s(:)
         real(kind=dp) :: lo, hi, w, ptp, nn, sd, g1, sg1, fd, st
         integer :: m
         if (present(lo_in)) then
            lo = lo_in
            hi = hi_in
            a = pack(x, x >= lo .and. x <= hi)
         else
            a = x
            lo = 0.0_dp
            hi = 1.0_dp
            if (size(a) > 0) then
               lo = minval(a)
               hi = maxval(a)
            end if
         end if
         if (lo == hi) then
            lo = lo - 0.5_dp
            hi = hi + 0.5_dp
         end if
         m = size(a)
         if (m == 0) then
            n = 1
            return
         end if
         nn = real(m, kind=dp)
         ptp = maxval(a) - minval(a)
         sd = sqrt(sum((a - sum(a) / nn) ** 2) / nn)
         select case (method)
         case ("sqrt")
            w = ptp / sqrt(nn)
         case ("sturges")
            w = ptp / (log(nn) / log(2.0_dp) + 1.0_dp)
         case ("rice")
            w = ptp / (2.0_dp * nn ** (1.0_dp / 3.0_dp))
         case ("scott")
            w = (24.0_dp * sqrt(acos(-1.0_dp)) / nn) ** (1.0_dp / 3.0_dp) * sd
         case ("doane")
            w = 0.0_dp
            if (m > 2 .and. sd > 0.0_dp) then
               sg1 = sqrt(6.0_dp * (nn - 2.0_dp) / ((nn + 1.0_dp) * (nn + 3.0_dp)))
               g1 = sum(((a - sum(a) / nn) / sd) ** 3) / nn
               w = ptp / (1.0_dp + log(nn) / log(2.0_dp) + log(1.0_dp + abs(g1) / sg1) / log(2.0_dp))
            end if
         case ("fd", "auto")
            s = a
            call sort_vec(s)
            fd = 2.0_dp * (pct(0.75_dp) - pct(0.25_dp)) * nn ** (-1.0_dp / 3.0_dp)
            w = fd
            if (method == "auto") then
               st = ptp / (log(nn) / log(2.0_dp) + 1.0_dp)
               if (fd /= 0.0_dp) then
                  w = min(fd, st)
               else
                  w = st
               end if
            end if
         case default
            error stop "np.histogram: unknown bin estimator"
         end select
         if (w /= 0.0_dp) then
            if (integer_data .and. w < 1.0_dp) w = 1.0_dp
            n = int(ceiling((hi - lo) / w))
         else
            n = 1
         end if
      contains
         pure real(kind=dp) function pct(q)
            ! The q quantile of the sorted s (numpy's linear method).
            real(kind=dp), intent(in) :: q
            real(kind=dp) :: pos
            integer :: k
            pos = q * real(size(s) - 1, kind=dp)
            k = int(pos)
            if (k >= size(s) - 1) then
               pct = s(size(s))
            else
               pct = s(k + 1) + (pos - real(k, kind=dp)) * (s(k + 2) - s(k + 1))
            end if
         end function pct
      end function np_hist_bin_count

      pure subroutine histogram2d_np(x, y, xbins, ybins, h, weights, density)
         ! numpy.histogram2d(x, y, bins=[xbins, ybins], weights=, density=):
         ! float counts (or sums of weights); per axis the last bin includes
         ! its right edge; density divides by the bin areas and the total.
         real(kind=dp), intent(in) :: x(:), y(:), xbins(:), ybins(:)
         real(kind=dp), allocatable, intent(out) :: h(:,:)
         real(kind=dp), intent(in), optional :: weights(:)
         logical, intent(in), optional :: density
         integer :: i, ix, iy, nxb, nyb
         real(kind=dp) :: s
         nxb = size(xbins) - 1
         nyb = size(ybins) - 1
         if (nxb < 1 .or. nyb < 1) error stop "np.histogram2d: bins must have at least 2 edges"
         if (size(x) /= size(y)) error stop "np.histogram2d: x and y must have the same length"
         if (present(weights)) then
            if (size(weights) /= size(x)) error stop "np.histogram2d: weights must have the length of x"
         end if
         allocate(h(nxb, nyb), source=0.0_dp)
         do i = 1, size(x)
            ix = bin_of(x(i), xbins)
            iy = bin_of(y(i), ybins)
            if (ix == 0 .or. iy == 0) cycle
            if (present(weights)) then
               h(ix, iy) = h(ix, iy) + weights(i)
            else
               h(ix, iy) = h(ix, iy) + 1.0_dp
            end if
         end do
         if (present(density)) then
            if (density) then
               s = sum(h)
               h = h / spread(xbins(2:) - xbins(:nxb), 2, nyb)
               h = h / spread(ybins(2:) - ybins(:nyb), 1, nxb)
               h = h / s
            end if
         end if
      contains
         pure integer function bin_of(v, e)
            ! 1-based bin of v in edges e (0 outside); the last bin is closed.
            real(kind=dp), intent(in) :: v, e(:)
            integer :: lo, hi, mid, m
            m = size(e)
            bin_of = 0
            if (.not. (v >= e(1) .and. v <= e(m))) return
            if (v == e(m)) then
               bin_of = m - 1
               return
            end if
            lo = 1
            hi = m
            do while (hi - lo > 1)
               mid = (lo + hi) / 2
               if (e(mid) <= v) then
                  lo = mid
               else
                  hi = mid
               end if
            end do
            bin_of = lo
         end function bin_of
      end subroutine histogram2d_np

      pure subroutine histogram2d_real_edges(x, y, xbins, ybins, h)
         ! 2D histogram with explicit real bin edges on both axes,
         ! matching numpy.histogram2d(x, y, bins=[xbins, ybins]): same
         ! per-axis binning rule as histogram_real_edges (last bin is
         ! right-inclusive), applied independently to x against xbins
         ! and y against ybins, then counted jointly.
         real(kind=dp), intent(in) :: x(:), y(:), xbins(:), ybins(:)
         integer, allocatable, intent(out) :: h(:,:)
         integer :: i, j, ix, iy, nxb, nyb
         logical :: placed
         nxb = size(xbins) - 1
         nyb = size(ybins) - 1
         if (nxb < 1 .or. nyb < 1) error stop 'histogram2d_real_edges: bins must have at least 2 entries'
         allocate(h(1:nxb, 1:nyb), source=0)
         do i = 1, size(x)
            if (x(i) < xbins(1) .or. x(i) > xbins(nxb + 1)) cycle
            if (y(i) < ybins(1) .or. y(i) > ybins(nyb + 1)) cycle
            ix = 0
            placed = .false.
            do j = 1, nxb - 1
               if (x(i) >= xbins(j) .and. x(i) < xbins(j + 1)) then
                  ix = j
                  placed = .true.
                  exit
               end if
            end do
            if (.not. placed) then
               if (x(i) >= xbins(nxb) .and. x(i) <= xbins(nxb + 1)) ix = nxb
            end if
            iy = 0
            placed = .false.
            do j = 1, nyb - 1
               if (y(i) >= ybins(j) .and. y(i) < ybins(j + 1)) then
                  iy = j
                  placed = .true.
                  exit
               end if
            end do
            if (.not. placed) then
               if (y(i) >= ybins(nyb) .and. y(i) <= ybins(nyb + 1)) iy = nyb
            end if
            if (ix > 0 .and. iy > 0) h(ix, iy) = h(ix, iy) + 1
         end do
      end subroutine histogram2d_real_edges

      pure function reduceat_add_real(x, idx) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_add_real: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) + x(j)
            end do
         end do
      end function reduceat_add_real

      pure function reduceat_add_int(x, idx) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         integer, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_add_int: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) + x(j)
            end do
         end do
      end function reduceat_add_int

      pure function reduceat_mul_real(x, idx) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_mul_real: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) * x(j)
            end do
         end do
      end function reduceat_mul_real

      pure function reduceat_mul_int(x, idx) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         integer, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_mul_int: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) * x(j)
            end do
         end do
      end function reduceat_mul_int

      pure function reduceat_min_real(x, idx) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_min_real: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = min(y(i), x(j))
            end do
         end do
      end function reduceat_min_real

      pure function reduceat_min_int(x, idx) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         integer, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_min_int: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = min(y(i), x(j))
            end do
         end do
      end function reduceat_min_int

      pure function reduceat_max_real(x, idx) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_max_real: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = max(y(i), x(j))
            end do
         end do
      end function reduceat_max_real

      pure function reduceat_max_int(x, idx) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         integer, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_max_int: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = max(y(i), x(j))
            end do
         end do
      end function reduceat_max_int

      pure function reduceat_logical_and(x, idx) result(y)
         logical, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         logical, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_logical_and: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) .and. x(j)
            end do
         end do
      end function reduceat_logical_and

      pure function reduceat_logical_or(x, idx) result(y)
         logical, intent(in) :: x(:)
         integer, intent(in) :: idx(:)
         logical, allocatable :: y(:)
         integer :: i, j, lo, hi, n, m
         n = size(x)
         m = size(idx)
         allocate(y(1:m))
         do i = 1, m
            lo = idx(i) + 1
            if (lo < 1 .or. lo > n) error stop 'reduceat_logical_or: idx out of bounds'
            if (i < m) then
               hi = idx(i + 1)
            else
               hi = n
            end if
            if (hi < lo) hi = lo
            y(i) = x(lo)
            do j = lo + 1, hi
               y(i) = y(i) .or. x(j)
            end do
         end do
      end function reduceat_logical_or

      pure real(kind=dp) function mean_1d(x)
         real(kind=dp), intent(in) :: x(:)
         ! Compatibility name for previously generated translations.
         mean_1d = mean(x)
      end function mean_1d

      pure real(kind=dp) function weighted_mean_1d(x, w)
         real(kind=dp), intent(in) :: x(:), w(:)
         integer :: n
         real(kind=dp) :: sw

         n = min(size(x), size(w))
         if (n <= 0) then
            weighted_mean_1d = 0.0_dp
            return
         end if
         sw = sum(w(1:n))
         if (sw == 0.0_dp) then
            weighted_mean_1d = 0.0_dp
         else
            weighted_mean_1d = sum(x(1:n) * w(1:n)) / sw
         end if
      end function weighted_mean_1d

      pure real(kind=dp) function var_1d(x, ddof)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         integer :: n, d
         real(kind=dp) :: mu
         n = size(x)
         if (present(ddof)) then
            d = ddof
         else
            d = 0
         end if
         if (n <= d .or. n <= 0) then
            var_1d = 0.0_dp
            return
         end if
         mu = mean(x)
         var_1d = sum((x - mu)**2) / real(n - d, kind=dp)
      end function var_1d

      pure real(kind=dp) function skew_1d(x)
         ! pandas Series/DataFrame.skew() -- the adjusted (bias-corrected)
         ! Fisher-Pearson standardized moment coefficient: G1 =
         ! sqrt(n*(n-1))/(n-2) * m3/m2**1.5, where m2/m3 are the 2nd/3rd
         ! central moments about the (population, /n not /(n-1)) mean.
         ! NaN for n<3 (undefined) or zero variance, matching pandas.
         real(kind=dp), intent(in) :: x(:)
         integer :: n
         real(kind=dp) :: mu, m2, m3
         n = size(x)
         if (n < 3) then
            skew_1d = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         mu = mean(x)
         m2 = sum((x - mu)**2) / real(n, kind=dp)
         m3 = sum((x - mu)**3) / real(n, kind=dp)
         if (m2 <= tiny(1.0_dp)) then
            skew_1d = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         skew_1d = (sqrt(real(n, kind=dp)*real(n - 1, kind=dp)) / real(n - 2, kind=dp)) * (m3 / m2**1.5_dp)
      end function skew_1d

      pure real(kind=dp) function kurt_1d(x)
         ! pandas Series/DataFrame.kurt() -- the adjusted (bias-corrected)
         ! excess kurtosis: G2 = ((n-1)/((n-2)*(n-3))) * ((n+1)*g2 + 6),
         ! where g2 = m4/m2**2 - 3 is the population excess kurtosis (m2/m4
         ! the 2nd/4th central moments about the population mean). NaN for
         ! n<4 (undefined) or zero variance, matching pandas.
         real(kind=dp), intent(in) :: x(:)
         integer :: n
         real(kind=dp) :: mu, m2, m4, g2
         n = size(x)
         if (n < 4) then
            kurt_1d = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         mu = mean(x)
         m2 = sum((x - mu)**2) / real(n, kind=dp)
         m4 = sum((x - mu)**4) / real(n, kind=dp)
         if (m2 <= tiny(1.0_dp)) then
            kurt_1d = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         g2 = m4 / m2**2 - 3.0_dp
         kurt_1d = (real(n - 1, kind=dp) / (real(n - 2, kind=dp)*real(n - 3, kind=dp))) * &
                   (real(n + 1, kind=dp)*g2 + 6.0_dp)
      end function kurt_1d

      function median_1d_real(x) result(m)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: m
         real(kind=dp), allocatable :: xs(:)
         integer :: n

         n = size(x)
         if (n <= 0) then
            m = 0.0_dp
            return
         end if
         allocate(xs(n))
         xs = x
         call sort_real_vec(xs)
         if (mod(n, 2) == 1) then
            m = xs((n + 1) / 2)
         else
            m = 0.5_dp * (xs(n / 2) + xs(n / 2 + 1))
         end if
      end function median_1d_real

      function median_low_int(x) result(m)
         integer, intent(in) :: x(:)
         integer :: m
         integer, allocatable :: xs(:)
         integer :: n

         n = size(x)
         if (n <= 0) then
            m = 0
            return
         end if
         allocate(xs(n))
         xs = x
         call sort_int_vec(xs)
         if (mod(n, 2) == 1) then
            m = xs((n + 1) / 2)
         else
            m = xs(n / 2)
         end if
      end function median_low_int

      pure function median_high_int(x) result(m)
         integer, intent(in) :: x(:)
         integer :: m
         integer, allocatable :: xs(:)
         integer :: n

         n = size(x)
         if (n <= 0) then
            m = 0
            return
         end if
         allocate(xs(n))
         xs = x
         call sort_int_vec(xs)
         m = xs(n / 2 + 1)
      end function median_high_int

      function mode_int(x) result(m)
         integer, intent(in) :: x(:)
         integer :: m
         integer, allocatable :: u(:), cnt(:)
         integer :: i, best_i, best_c

         if (size(x) <= 0) then
            m = 0
            return
         end if
         call unique_int_counts(x, u, cnt)
         if (size(u) <= 0) then
            m = 0
            return
         end if
         best_i = 1
         best_c = cnt(1)
         do i = 2, size(cnt)
            if (cnt(i) > best_c) then
               best_c = cnt(i)
               best_i = i
            end if
         end do
         m = u(best_i)
      end function mode_int

      pure function mode_real(x) result(m)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: m
         integer :: i, j, cnt, best_c

         if (size(x) <= 0) then
            m = 0.0_dp
            return
         end if
         m = x(1)
         best_c = 0
         do i = 1, size(x)
            cnt = 0
            do j = 1, size(x)
               if (x(j) == x(i)) cnt = cnt + 1
            end do
            if (cnt > best_c) then
               best_c = cnt
               m = x(i)
            end if
         end do
      end function mode_real

      function multimode_int(x) result(mm)
         integer, intent(in) :: x(:)
         integer, allocatable :: mm(:)
         integer, allocatable :: u(:), cnt(:)
         integer :: maxc

         if (size(x) <= 0) then
            allocate(mm(0))
            return
         end if
         call unique_int_counts(x, u, cnt)
         if (size(u) <= 0) then
            allocate(mm(0))
            return
         end if
         maxc = maxval(cnt)
         mm = pack(u, cnt == maxc)
      end function multimode_int

      pure function zeros_real(n) result(x)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: x(:)
         if (n < 0) error stop 'zeros_real: n must be >= 0'
         allocate(x(n), source=0.0_dp)
      end function zeros_real

      pure function ones_real(n) result(x)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: x(:)
         if (n < 0) error stop 'ones_real: n must be >= 0'
         allocate(x(n), source=1.0_dp)
      end function ones_real

      pure function zeros_complex(n) result(x)
         integer, intent(in) :: n
         complex(kind=dp), allocatable :: x(:)
         if (n < 0) error stop 'zeros_complex: n must be >= 0'
         allocate(x(n), source=(0.0_dp, 0.0_dp))
      end function zeros_complex

      pure function ones_complex(n) result(x)
         integer, intent(in) :: n
         complex(kind=dp), allocatable :: x(:)
         if (n < 0) error stop 'ones_complex: n must be >= 0'
         allocate(x(n), source=(1.0_dp, 0.0_dp))
      end function ones_complex

      pure elemental logical function complex_isfinite(z) result(ok)
         complex(kind=dp), intent(in) :: z
         ok = ieee_is_finite(real(z, kind=dp)) .and. ieee_is_finite(aimag(z))
      end function complex_isfinite

      pure elemental logical function complex_isinf(z) result(ok)
         complex(kind=dp), intent(in) :: z
         logical :: re_inf, im_inf
         re_inf = (.not. ieee_is_finite(real(z, kind=dp))) .and. (.not. ieee_is_nan(real(z, kind=dp)))
         im_inf = (.not. ieee_is_finite(aimag(z))) .and. (.not. ieee_is_nan(aimag(z)))
         ok = re_inf .or. im_inf
      end function complex_isinf

      pure elemental logical function complex_isnan(z) result(ok)
         complex(kind=dp), intent(in) :: z
         ok = ieee_is_nan(real(z, kind=dp)) .or. ieee_is_nan(aimag(z))
      end function complex_isnan

      pure function zeros_int(n) result(x)
         integer, intent(in) :: n
         integer, allocatable :: x(:)
         if (n < 0) error stop 'zeros_int: n must be >= 0'
         allocate(x(n), source=0)
      end function zeros_int

      pure function ones_int(n) result(x)
         integer, intent(in) :: n
         integer, allocatable :: x(:)
         if (n < 0) error stop 'ones_int: n must be >= 0'
         allocate(x(n), source=1)
      end function ones_int

      pure function zeros_logical(n) result(x)
         integer, intent(in) :: n
         logical, allocatable :: x(:)
         if (n < 0) error stop 'zeros_logical: n must be >= 0'
         allocate(x(n), source=.false.)
      end function zeros_logical

      pure function ones_logical(n) result(x)
         integer, intent(in) :: n
         logical, allocatable :: x(:)
         if (n < 0) error stop 'ones_logical: n must be >= 0'
         allocate(x(n), source=.true.)
      end function ones_logical

      pure function to_lower(s)
         character(len=*), intent(in) :: s
         character(len=len(s)) :: to_lower
         integer :: i, k
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (k >= iachar("A") .and. k <= iachar("Z")) then
               to_lower(i:i) = achar(k + 32)
            else
               to_lower(i:i) = s(i:i)
            end if
         end do
      end function to_lower

      pure function to_upper(s)
         character(len=*), intent(in) :: s
         character(len=len(s)) :: to_upper
         integer :: i, k
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (k >= iachar("a") .and. k <= iachar("z")) then
               to_upper(i:i) = achar(k - 32)
            else
               to_upper(i:i) = s(i:i)
            end if
         end do
      end function to_upper

      pure logical function char_in_set(ch, set_chars)
         character(len=1), intent(in) :: ch
         character(len=*), intent(in) :: set_chars
         integer :: i
         char_in_set = .false.
         do i = 1, len(set_chars)
            if (ch == set_chars(i:i)) then
               char_in_set = .true.
               return
            end if
         end do
      end function char_in_set

      pure function str_lstrip(s, chars) result(out)
         character(len=*), intent(in) :: s
         character(len=*), intent(in), optional :: chars
         character(len=:), allocatable :: out
         character(len=:), allocatable :: set_chars
         integer :: i, n
         n = len(s)
         if (present(chars)) then
            set_chars = chars
         else
            set_chars = " "
         end if
         i = 1
         do while (i <= n .and. char_in_set(s(i:i), set_chars))
            i = i + 1
         end do
         if (i > n) then
            out = ""
         else
            out = s(i:n)
         end if
      end function str_lstrip

      pure function str_rstrip(s, chars) result(out)
         character(len=*), intent(in) :: s
         character(len=*), intent(in), optional :: chars
         character(len=:), allocatable :: out
         character(len=:), allocatable :: set_chars
         integer :: j
         if (present(chars)) then
            set_chars = chars
         else
            set_chars = " "
         end if
         j = len(s)
         do while (j >= 1 .and. char_in_set(s(j:j), set_chars))
            j = j - 1
         end do
         if (j < 1) then
            out = ""
         else
            out = s(1:j)
         end if
      end function str_rstrip

      pure function str_strip(s, chars) result(out)
         character(len=*), intent(in) :: s
         character(len=*), intent(in), optional :: chars
         character(len=:), allocatable :: out
         character(len=:), allocatable :: tmp
         if (present(chars)) then
            tmp = str_lstrip(s, chars)
            out = str_rstrip(tmp, chars)
         else
            tmp = str_lstrip(s)
            out = str_rstrip(tmp)
         end if
      end function str_strip

      pure logical function starts_with(s, prefix)
         character(len=*), intent(in) :: s, prefix
         integer :: n
         n = len(prefix)
         if (n == 0) then
            starts_with = .true.
         else if (len(s) < n) then
            starts_with = .false.
         else
            starts_with = (s(1:n) == prefix)
         end if
      end function starts_with

      pure logical function ends_with(s, suffix)
         character(len=*), intent(in) :: s, suffix
         integer :: n, ls
         n = len(suffix)
         ls = len(s)
         if (n == 0) then
            ends_with = .true.
         else if (ls < n) then
            ends_with = .false.
         else
            ends_with = (s(ls - n + 1:ls) == suffix)
         end if
      end function ends_with

      pure integer function str_find(s, sub)
         character(len=*), intent(in) :: s, sub
         integer :: p
         if (len(sub) == 0) then
            str_find = 0
            return
         end if
         p = index(s, sub)
         if (p <= 0) then
            str_find = -1
         else
            str_find = p - 1
         end if
      end function str_find

      pure integer function str_rfind(s, sub)
         character(len=*), intent(in) :: s, sub
         integer :: p
         if (len(sub) == 0) then
            str_rfind = len(s)
            return
         end if
         p = index(s, sub, back=.true.)
         if (p <= 0) then
            str_rfind = -1
         else
            str_rfind = p - 1
         end if
      end function str_rfind

      function str_replace(s, old, new) result(out)
         character(len=*), intent(in) :: s, old, new
         character(len=:), allocatable :: out
         character(len=:), allocatable :: acc
         integer :: p, pos, lo
         if (len(old) == 0) then
            out = s
            return
         end if
         acc = ""
         pos = 1
         lo = len(old)
         do
            p = index(s(pos:), old)
            if (p <= 0) exit
            acc = acc // s(pos:pos + p - 2) // new
            pos = pos + p - 1 + lo
            if (pos > len(s)) exit
         end do
         if (pos <= len(s)) then
            out = acc // s(pos:)
         else
            out = acc
         end if
      end function str_replace

      pure function str_reverse(s) result(out)
         character(len=*), intent(in) :: s
         character(len=len(s)) :: out
         integer :: i, n
         n = len(s)
         do i = 1, n
            out(i:i) = s(n - i + 1:n - i + 1)
         end do
      end function str_reverse

      pure function str_to_chars(s) result(out)
         character(len=*), intent(in) :: s
         character(len=1), allocatable :: out(:)
         integer :: i
         allocate(out(len(s)))
         do i = 1, len(s)
            out(i) = s(i:i)
         end do
      end function str_to_chars

      function str_zfill(s, width) result(out)
         character(len=*), intent(in) :: s
         integer, intent(in) :: width
         character(len=:), allocatable :: out
         character(len=:), allocatable :: t
         character(len=1) :: sign
         integer :: n, w
         t = trim(s)
         n = len(t)
         w = max(width, n)
         if (n >= 1 .and. (t(1:1) == "+" .or. t(1:1) == "-")) then
            sign = t(1:1)
            if (w <= n) then
               out = t
            else
               out = sign // repeat("0", w - n) // t(2:)
            end if
         else if (w <= n) then
            out = t
         else
            out = repeat("0", w - n) // t
         end if
      end function str_zfill

      pure function str_head(s, n) result(out)
         character(len=*), intent(in) :: s
         integer, intent(in) :: n
         character(len=:), allocatable :: out
         out = s(1:min(max(n, 0), len(s)))
      end function str_head

      pure function py_repr_str(s) result(out)
         ! Python repr() of a str: single quotes unless the text contains a
         ! single quote and no double quote; escape backslashes, the chosen
         ! quote and the common control characters.
         character(len=*), intent(in) :: s
         character(len=:), allocatable :: out
         character(len=1) :: q
         integer :: i
         q = "'"
         if (index(s, "'") > 0 .and. index(s, '"') == 0) q = '"'
         out = q
         do i = 1, len(s)
            select case (s(i:i))
            case ('\')
               out = out // '\\'
            case (achar(10))
               out = out // '\n'
            case (achar(13))
               out = out // '\r'
            case (achar(9))
               out = out // '\t'
            case default
               if (s(i:i) == q) then
                  out = out // '\' // q
               else
                  out = out // s(i:i)
               end if
            end select
         end do
         out = out // q
      end function py_repr_str

      pure function str_ljust(s, width) result(out)
         character(len=*), intent(in) :: s
         integer, intent(in) :: width
         character(len=:), allocatable :: out
         character(len=:), allocatable :: t
         integer :: n, w
         t = trim(s)
         n = len(t)
         w = max(width, n)
         if (w <= n) then
            out = t
         else
            out = t // repeat(" ", w - n)
         end if
      end function str_ljust

      pure function str_rjust(s, width) result(out)
         character(len=*), intent(in) :: s
         integer, intent(in) :: width
         character(len=:), allocatable :: out
         character(len=:), allocatable :: t
         integer :: n, w
         t = trim(s)
         n = len(t)
         w = max(width, n)
         if (w <= n) then
            out = t
         else
            out = repeat(" ", w - n) // t
         end if
      end function str_rjust

      pure subroutine append_strvec(items, tok)
         type(strvec_t), intent(inout) :: items
         character(len=*), intent(in) :: tok
         character(len=:), allocatable :: tmp(:)
         integer :: n, lnew, i
         if (.not. allocated(items%v)) then
            allocate(character(len=len(tok)) :: items%v(1))
            items%v(1) = tok
            return
         end if
         n = size(items%v)
         lnew = len(tok)
         do i = 1, n
            lnew = max(lnew, len(items%v(i)))
         end do
         allocate(character(len=lnew) :: tmp(n + 1))
         do i = 1, n
            tmp(i) = items%v(i)
         end do
         tmp(n + 1) = tok
         call move_alloc(tmp, items%v)
      end subroutine append_strvec

      pure function str_split(s, sep) result(out)
         character(len=*), intent(in) :: s
         character(len=*), intent(in), optional :: sep
         type(strvec_t) :: out
         character(len=:), allocatable :: d
         integer :: p, pos, ld, i, j
         if (present(sep)) then
            d = sep
         else
            d = " "
         end if
         if (len(d) == 0) then
            call append_strvec(out, s)
            return
         end if
         if (.not. present(sep)) then
            i = 1
            do while (i <= len(s))
               ! Fortran does not guarantee short-circuit evaluation of .and.
               ! Check the bound before evaluating the substring expression.
               do while (i <= len(s))
                  if (.not. (s(i:i) == " " .or. s(i:i) == achar(9))) exit
                  i = i + 1
               end do
               if (i > len(s)) exit
               j = i
               do while (j <= len(s))
                  if (s(j:j) == " " .or. s(j:j) == achar(9)) exit
                  j = j + 1
               end do
               call append_strvec(out, s(i:j - 1))
               i = j + 1
            end do
            return
         end if
         pos = 1
         ld = len(d)
         do
            p = index(s(pos:), d)
            if (p <= 0) exit
            call append_strvec(out, s(pos:pos + p - 2))
            pos = pos + p - 1 + ld
            if (pos > len(s) + 1) exit
         end do
         if (pos <= len(s) + 1) call append_strvec(out, s(pos:))
      end function str_split

      function csv_split_line(line, delimiter, quotechar) result(fields)
         character(len=*), intent(in) :: line
         character(len=*), intent(in), optional :: delimiter, quotechar
         character(len=:), allocatable :: fields(:)
         character(len=1) :: d, q, ch
         integer :: i, j, nf, maxlen, pos
         logical :: inq
         character(len=4096) :: tok

         d = ","
         q = '"'
         if (present(delimiter)) then
            if (len_trim(delimiter) > 0) d = delimiter(1:1)
         end if
         if (present(quotechar)) then
            if (len_trim(quotechar) > 0) q = quotechar(1:1)
         end if

         nf = 1
         inq = .false.
         do i = 1, len_trim(line)
            ch = line(i:i)
            if (ch == q) then
               inq = .not. inq
            else if (ch == d .and. .not. inq) then
               nf = nf + 1
            end if
         end do

         maxlen = 1
         inq = .false.
         j = 1
         tok = ""
         pos = 0
         do i = 1, len_trim(line)
            ch = line(i:i)
            if (ch == q) then
               inq = .not. inq
            else if (ch == d .and. .not. inq) then
               maxlen = max(maxlen, len_trim(tok))
               tok = ""
               pos = 0
               j = j + 1
            else
               pos = pos + 1
               if (pos <= len(tok)) tok(pos:pos) = ch
            end if
         end do
         maxlen = max(maxlen, len_trim(tok))

         allocate(character(len=maxlen) :: fields(nf))
         fields = ""
         inq = .false.
         j = 1
         tok = ""
         pos = 0
         do i = 1, len_trim(line)
            ch = line(i:i)
            if (ch == q) then
               inq = .not. inq
            else if (ch == d .and. .not. inq) then
               fields(j) = trim(tok)
               tok = ""
               pos = 0
               j = j + 1
            else
               pos = pos + 1
               if (pos <= len(tok)) tok(pos:pos) = ch
            end if
         end do
         if (j <= nf) fields(j) = trim(tok)
      end function csv_split_line

      pure function str_join(sep, items) result(out)
         character(len=*), intent(in) :: sep
         type(strvec_t), intent(in) :: items
         character(len=:), allocatable :: out
         integer :: i, n
         out = ""
         if (.not. allocated(items%v)) return
         n = size(items%v)
         if (n <= 0) return
         out = trim(items%v(1))
         do i = 2, n
            out = out // sep // trim(items%v(i))
         end do
      end function str_join

      pure integer function str_count(s, sub)
         character(len=*), intent(in) :: s, sub
         integer :: p, pos, ls
         if (len(sub) == 0) then
            str_count = len(s) + 1
            return
         end if
         str_count = 0
         pos = 1
         ls = len(sub)
         do
            p = index(s(pos:), sub)
            if (p <= 0) exit
            str_count = str_count + 1
            pos = pos + p - 1 + ls
            if (pos > len(s)) exit
         end do
      end function str_count

      pure logical function str_isdigit(s)
         character(len=*), intent(in) :: s
         integer :: i, k
         if (len(s) <= 0) then
            str_isdigit = .false.
            return
         end if
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (k < iachar("0") .or. k > iachar("9")) then
               str_isdigit = .false.
               return
            end if
         end do
         str_isdigit = .true.
      end function str_isdigit

      pure logical function str_isalpha(s)
         character(len=*), intent(in) :: s
         integer :: i, k
         if (len(s) <= 0) then
            str_isalpha = .false.
            return
         end if
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (.not. ((k >= iachar("A") .and. k <= iachar("Z")) .or. (k >= iachar("a") .and. k <= iachar("z")))) then
               str_isalpha = .false.
               return
            end if
         end do
         str_isalpha = .true.
      end function str_isalpha

      pure logical function str_isalnum(s)
         character(len=*), intent(in) :: s
         integer :: i, k
         if (len(s) <= 0) then
            str_isalnum = .false.
            return
         end if
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (.not. ((k >= iachar("0") .and. k <= iachar("9")) .or. &
                       (k >= iachar("A") .and. k <= iachar("Z")) .or. &
                       (k >= iachar("a") .and. k <= iachar("z")))) then
               str_isalnum = .false.
               return
            end if
         end do
         str_isalnum = .true.
      end function str_isalnum

      pure logical function str_isspace(s)
         character(len=*), intent(in) :: s
         integer :: i, k
         if (len(s) <= 0) then
            str_isspace = .false.
            return
         end if
         do i = 1, len(s)
            k = iachar(s(i:i))
            if (.not. (k == 32 .or. k == 9 .or. k == 10 .or. k == 11 .or. k == 12 .or. k == 13)) then
               str_isspace = .false.
               return
            end if
         end do
         str_isspace = .true.
      end function str_isspace

      pure function rank_min_real(x) result(r)
         ! pandas Series.rank(method="min"): tied values share the
         ! smallest rank within their tie group -- rank(i) = 1 + (count
         ! of non-NaN elements strictly less than x(i)). NaN entries are
         ! excluded from ranking and stay NaN in the result, matching
         ! pandas' default na_option="keep". O(n**2) is fine here --
         ! .rank() is used on small per-model/per-symbol comparison
         ! tables, not large simulation arrays.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: r(:)
         integer :: i, j, n, c
         n = size(x)
         allocate(r(n))
         do i = 1, n
            if (ieee_is_nan(x(i))) then
               r(i) = ieee_value(1.0_dp, ieee_quiet_nan)
               cycle
            end if
            c = 0
            do j = 1, n
               if ((.not. ieee_is_nan(x(j))) .and. x(j) < x(i)) c = c + 1
            end do
            r(i) = real(c + 1, kind=dp)
         end do
      end function rank_min_real

      pure function rank_max_real(x) result(r)
         ! pandas Series.rank(method="max"): tied values share the
         ! largest rank within their tie group -- rank(i) = count of
         ! non-NaN elements <= x(i) (equivalently: 1 + count strictly
         ! less + count of other tied elements). See rank_min_real for
         ! the NaN/complexity notes, which apply here too.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: r(:)
         integer :: i, j, n, c
         n = size(x)
         allocate(r(n))
         do i = 1, n
            if (ieee_is_nan(x(i))) then
               r(i) = ieee_value(1.0_dp, ieee_quiet_nan)
               cycle
            end if
            c = 0
            do j = 1, n
               if ((.not. ieee_is_nan(x(j))) .and. x(j) <= x(i)) c = c + 1
            end do
            r(i) = real(c, kind=dp)
         end do
      end function rank_max_real

      pure function rank_average_real(x) result(r)
         ! pandas Series.rank(method="average", the default): tied
         ! values share the mean of the ranks they'd occupy, which is
         ! just (rank_min(i) + rank_max(i)) / 2 for every tie group. See
         ! rank_min_real for the NaN/complexity notes, which apply here
         ! too.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: r(:)
         integer :: i, j, n, c_lt, c_le
         n = size(x)
         allocate(r(n))
         do i = 1, n
            if (ieee_is_nan(x(i))) then
               r(i) = ieee_value(1.0_dp, ieee_quiet_nan)
               cycle
            end if
            c_lt = 0
            c_le = 0
            do j = 1, n
               if (ieee_is_nan(x(j))) cycle
               if (x(j) < x(i)) c_lt = c_lt + 1
               if (x(j) <= x(i)) c_le = c_le + 1
            end do
            r(i) = (real(c_lt + 1, kind=dp) + real(c_le, kind=dp)) / 2.0_dp
         end do
      end function rank_average_real

      pure function rank_first_real(x) result(r)
         ! pandas Series.rank(method="first"): ties are broken by order
         ! of appearance -- among equal values, the one occurring
         ! earlier in x gets the lower rank. rank(i) = 1 + (count of
         ! non-NaN elements strictly less than x(i)) + (count of earlier
         ! non-NaN elements equal to x(i)). See rank_min_real for the
         ! NaN/complexity notes, which apply here too.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: r(:)
         integer :: i, j, n, c
         n = size(x)
         allocate(r(n))
         do i = 1, n
            if (ieee_is_nan(x(i))) then
               r(i) = ieee_value(1.0_dp, ieee_quiet_nan)
               cycle
            end if
            c = 0
            do j = 1, n
               if (ieee_is_nan(x(j))) cycle
               if (x(j) < x(i)) then
                  c = c + 1
               else if (x(j) == x(i) .and. j < i) then
                  c = c + 1
               end if
            end do
            r(i) = real(c + 1, kind=dp)
         end do
      end function rank_first_real

      pure function rank_dense_real(x) result(r)
         ! pandas Series.rank(method="dense"): like method="min" but
         ! without gaps between tie groups -- rank(i) = 1 + (count of
         ! DISTINCT non-NaN values strictly less than x(i)). Builds the
         ! distinct-value set first (O(n**2), same complexity budget as
         ! rank_min_real) rather than checking distinctness inline
         ! per-(i,j) pair, which would be O(n**3).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: r(:)
         real(kind=dp), allocatable :: uniq(:)
         logical, allocatable :: is_first(:)
         integer :: i, j, n, nu, c
         n = size(x)
         allocate(r(n))
         allocate(is_first(n))
         do i = 1, n
            is_first(i) = .not. ieee_is_nan(x(i))
            if (is_first(i)) then
               do j = 1, i - 1
                  if ((.not. ieee_is_nan(x(j))) .and. x(j) == x(i)) then
                     is_first(i) = .false.
                     exit
                  end if
               end do
            end if
         end do
         nu = count(is_first)
         allocate(uniq(nu))
         c = 0
         do i = 1, n
            if (is_first(i)) then
               c = c + 1
               uniq(c) = x(i)
            end if
         end do
         do i = 1, n
            if (ieee_is_nan(x(i))) then
               r(i) = ieee_value(1.0_dp, ieee_quiet_nan)
               cycle
            end if
            c = 0
            do j = 1, nu
               if (uniq(j) < x(i)) c = c + 1
            end do
            r(i) = real(c + 1, kind=dp)
         end do
      end function rank_dense_real

      pure function cumsum_real(x) result(y)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, n
         n = size(x)
         allocate(y(1:n))
         if (n >= 1) then
            y(1) = x(1)
            do i = 2, n
               y(i) = y(i-1) + x(i)
            end do
         end if
      end function cumsum_real

      pure function cumsum_real_axis0_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         integer :: i, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (m >= 1) then
            y(1,:) = x(1,:)
            do i = 2, m
               y(i,:) = y(i-1,:) + x(i,:)
            end do
         end if
      end function cumsum_real_axis0_2d

      pure function cumsum_real_axis1_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         integer :: j, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (n >= 1) then
            y(:,1) = x(:,1)
            do j = 2, n
               y(:,j) = y(:,j-1) + x(:,j)
            end do
         end if
      end function cumsum_real_axis1_2d

      pure function unique_int(x) result(y)
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         integer, allocatable :: tmp(:)
         integer :: i, j, n, m, key
         n = size(x)
         allocate(tmp(1:n))
         tmp = x
         do i = 2, n
            key = tmp(i)
            j = i - 1
            do while (j >= 1)
               if (tmp(j) <= key) exit
               tmp(j+1) = tmp(j)
               j = j - 1
            end do
            tmp(j+1) = key
         end do
         m = 0
         do i = 1, n
            if (i == 1) then
               m = m + 1
            else if (tmp(i) /= tmp(i-1)) then
               m = m + 1
            end if
         end do
         allocate(y(1:m))
         m = 0
         do i = 1, n
            if (i == 1) then
               m = m + 1
               y(m) = tmp(i)
            else if (tmp(i) /= tmp(i-1)) then
               m = m + 1
               y(m) = tmp(i)
            end if
         end do
         deallocate(tmp)
      end function unique_int

      pure function unique_char(x) result(y)
         character(len=*), intent(in) :: x(:)
         character(len=:), allocatable :: y(:)
         integer :: i, j, n, m, llen
         logical :: seen
         n = size(x)
         llen = len(x)
         if (llen < 1) llen = 1
         m = 0
         do i = 1, n
            seen = .false.
            do j = 1, i - 1
               if (x(i) == x(j)) then
                  seen = .true.
                  exit
               end if
            end do
            if (.not. seen) m = m + 1
         end do
         allocate(character(len=llen) :: y(m))
         m = 0
         do i = 1, n
            seen = .false.
            do j = 1, i - 1
               if (x(i) == x(j)) then
                  seen = .true.
                  exit
               end if
            end do
            if (.not. seen) then
               m = m + 1
               y(m) = x(i)
            end if
         end do
      end function unique_char

      pure function tile_int(x, reps) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: reps
         integer, allocatable :: y(:)
         integer :: n, r, k, i1, i2
         n = size(x)
         r = max(0, reps)
         allocate(y(1:n*r))
         do k = 1, r
            i1 = (k - 1) * n + 1
            i2 = k * n
            y(i1:i2) = x
         end do
      end function tile_int

      pure function tile_int_2d(x, reps0, reps1) result(y)
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: reps0, reps1
         integer, allocatable :: y(:,:)
         integer :: m, n, r0, r1, i, j
         m = size(x,1)
         n = size(x,2)
         r0 = max(0, reps0)
         r1 = max(0, reps1)
         allocate(y(1:m*r0, 1:n*r1))
         do i = 1, r0
            do j = 1, r1
               y((i-1)*m+1:i*m, (j-1)*n+1:j*n) = x
            end do
         end do
      end function tile_int_2d

      pure function diag_from_vec_int(v) result(x)
         integer, intent(in) :: v(:)
         integer, allocatable :: x(:,:)
         integer :: i, n
         n = size(v)
         allocate(x(1:n,1:n), source=0)
         do i = 1, n
            x(i,i) = v(i)
         end do
      end function diag_from_vec_int

      pure function cumprod_int(x) result(y)
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         integer :: i, n
         n = size(x)
         allocate(y(1:n))
         if (n >= 1) then
            y(1) = x(1)
            do i = 2, n
               y(i) = y(i-1) * x(i)
            end do
         end if
      end function cumprod_int

      pure function repeat_int(x, reps) result(y)
         integer, intent(in) :: x(:)
         integer, intent(in) :: reps
         integer, allocatable :: y(:)
         integer :: i, j, n, r, k
         n = size(x)
         r = max(0, reps)
         allocate(y(1:n*r))
         k = 0
         do i = 1, n
            do j = 1, r
               k = k + 1
               y(k) = x(i)
            end do
         end do
      end function repeat_int

      pure function repeat_int_axis0_2d(x, reps) result(y)
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: reps
         integer, allocatable :: y(:,:)
         integer :: i, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m*r, 1:n))
         do i = 1, m
            do k = 1, r
               y((i-1)*r + k, :) = x(i, :)
            end do
         end do
      end function repeat_int_axis0_2d

      pure function repeat_int_axis1_2d(x, reps) result(y)
         integer, intent(in) :: x(:,:)
         integer, intent(in) :: reps
         integer, allocatable :: y(:,:)
         integer :: j, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m, 1:n*r))
         do j = 1, n
            do k = 1, r
               y(:, (j-1)*r + k) = x(:, j)
            end do
         end do
      end function repeat_int_axis1_2d

      pure function diag_from_mat_complex(a) result(v)
         complex(kind=dp), intent(in) :: a(:,:)
         complex(kind=dp), allocatable :: v(:)
         integer :: i, n
         n = min(size(a,1), size(a,2))
         allocate(v(n))
         do i = 1, n
            v(i) = a(i,i)
         end do
      end function diag_from_mat_complex

      pure function diag_from_vec_complex(v) result(a)
         complex(kind=dp), intent(in) :: v(:)
         complex(kind=dp), allocatable :: a(:,:)
         integer :: i, n
         n = size(v)
         allocate(a(n,n), source=cmplx(0.0_dp, 0.0_dp, kind=dp))
         do i = 1, n
            a(i,i) = v(i)
         end do
      end function diag_from_vec_complex

      pure function diag_from_mat_real(a) result(v)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: v(:)
         integer :: i, n
         n = min(size(a,1), size(a,2))
         allocate(v(1:n))
         do i = 1, n
            v(i) = a(i,i)
         end do
      end function diag_from_mat_real

      pure function diagonal_real_2d(a, offset) result(v)
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: offset
         real(kind=dp), allocatable :: v(:)
         integer :: i, n, k
         k = 0
         if (present(offset)) k = offset
         if (k >= 0) then
            n = min(size(a,1), max(0, size(a,2) - k))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i, i + k)
            end do
         else
            n = min(max(0, size(a,1) + k), size(a,2))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i - k, i)
            end do
         end if
      end function diagonal_real_2d

      pure function diagonal_complex_2d(a, offset) result(v)
         complex(kind=dp), intent(in) :: a(:,:)
         integer, intent(in), optional :: offset
         complex(kind=dp), allocatable :: v(:)
         integer :: i, n, k
         k = 0
         if (present(offset)) k = offset
         if (k >= 0) then
            n = min(size(a,1), max(0, size(a,2) - k))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i, i + k)
            end do
         else
            n = min(max(0, size(a,1) + k), size(a,2))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i - k, i)
            end do
         end if
      end function diagonal_complex_2d

      pure function cumsum_int(x) result(y)
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         integer :: i, n
         n = size(x)
         allocate(y(1:n))
         if (n >= 1) then
            y(1) = x(1)
            do i = 2, n
               y(i) = y(i-1) + x(i)
            end do
         end if
      end function cumsum_int

      pure function cumsum_int_axis0_2d(x) result(y)
         integer, intent(in) :: x(:,:)
         integer, allocatable :: y(:,:)
         integer :: i, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (m >= 1) then
            y(1,:) = x(1,:)
            do i = 2, m
               y(i,:) = y(i-1,:) + x(i,:)
            end do
         end if
      end function cumsum_int_axis0_2d

      pure function cumsum_int_axis1_2d(x) result(y)
         integer, intent(in) :: x(:,:)
         integer, allocatable :: y(:,:)
         integer :: j, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (n >= 1) then
            y(:,1) = x(:,1)
            do j = 2, n
               y(:,j) = y(:,j-1) + x(:,j)
            end do
         end if
      end function cumsum_int_axis1_2d

      pure function cumprod_real_axis0_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         integer :: i, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (m >= 1) then
            y(1,:) = x(1,:)
            do i = 2, m
               y(i,:) = y(i-1,:) * x(i,:)
            end do
         end if
      end function cumprod_real_axis0_2d

      pure function cumprod_real_axis1_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         integer :: j, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (n >= 1) then
            y(:,1) = x(:,1)
            do j = 2, n
               y(:,j) = y(:,j-1) * x(:,j)
            end do
         end if
      end function cumprod_real_axis1_2d

      pure function cumprod_int_axis0_2d(x) result(y)
         integer, intent(in) :: x(:,:)
         integer, allocatable :: y(:,:)
         integer :: i, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (m >= 1) then
            y(1,:) = x(1,:)
            do i = 2, m
               y(i,:) = y(i-1,:) * x(i,:)
            end do
         end if
      end function cumprod_int_axis0_2d

      pure function cumprod_int_axis1_2d(x) result(y)
         integer, intent(in) :: x(:,:)
         integer, allocatable :: y(:,:)
         integer :: j, m, n
         m = size(x,1)
         n = size(x,2)
         allocate(y(1:m,1:n))
         if (n >= 1) then
            y(:,1) = x(:,1)
            do j = 2, n
               y(:,j) = y(:,j-1) * x(:,j)
            end do
         end if
      end function cumprod_int_axis1_2d

      pure function diag_from_vec_real(v) result(x)
         real(kind=dp), intent(in) :: v(:)
         real(kind=dp), allocatable :: x(:,:)
         integer :: i, n
         n = size(v)
         allocate(x(1:n,1:n), source=0.0_dp)
         do i = 1, n
            x(i,i) = v(i)
         end do
      end function diag_from_vec_real

      pure function diagonal_real_3d_axis12(a, offset) result(v)
         real(kind=dp), intent(in) :: a(:,:,:)
         integer, intent(in), optional :: offset
         real(kind=dp), allocatable :: v(:,:)
         integer :: i, j, n, k
         k = 0
         if (present(offset)) k = offset
         if (k >= 0) then
            n = min(size(a,2), max(0, size(a,3) - k))
            allocate(v(1:size(a,1),1:n))
            do i = 1, size(a,1)
               do j = 1, n
                  v(i,j) = a(i, j, j + k)
               end do
            end do
         else
            n = min(max(0, size(a,2) + k), size(a,3))
            allocate(v(1:size(a,1),1:n))
            do i = 1, size(a,1)
               do j = 1, n
                  v(i,j) = a(i, j - k, j)
               end do
            end do
         end if
      end function diagonal_real_3d_axis12

      pure function repeat_real(x, reps) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: reps
         real(kind=dp), allocatable :: y(:)
         integer :: i, j, n, r, k
         n = size(x)
         r = max(0, reps)
         allocate(y(1:n*r))
         k = 0
         do i = 1, n
            do j = 1, r
               k = k + 1
               y(k) = x(i)
            end do
         end do
      end function repeat_real

      pure function repeat_real_axis0_2d(x, reps) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: reps
         real(kind=dp), allocatable :: y(:,:)
         integer :: i, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m*r, 1:n))
         do i = 1, m
            do k = 1, r
               y((i-1)*r + k, :) = x(i, :)
            end do
         end do
      end function repeat_real_axis0_2d

      pure function repeat_real_axis1_2d(x, reps) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: reps
         real(kind=dp), allocatable :: y(:,:)
         integer :: j, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m, 1:n*r))
         do j = 1, n
            do k = 1, r
               y(:, (j-1)*r + k) = x(:, j)
            end do
         end do
      end function repeat_real_axis1_2d

      pure function repeat_logical(x, reps) result(y)
         logical, intent(in) :: x(:)
         integer, intent(in) :: reps
         logical, allocatable :: y(:)
         integer :: i, j, n, r, k
         n = size(x)
         r = max(0, reps)
         allocate(y(1:n*r))
         k = 0
         do i = 1, n
            do j = 1, r
               k = k + 1
               y(k) = x(i)
            end do
         end do
      end function repeat_logical

      pure function repeat_logical_axis0_2d(x, reps) result(y)
         logical, intent(in) :: x(:,:)
         integer, intent(in) :: reps
         logical, allocatable :: y(:,:)
         integer :: i, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m*r, 1:n))
         do i = 1, m
            do k = 1, r
               y((i-1)*r + k, :) = x(i, :)
            end do
         end do
      end function repeat_logical_axis0_2d

      pure function repeat_logical_axis1_2d(x, reps) result(y)
         logical, intent(in) :: x(:,:)
         integer, intent(in) :: reps
         logical, allocatable :: y(:,:)
         integer :: j, k, m, n, r
         m = size(x,1)
         n = size(x,2)
         r = max(0, reps)
         allocate(y(1:m, 1:n*r))
         do j = 1, n
            do k = 1, r
               y(:, (j-1)*r + k) = x(:, j)
            end do
         end do
      end function repeat_logical_axis1_2d

      pure function diag_from_mat_int(a) result(v)
         integer, intent(in) :: a(:,:)
         integer, allocatable :: v(:)
         integer :: i, n
         n = min(size(a,1), size(a,2))
         allocate(v(1:n))
         do i = 1, n
            v(i) = a(i,i)
         end do
      end function diag_from_mat_int

      pure function diagonal_int_2d(a, offset) result(v)
         integer, intent(in) :: a(:,:)
         integer, intent(in), optional :: offset
         integer, allocatable :: v(:)
         integer :: i, n, k
         k = 0
         if (present(offset)) k = offset
         if (k >= 0) then
            n = min(size(a,1), max(0, size(a,2) - k))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i, i + k)
            end do
         else
            n = min(max(0, size(a,1) + k), size(a,2))
            allocate(v(1:n))
            do i = 1, n
               v(i) = a(i - k, i)
            end do
         end if
      end function diagonal_int_2d

      pure function diagonal_int_3d_axis12(a, offset) result(v)
         integer, intent(in) :: a(:,:,:)
         integer, intent(in), optional :: offset
         integer, allocatable :: v(:,:)
         integer :: i, j, n, k
         k = 0
         if (present(offset)) k = offset
         if (k >= 0) then
            n = min(size(a,2), max(0, size(a,3) - k))
            allocate(v(1:size(a,1),1:n))
            do i = 1, size(a,1)
               do j = 1, n
                  v(i,j) = a(i, j, j + k)
               end do
            end do
         else
            n = min(max(0, size(a,2) + k), size(a,3))
            allocate(v(1:size(a,1),1:n))
            do i = 1, size(a,1)
               do j = 1, n
                  v(i,j) = a(i, j - k, j)
               end do
            end do
         end if
      end function diagonal_int_3d_axis12

      pure function tile_real(x, reps) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: reps
         real(kind=dp), allocatable :: y(:)
         integer :: n, r, k, i1, i2
         n = size(x)
         r = max(0, reps)
         allocate(y(1:n*r))
         do k = 1, r
            i1 = (k - 1) * n + 1
            i2 = k * n
            y(i1:i2) = x
         end do
      end function tile_real

      pure function tile_real_2d(x, reps0, reps1) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: reps0, reps1
         real(kind=dp), allocatable :: y(:,:)
         integer :: m, n, r0, r1, i, j
         m = size(x,1)
         n = size(x,2)
         r0 = max(0, reps0)
         r1 = max(0, reps1)
         allocate(y(1:m*r0, 1:n*r1))
         do i = 1, r0
            do j = 1, r1
               y((i-1)*m+1:i*m, (j-1)*n+1:j*n) = x
            end do
         end do
      end function tile_real_2d

      pure function eye_real(n, m, k) result(x)
         ! np.eye(n, m, k): ones on diagonal k (above the main one for k > 0).
         integer, intent(in) :: n
         integer, intent(in), optional :: m, k
         real(kind=dp), allocatable :: x(:,:)
         integer :: mm, kk, i
         mm = n
         if (present(m)) mm = m
         kk = 0
         if (present(k)) kk = k
         if (n < 0 .or. mm < 0) error stop "eye_real: dimensions must be >= 0"
         allocate(x(1:n,1:mm), source=0.0_dp)
         do i = max(1, 1 - kk), min(n, mm - kk)
            x(i,i+kk) = 1.0_dp
         end do
      end function eye_real

      pure function unique_real(x) result(y)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         real(kind=dp), allocatable :: tmp(:)
         integer :: i, n, m
         n = size(x)
         allocate(tmp(1:n))
         tmp = x
         call sort_real_vec(tmp)
         ! NaNs sort last; numpy keeps one (equal_nan).
         m = 0
         do i = 1, n
            if (i == 1) then
               m = m + 1
            else if (ieee_is_nan(tmp(i))) then
               if (.not. ieee_is_nan(tmp(i-1))) m = m + 1
            else if (tmp(i) /= tmp(i-1)) then
               m = m + 1
            end if
         end do
         allocate(y(1:m))
         m = 0
         do i = 1, n
            if (i == 1) then
               m = m + 1
               y(m) = tmp(i)
            else if (ieee_is_nan(tmp(i))) then
               if (.not. ieee_is_nan(tmp(i-1))) then
                  m = m + 1
                  y(m) = tmp(i)
               end if
            else if (tmp(i) /= tmp(i-1)) then
               m = m + 1
               y(m) = tmp(i)
            end if
         end do
         deallocate(tmp)
      end function unique_real

      pure function cumprod_real(x) result(y)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i, n
         n = size(x)
         allocate(y(1:n))
         if (n >= 1) then
            y(1) = x(1)
            do i = 2, n
               y(i) = y(i-1) * x(i)
            end do
         end if
      end function cumprod_real

      pure function gradient_1d(x) result(g)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: g(:)
         integer :: n
         n = size(x)
         allocate(g(1:n))
         if (n <= 0) return
         if (n == 1) then
            g(1) = 0.0_dp
            return
         end if
         if (n == 2) then
            g(1) = x(2) - x(1)
            g(2) = x(2) - x(1)
            return
         end if
         g(1) = x(2) - x(1)
         g(2:n-1) = 0.5_dp * (x(3:n) - x(1:n-2))
         g(n) = x(n) - x(n-1)
      end function gradient_1d

      ! ---- np.polynomial: orthogonal and power series ----------------------
      ! Families: 1 power series (coefficients lowest degree first, unlike
      ! np.polyval), 2 Chebyshev, 3 Legendre, 4 Hermite (physicists'),
      ! 5 HermiteE (probabilists'), 6 Laguerre. The algorithms are numpy's
      ! (Clenshaw-style evaluation, the three-term recurrences for the
      ! Vandermonde matrices, numpy's derivative and integral recurrences, and
      ! numpy's column-scaled least-squares fit), so results agree with numpy
      ! to rounding.

      pure function opoly_val0(fam, x, c) result(y)
         ! Value at x of the series with coefficients c in family fam.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y, c0, c1, tmp, x2, nd
         integer :: n, i
         n = size(c)
         if (n == 0) error stop "np.polynomial: the coefficient array is empty"
         if (fam == 1) then
            c0 = c(n)
            do i = 2, n
               c0 = c(n - i + 1) + c0 * x
            end do
            y = c0
            return
         end if
         x2 = 2.0_dp * x
         if (n == 1) then
            c0 = c(1)
            c1 = 0.0_dp
         else if (n == 2) then
            c0 = c(1)
            c1 = c(2)
         else
            nd = real(n, kind=dp)
            c0 = c(n - 1)
            c1 = c(n)
            do i = 3, n
               tmp = c0
               select case (fam)
               case (2)
                  c0 = c(n - i + 1) - c1
                  c1 = tmp + c1 * x2
               case (3)
                  nd = nd - 1.0_dp
                  c0 = c(n - i + 1) - (c1 * (nd - 1.0_dp)) / nd
                  c1 = tmp + (c1 * x * (2.0_dp * nd - 1.0_dp)) / nd
               case (4)
                  nd = nd - 1.0_dp
                  c0 = c(n - i + 1) - c1 * (2.0_dp * (nd - 1.0_dp))
                  c1 = tmp + c1 * x2
               case (5)
                  nd = nd - 1.0_dp
                  c0 = c(n - i + 1) - c1 * (nd - 1.0_dp)
                  c1 = tmp + c1 * x
               case default
                  nd = nd - 1.0_dp
                  c0 = c(n - i + 1) - (c1 * (nd - 1.0_dp)) / nd
                  c1 = tmp + (c1 * ((2.0_dp * nd - 1.0_dp) - x)) / nd
               end select
            end do
         end if
         select case (fam)
         case (4)
            y = c0 + c1 * x2
         case (6)
            y = c0 + c1 * (1.0_dp - x)
         case default
            y = c0 + c1 * x
         end select
      end function opoly_val0

      pure function opoly_val2d0(fam, x, y, c) result(r)
         ! sum_ij c(i, j) P_i(x) P_j(y) for the basis P of family fam (as
         ! opoly_val0): numpy's <f>val2d at one point.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         real(kind=dp) :: v(size(c, 1))
         integer :: i
         do i = 1, size(c, 1)
            v(i) = opoly_val0(fam, y, c(i, :))
         end do
         r = opoly_val0(fam, x, v)
      end function opoly_val2d0

      pure function opoly_val3d0(fam, x, y, z, c) result(r)
         ! sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z): <f>val3d at one point.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         real(kind=dp) :: v(size(c, 1))
         integer :: i
         do i = 1, size(c, 1)
            v(i) = opoly_val2d0(fam, y, z, c(i, :, :))
         end do
         r = opoly_val0(fam, x, v)
      end function opoly_val3d0

      pure function opoly_grid2d(fam, x, y, c) result(r)
         ! r(a, b) = sum_ij c(i, j) P_i(x(a)) P_j(y(b)): <f>grid2d.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         if (size(c, 1) == 0 .or. size(c, 2) == 0) error stop "np.polynomial: the coefficient array is empty"
         r = matmul(matmul(opoly_vander(fam, x, size(c, 1) - 1), c), &
            transpose(opoly_vander(fam, y, size(c, 2) - 1)))
      end function opoly_grid2d

      pure function opoly_grid3d(fam, x, y, z, c) result(r)
         ! r(a, b, d) = sum_ijk c(i, j, k) P_i(x(a)) P_j(y(b)) P_k(z(d)):
         ! <f>grid3d.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         real(kind=dp), allocatable :: vz(:,:)
         real(kind=dp) :: cz(size(c, 1), size(c, 2))
         integer :: d, k
         if (size(c, 3) == 0) error stop "np.polynomial: the coefficient array is empty"
         vz = opoly_vander(fam, z, size(c, 3) - 1)
         allocate(r(size(x), size(y), size(z)))
         do d = 1, size(z)
            cz = 0.0_dp
            do k = 1, size(c, 3)
               cz = cz + c(:, :, k) * vz(d, k)
            end do
            r(:, :, d) = opoly_grid2d(fam, x, y, cz)
         end do
      end function opoly_grid3d

      pure function powvalfromroots_0(x, r) result(y)
         ! np.polynomial.polynomial.polyvalfromroots: prod(x - r).
         real(kind=dp), intent(in) :: x, r(:)
         real(kind=dp) :: y
         y = product(x - r)
      end function powvalfromroots_0

      pure function powvalfromroots_1(x, r) result(y)
         real(kind=dp), intent(in) :: x(:), r(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = product(x(i) - r)
         end do
      end function powvalfromroots_1

      pure function powvalfromroots_2(x, r) result(y)
         real(kind=dp), intent(in) :: x(:,:), r(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = product(x(i, j) - r)
            end do
         end do
      end function powvalfromroots_2

      pure function powval2d_0(x, y, c) result(r)
         ! np.polynomial.polynomial.polyval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(1, x, y, c)
      end function powval2d_0

      pure function powval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "polyval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(1, x(i), y(i), c)
         end do
      end function powval2d_1

      pure function powval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "polyval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(1, x(i, j), y(i, j), c)
            end do
         end do
      end function powval2d_2

      pure function powval3d_0(x, y, z, c) result(r)
         ! np.polynomial.polynomial.polyval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(1, x, y, z, c)
      end function powval3d_0

      pure function powval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "polyval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(1, x(i), y(i), z(i), c)
         end do
      end function powval3d_1

      pure function powgrid2d(x, y, c) result(r)
         ! np.polynomial.polynomial.polygrid2d: r(a, b) = polyval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(1, x, y, c)
      end function powgrid2d

      pure function powgrid3d(x, y, z, c) result(r)
         ! np.polynomial.polynomial.polygrid3d: r(a, b, d) = polyval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(1, x, y, z, c)
      end function powgrid3d

      pure function chebval2d_0(x, y, c) result(r)
         ! np.polynomial.chebyshev.chebval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(2, x, y, c)
      end function chebval2d_0

      pure function chebval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "chebval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(2, x(i), y(i), c)
         end do
      end function chebval2d_1

      pure function chebval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "chebval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(2, x(i, j), y(i, j), c)
            end do
         end do
      end function chebval2d_2

      pure function chebval3d_0(x, y, z, c) result(r)
         ! np.polynomial.chebyshev.chebval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(2, x, y, z, c)
      end function chebval3d_0

      pure function chebval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "chebval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(2, x(i), y(i), z(i), c)
         end do
      end function chebval3d_1

      pure function chebgrid2d(x, y, c) result(r)
         ! np.polynomial.chebyshev.chebgrid2d: r(a, b) = chebval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(2, x, y, c)
      end function chebgrid2d

      pure function chebgrid3d(x, y, z, c) result(r)
         ! np.polynomial.chebyshev.chebgrid3d: r(a, b, d) = chebval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(2, x, y, z, c)
      end function chebgrid3d

      pure function legval2d_0(x, y, c) result(r)
         ! np.polynomial.legendre.legval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(3, x, y, c)
      end function legval2d_0

      pure function legval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "legval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(3, x(i), y(i), c)
         end do
      end function legval2d_1

      pure function legval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "legval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(3, x(i, j), y(i, j), c)
            end do
         end do
      end function legval2d_2

      pure function legval3d_0(x, y, z, c) result(r)
         ! np.polynomial.legendre.legval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(3, x, y, z, c)
      end function legval3d_0

      pure function legval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "legval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(3, x(i), y(i), z(i), c)
         end do
      end function legval3d_1

      pure function leggrid2d(x, y, c) result(r)
         ! np.polynomial.legendre.leggrid2d: r(a, b) = legval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(3, x, y, c)
      end function leggrid2d

      pure function leggrid3d(x, y, z, c) result(r)
         ! np.polynomial.legendre.leggrid3d: r(a, b, d) = legval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(3, x, y, z, c)
      end function leggrid3d

      pure function hermval2d_0(x, y, c) result(r)
         ! np.polynomial.hermite.hermval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(4, x, y, c)
      end function hermval2d_0

      pure function hermval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "hermval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(4, x(i), y(i), c)
         end do
      end function hermval2d_1

      pure function hermval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "hermval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(4, x(i, j), y(i, j), c)
            end do
         end do
      end function hermval2d_2

      pure function hermval3d_0(x, y, z, c) result(r)
         ! np.polynomial.hermite.hermval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(4, x, y, z, c)
      end function hermval3d_0

      pure function hermval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "hermval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(4, x(i), y(i), z(i), c)
         end do
      end function hermval3d_1

      pure function hermgrid2d(x, y, c) result(r)
         ! np.polynomial.hermite.hermgrid2d: r(a, b) = hermval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(4, x, y, c)
      end function hermgrid2d

      pure function hermgrid3d(x, y, z, c) result(r)
         ! np.polynomial.hermite.hermgrid3d: r(a, b, d) = hermval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(4, x, y, z, c)
      end function hermgrid3d

      pure function hermeval2d_0(x, y, c) result(r)
         ! np.polynomial.hermite_e.hermeval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(5, x, y, c)
      end function hermeval2d_0

      pure function hermeval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "hermeval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(5, x(i), y(i), c)
         end do
      end function hermeval2d_1

      pure function hermeval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "hermeval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(5, x(i, j), y(i, j), c)
            end do
         end do
      end function hermeval2d_2

      pure function hermeval3d_0(x, y, z, c) result(r)
         ! np.polynomial.hermite_e.hermeval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(5, x, y, z, c)
      end function hermeval3d_0

      pure function hermeval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "hermeval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(5, x(i), y(i), z(i), c)
         end do
      end function hermeval3d_1

      pure function hermegrid2d(x, y, c) result(r)
         ! np.polynomial.hermite_e.hermegrid2d: r(a, b) = hermeval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(5, x, y, c)
      end function hermegrid2d

      pure function hermegrid3d(x, y, z, c) result(r)
         ! np.polynomial.hermite_e.hermegrid3d: r(a, b, d) = hermeval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(5, x, y, z, c)
      end function hermegrid3d

      pure function lagval2d_0(x, y, c) result(r)
         ! np.polynomial.laguerre.lagval2d: sum_ij c(i, j) P_i(x) P_j(y).
         real(kind=dp), intent(in) :: x, y, c(:,:)
         real(kind=dp) :: r
         r = opoly_val2d0(6, x, y, c)
      end function lagval2d_0

      pure function lagval2d_1(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x)) error stop "lagval2d: x and y must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val2d0(6, x(i), y(i), c)
         end do
      end function lagval2d_1

      pure function lagval2d_2(x, y, c) result(r)
         real(kind=dp), intent(in) :: x(:,:), y(:,:), c(:,:)
         real(kind=dp) :: r(size(x, 1), size(x, 2))
         integer :: i, j
         if (any(shape(y) /= shape(x))) error stop "lagval2d: x and y must have the same shape"
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               r(i, j) = opoly_val2d0(6, x(i, j), y(i, j), c)
            end do
         end do
      end function lagval2d_2

      pure function lagval3d_0(x, y, z, c) result(r)
         ! np.polynomial.laguerre.lagval3d: sum_ijk c(i, j, k) P_i(x) P_j(y) P_k(z).
         real(kind=dp), intent(in) :: x, y, z, c(:,:,:)
         real(kind=dp) :: r
         r = opoly_val3d0(6, x, y, z, c)
      end function lagval3d_0

      pure function lagval3d_1(x, y, z, c) result(r)
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp) :: r(size(x))
         integer :: i
         if (size(y) /= size(x) .or. size(z) /= size(x)) error stop "lagval3d: x, y and z must have the same shape"
         do i = 1, size(x)
            r(i) = opoly_val3d0(6, x(i), y(i), z(i), c)
         end do
      end function lagval3d_1

      pure function laggrid2d(x, y, c) result(r)
         ! np.polynomial.laguerre.laggrid2d: r(a, b) = lagval2d(x(a), y(b), c).
         real(kind=dp), intent(in) :: x(:), y(:), c(:,:)
         real(kind=dp), allocatable :: r(:,:)
         r = opoly_grid2d(6, x, y, c)
      end function laggrid2d

      pure function laggrid3d(x, y, z, c) result(r)
         ! np.polynomial.laguerre.laggrid3d: r(a, b, d) = lagval3d(x(a), y(b), z(d), c).
         real(kind=dp), intent(in) :: x(:), y(:), z(:), c(:,:,:)
         real(kind=dp), allocatable :: r(:,:,:)
         r = opoly_grid3d(6, x, y, z, c)
      end function laggrid3d

      pure function opoly_vander(fam, x, deg) result(v)
         ! Pseudo-Vandermonde matrix: v(i, j+1) = basis function of degree j
         ! at x(i), j = 0..deg.
         integer, intent(in) :: fam, deg
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: v(:,:)
         integer :: i
         real(kind=dp) :: ri
         if (deg < 0) error stop "np.polynomial: deg must be non-negative"
         allocate(v(size(x), deg + 1))
         ! Degree 0 is 1, also at NaN and inf.
         v(:, 1) = 1.0_dp
         if (deg == 0) return
         select case (fam)
         case (1, 2, 3, 5)
            v(:, 2) = x
         case (4)
            v(:, 2) = x * 2.0_dp
         case default
            v(:, 2) = 1.0_dp - x
         end select
         do i = 2, deg
            ri = real(i, kind=dp)
            select case (fam)
            case (1)
               v(:, i + 1) = v(:, i) * x
            case (2)
               v(:, i + 1) = v(:, i) * (2.0_dp * x) - v(:, i - 1)
            case (3)
               v(:, i + 1) = (v(:, i) * x * (2.0_dp * ri - 1.0_dp) - v(:, i - 1) * (ri - 1.0_dp)) / ri
            case (4)
               v(:, i + 1) = v(:, i) * (x * 2.0_dp) - v(:, i - 1) * (2.0_dp * (ri - 1.0_dp))
            case (5)
               v(:, i + 1) = v(:, i) * x - v(:, i - 1) * (ri - 1.0_dp)
            case default
               v(:, i + 1) = (v(:, i) * (2.0_dp * ri - 1.0_dp - x) - v(:, i - 1) * (ri - 1.0_dp)) / ri
            end select
         end do
      end function opoly_vander

      pure function opoly_der(fam, c_in, m, scl) result(c)
         ! m-th derivative of the series, each differentiation multiplied by
         ! scl (default 1).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: c(:), der(:)
         real(kind=dp) :: s
         integer :: cnt, n, i, j
         cnt = 1
         if (present(m)) cnt = m
         s = 1.0_dp
         if (present(scl)) s = scl
         if (cnt < 0) error stop "np.polynomial: The order of derivation must be non-negative"
         c = c_in
         if (cnt == 0) return
         n = size(c)
         if (cnt >= n) then
            ! numpy's c[:1] * 0 (empty for an empty c).
            c = c(1:min(1, n)) * 0.0_dp
            return
         end if
         do i = 1, cnt
            n = n - 1
            c = c * s
            allocate(der(n))
            select case (fam)
            case (1)
               do j = n, 1, -1
                  der(j) = real(j, kind=dp) * c(j + 1)
               end do
            case (2)
               do j = n, 3, -1
                  der(j) = real(2 * j, kind=dp) * c(j + 1)
                  c(j - 1) = c(j - 1) + (real(j, kind=dp) * c(j + 1)) / real(j - 2, kind=dp)
               end do
               if (n > 1) der(2) = 4.0_dp * c(3)
               der(1) = c(2)
            case (3)
               do j = n, 3, -1
                  der(j) = real(2 * j - 1, kind=dp) * c(j + 1)
                  c(j - 1) = c(j - 1) + c(j + 1)
               end do
               if (n > 1) der(2) = 3.0_dp * c(3)
               der(1) = c(2)
            case (4)
               do j = n, 1, -1
                  der(j) = real(2 * j, kind=dp) * c(j + 1)
               end do
            case (5)
               do j = n, 1, -1
                  der(j) = real(j, kind=dp) * c(j + 1)
               end do
            case default
               do j = n, 2, -1
                  der(j) = -c(j + 1)
                  c(j) = c(j) + c(j + 1)
               end do
               der(1) = -c(2)
            end select
            c = der
            deallocate(der)
         end do
      end function opoly_der

      pure function opoly_int(fam, c_in, m, k, lbnd, scl) result(c)
         ! m-th integral of the series: integration constants k (missing ones
         ! 0), the value of each integral at lbnd being k, each integration
         ! multiplied by scl.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: c(:), tmp(:), kk(:)
         real(kind=dp) :: s, lb, t
         integer :: cnt, n, i, j
         cnt = 1
         if (present(m)) cnt = m
         s = 1.0_dp
         if (present(scl)) s = scl
         lb = 0.0_dp
         if (present(lbnd)) lb = lbnd
         if (cnt < 0) error stop "np.polynomial: The order of integration must be non-negative"
         allocate(kk(max(cnt, 0)), source=0.0_dp)
         if (present(k)) then
            if (size(k) > cnt) error stop "np.polynomial: Too many integration constants"
            kk(1:size(k)) = k
         end if
         c = c_in
         do i = 1, cnt
            n = size(c)
            c = c * s
            if (n == 1 .and. c(1) == 0.0_dp) then
               c(1) = c(1) + kk(i)
               cycle
            end if
            allocate(tmp(n + 1), source=0.0_dp)
            select case (fam)
            case (1)
               tmp(2) = c(1)
               do j = 1, n - 1
                  tmp(j + 2) = c(j + 1) / real(j + 1, kind=dp)
               end do
            case (2)
               tmp(2) = c(1)
               if (n > 1) tmp(3) = c(2) / 4.0_dp
               do j = 2, n - 1
                  tmp(j + 2) = c(j + 1) / real(2 * (j + 1), kind=dp)
                  tmp(j) = tmp(j) - c(j + 1) / real(2 * (j - 1), kind=dp)
               end do
            case (3)
               tmp(2) = c(1)
               if (n > 1) tmp(3) = c(2) / 3.0_dp
               do j = 2, n - 1
                  t = c(j + 1) / real(2 * j + 1, kind=dp)
                  tmp(j + 2) = t
                  tmp(j) = tmp(j) - t
               end do
            case (4)
               tmp(2) = c(1) / 2.0_dp
               do j = 1, n - 1
                  tmp(j + 2) = c(j + 1) / real(2 * (j + 1), kind=dp)
               end do
            case (5)
               tmp(2) = c(1)
               do j = 1, n - 1
                  tmp(j + 2) = c(j + 1) / real(j + 1, kind=dp)
               end do
            case default
               tmp(1) = c(1)
               tmp(2) = -c(1)
               do j = 1, n - 1
                  tmp(j + 1) = tmp(j + 1) + c(j + 1)
                  tmp(j + 2) = -c(j + 1)
               end do
            end select
            tmp(1) = tmp(1) + (kk(i) - opoly_val0(fam, lb, tmp))
            c = tmp
            deallocate(tmp)
         end do
      end function opoly_int

      function opoly_fit(fam, x, y, deg, rcond, w) result(c)
         ! Least-squares fit of degree deg as numpy does it: the columns of
         ! the pseudo-Vandermonde matrix (rows weighted by w) are scaled to
         ! unit norm, solved with lstsq (rcond default size(x) * eps), and the
         ! scaling is undone.
         integer, intent(in) :: fam, deg
         real(kind=dp), intent(in) :: x(:), y(:)
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:), a(:,:), b(:,:), sol(:,:), res(:), sv(:), scl(:)
         real(kind=dp) :: rc
         integer :: rnk, j
         if (size(x) == 0) error stop "np.polynomial: expected non-empty vector for x"
         if (size(x) /= size(y)) error stop "np.polynomial: expected x and y to have same length"
         if (deg < 0) error stop "np.polynomial: expected deg >= 0"
         a = opoly_vander(fam, x, deg)
         allocate(b(size(y), 1))
         b(:, 1) = y
         if (present(w)) then
            if (size(w) /= size(x)) error stop "np.polynomial: expected x and w to have same length"
            do j = 1, size(a, 2)
               a(:, j) = a(:, j) * w
            end do
            b(:, 1) = b(:, 1) * w
         end if
         rc = real(size(x), kind=dp) * epsilon(1.0_dp)
         if (present(rcond)) rc = rcond
         allocate(scl(size(a, 2)))
         do j = 1, size(a, 2)
            scl(j) = sqrt(sum(a(:, j) ** 2))
            if (scl(j) == 0.0_dp) scl(j) = 1.0_dp
            a(:, j) = a(:, j) / scl(j)
         end do
         call linalg_lstsq_mat(a, b, sol, res, rnk, sv, rc)
         c = sol(:, 1) / scl
      end function opoly_fit

      ! ---- np.polynomial, continued: trimming, companion matrices, roots,
      ! Gauss quadrature, arithmetic in each basis, conversions -------------

      pure function opoly_trim(c) result(r)
         ! numpy's polyutils.trimseq: trailing zero coefficients removed,
         ! keeping at least one.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         integer :: i
         if (size(c) == 0) then
            allocate(r(0))
            return
         end if
         do i = size(c), 1, -1
            if (c(i) /= 0.0_dp) exit
         end do
         r = c(1:max(i, 1))
      end function opoly_trim

      pure function opoly_trimcoef(c, tol) result(r)
         ! numpy's polyutils.trimcoef (<f>trim): trailing coefficients with
         ! |c| <= tol removed, keeping at least one (then 0).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:), ct(:)
         real(kind=dp) :: tl
         integer :: i
         tl = 0.0_dp
         if (present(tol)) tl = tol
         if (tl < 0.0_dp) error stop "np.polynomial: tol must be non-negative"
         ct = opoly_trim(c)
         do i = size(ct), 1, -1
            if (abs(ct(i)) > tl) exit
         end do
         if (i < 1) then
            r = ct(1:1) * 0.0_dp
         else
            r = ct(1:i)
         end if
      end function opoly_trimcoef

      pure function opoly_companion(fam, c_in) result(mat)
         ! Scaled companion matrix of the series (numpy's <f>companion).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         real(kind=dp), allocatable :: mat(:,:), c(:), scl(:), top(:)
         integer :: n, i
         c = opoly_trim(c_in)
         if (size(c) < 2) error stop "np.polynomial: Series must have maximum degree of at least 1."
         n = size(c) - 1
         allocate(mat(n, n), source=0.0_dp)
         if (n == 1) then
            select case (fam)
            case (4)
               mat(1, 1) = -0.5_dp * c(1) / c(2)
            case (6)
               mat(1, 1) = 1.0_dp + c(1) / c(2)
            case default
               mat(1, 1) = -c(1) / c(2)
            end select
            return
         end if
         allocate(scl(n), top(n - 1))
         select case (fam)
         case (1)
            do i = 1, n - 1
               mat(i + 1, i) = 1.0_dp
            end do
            mat(:, n) = mat(:, n) - c(1:n) / c(n + 1)
         case (2)
            scl = sqrt(0.5_dp)
            scl(1) = 1.0_dp
            top = 0.5_dp
            top(1) = sqrt(0.5_dp)
            do i = 1, n - 1
               mat(i, i + 1) = top(i)
               mat(i + 1, i) = top(i)
            end do
            mat(:, n) = mat(:, n) - (c(1:n) / c(n + 1)) * (scl / scl(n)) * 0.5_dp
         case (3)
            scl = [(1.0_dp / sqrt(real(2 * i + 1, kind=dp)), i = 0, n - 1)]
            do i = 1, n - 1
               top(i) = real(i, kind=dp) * scl(i) * scl(i + 1)
               mat(i, i + 1) = top(i)
               mat(i + 1, i) = top(i)
            end do
            mat(:, n) = mat(:, n) - (c(1:n) / c(n + 1)) * (scl / scl(n)) * &
               (real(n, kind=dp) / real(2 * n - 1, kind=dp))
         case (4, 5)
            ! scl = cumprod([1, 1/sqrt(k(n-1)), ..., 1/sqrt(k*1)])[::-1], k = 2 or 1
            scl(1) = 1.0_dp
            do i = 2, n
               scl(i) = scl(i - 1) / sqrt(merge(2.0_dp, 1.0_dp, fam == 4) * real(n - i + 1, kind=dp))
            end do
            scl = scl(n:1:-1)
            do i = 1, n - 1
               top(i) = sqrt(merge(0.5_dp, 1.0_dp, fam == 4) * real(i, kind=dp))
               mat(i, i + 1) = top(i)
               mat(i + 1, i) = top(i)
            end do
            if (fam == 4) then
               mat(:, n) = mat(:, n) - scl * c(1:n) / (2.0_dp * c(n + 1))
            else
               mat(:, n) = mat(:, n) - scl * c(1:n) / c(n + 1)
            end if
         case default
            do i = 1, n - 1
               mat(i, i + 1) = -real(i, kind=dp)
               mat(i + 1, i) = -real(i, kind=dp)
            end do
            do i = 1, n
               mat(i, i) = 2.0_dp * real(i - 1, kind=dp) + 1.0_dp
            end do
            mat(:, n) = mat(:, n) + (c(1:n) / c(n + 1)) * real(n, kind=dp)
         end select
      end function opoly_companion

      function opoly_roots(fam, c_in) result(r)
         ! Roots of the series (numpy's <f>roots): eigenvalues of the
         ! companion matrix with rows and columns reversed, sorted by real
         ! part, then imaginary part. Always complex.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         complex(kind=dp), allocatable :: r(:)
         real(kind=dp), allocatable :: c(:), m(:,:)
         complex(kind=dp) :: tmp
         integer :: i, j, n
         c = opoly_trim(c_in)
         if (size(c) < 2) then
            allocate(r(0))
            return
         end if
         if (size(c) == 2) then
            select case (fam)
            case (4)
               r = [cmplx(-0.5_dp * c(1) / c(2), 0.0_dp, kind=dp)]
            case (6)
               r = [cmplx(1.0_dp + c(1) / c(2), 0.0_dp, kind=dp)]
            case default
               r = [cmplx(-c(1) / c(2), 0.0_dp, kind=dp)]
            end select
            return
         end if
         m = opoly_companion(fam, c)
         n = size(m, 1)
         m = m(n:1:-1, n:1:-1)
         r = linalg_eigvals_real(m)
         do i = 2, size(r)
            tmp = r(i)
            j = i - 1
            do while (j >= 1)
               if (.not. (real(r(j)) > real(tmp) .or. (real(r(j)) == real(tmp) .and. aimag(r(j)) > aimag(tmp)))) exit
               r(j + 1) = r(j)
               j = j - 1
            end do
            r(j + 1) = tmp
         end do
      end function opoly_roots

      function opoly_realroots(fam, c, tol, lo, hi) result(x)
         ! The real roots of the series, ascending (not a numpy function):
         ! the roots from opoly_roots whose imaginary part is at most
         ! tol * max(1, |root|) (default sqrt(epsilon)), polished by a few
         ! Newton steps on the series, optionally only those in [lo, hi].
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:), dc(:)
         complex(kind=dp), allocatable :: r(:)
         real(kind=dp) :: tl, xi, fx, dfx, step
         logical, allocatable :: keep(:)
         integer :: i, it
         tl = sqrt(epsilon(1.0_dp))
         if (present(tol)) tl = tol
         r = opoly_roots(fam, c)
         allocate(keep(size(r)))
         keep = abs(aimag(r)) <= tl * max(1.0_dp, abs(r))
         x = pack(real(r, kind=dp), keep)
         dc = opoly_der(fam, opoly_trim(c))
         do i = 1, size(x)
            xi = x(i)
            do it = 1, 3
               fx = opoly_val0(fam, xi, c)
               dfx = opoly_val0(fam, xi, dc)
               if (dfx == 0.0_dp) exit
               step = fx / dfx
               ! Keep a polishing step small (a multiple root has dfx ~ 0).
               if (abs(step) > tl * max(1.0_dp, abs(xi))) exit
               xi = xi - step
            end do
            x(i) = xi
         end do
         if (present(lo)) x = pack(x, x >= lo)
         if (present(hi)) x = pack(x, x <= hi)
      end function opoly_realroots

      pure function opoly_normed_herm(x, n, e) result(y)
         ! numpy's _normed_hermite_n (e = .false.) / _normed_hermite_e_n
         ! (e = .true.): the normalized Hermite function of degree n at x.
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: n
         logical, intent(in) :: e
         real(kind=dp) :: y(size(x)), pi, nd
         real(kind=dp) :: c0(size(x)), c1(size(x)), tmp(size(x))
         integer :: i
         pi = acos(-1.0_dp)
         if (n == 0) then
            y = 1.0_dp / sqrt(sqrt(merge(2.0_dp * pi, pi, e)))
            return
         end if
         c0 = 0.0_dp
         c1 = 1.0_dp / sqrt(sqrt(merge(2.0_dp * pi, pi, e)))
         nd = real(n, kind=dp)
         do i = 1, n - 1
            tmp = c0
            c0 = -c1 * sqrt((nd - 1.0_dp) / nd)
            if (e) then
               c1 = tmp + c1 * x * sqrt(1.0_dp / nd)
            else
               c1 = tmp + c1 * x * sqrt(2.0_dp / nd)
            end if
            nd = nd - 1.0_dp
         end do
         if (e) then
            y = c0 + c1 * x
         else
            y = c0 + c1 * x * sqrt(2.0_dp)
         end if
      end function opoly_normed_herm

      subroutine opoly_gauss(fam, deg, x, w)
         ! Gauss quadrature nodes and weights (numpy's <f>gauss) for the
         ! Chebyshev, Hermite, HermiteE and Laguerre weight functions
         ! (Legendre: leggauss).
         integer, intent(in) :: fam, deg
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         real(kind=dp), allocatable :: c(:), dy(:), df(:), fm(:)
         real(kind=dp) :: pi
         integer :: i
         pi = acos(-1.0_dp)
         if (deg <= 0) error stop "np.polynomial: deg must be a positive integer"
         if (fam == 2) then
            x = [(cos(pi * real(2 * i - 1, kind=dp) / (2.0_dp * real(deg, kind=dp))), i = 1, deg)]
            allocate(w(deg), source=pi / real(deg, kind=dp))
            return
         end if
         allocate(c(deg + 1), source=0.0_dp)
         c(deg + 1) = 1.0_dp
         x = linalg_eigvalsh(opoly_companion(fam, c))
         select case (fam)
         case (4, 5)
            dy = opoly_normed_herm(x, deg, fam == 5)
            df = opoly_normed_herm(x, deg - 1, fam == 5) * sqrt(merge(2.0_dp, 1.0_dp, fam == 4) * real(deg, kind=dp))
            x = x - dy / df
            fm = opoly_normed_herm(x, deg - 1, fam == 5)
            fm = fm / maxval(abs(fm))
            w = 1.0_dp / (fm * fm)
            w = (w + w(deg:1:-1)) / 2.0_dp
            x = (x - x(deg:1:-1)) / 2.0_dp
            w = w * (merge(sqrt(pi), sqrt(2.0_dp * pi), fam == 4) / sum(w))
         case (6)
            dy = lagval_1(x, c)
            df = lagval_1(x, opoly_der(6, c))
            x = x - dy / df
            fm = lagval_1(x, c(2:))
            fm = fm / maxval(abs(fm))
            df = df / maxval(abs(df))
            w = 1.0_dp / (fm * df)
            w = w / sum(w)
         case default
            error stop "np.polynomial: no Gauss rule for this family"
         end select
      end subroutine opoly_gauss

      function opoly_gauss_part(fam, deg, part) result(v)
         ! <f>gauss(deg)[part]: the nodes (0) or the weights (1).
         integer, intent(in) :: fam, deg, part
         real(kind=dp), allocatable :: v(:), x(:), w(:)
         call opoly_gauss(fam, deg, x, w)
         if (part == 0) then
            v = x
         else
            v = w
         end if
      end function opoly_gauss_part

      pure function opoly_mulx(fam, c_in) result(prd)
         ! The series times x (numpy's <f>mulx).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         real(kind=dp), allocatable :: prd(:), c(:)
         integer :: i, n
         c = opoly_trim(c_in)
         n = size(c)
         if (n == 1 .and. c(1) == 0.0_dp) then
            prd = c
            return
         end if
         allocate(prd(n + 1), source=0.0_dp)
         select case (fam)
         case (1)
            prd(2:) = c
         case (2)
            prd(2) = c(1)
            if (n > 1) then
               prd(3:) = c(2:) / 2.0_dp
               prd(1:n - 1) = prd(1:n - 1) + c(2:) / 2.0_dp
            end if
         case (3)
            prd(2) = c(1)
            do i = 1, n - 1
               prd(i + 2) = (c(i + 1) * real(i + 1, kind=dp)) / real(2 * i + 1, kind=dp)
               prd(i) = prd(i) + (c(i + 1) * real(i, kind=dp)) / real(2 * i + 1, kind=dp)
            end do
         case (4)
            prd(2) = c(1) / 2.0_dp
            do i = 1, n - 1
               prd(i + 2) = c(i + 1) / 2.0_dp
               prd(i) = prd(i) + c(i + 1) * real(i, kind=dp)
            end do
         case (5)
            prd(2) = c(1)
            do i = 1, n - 1
               prd(i + 2) = c(i + 1)
               prd(i) = prd(i) + c(i + 1) * real(i, kind=dp)
            end do
         case default
            prd(1) = c(1)
            prd(2) = -c(1)
            do i = 1, n - 1
               prd(i + 2) = -c(i + 1) * real(i + 1, kind=dp)
               prd(i + 1) = prd(i + 1) + c(i + 1) * real(2 * i + 1, kind=dp)
               prd(i) = prd(i) - c(i + 1) * real(i, kind=dp)
            end do
         end select
      end function opoly_mulx

      pure function opoly_add(c1_in, c2_in, sgn) result(r)
         ! numpy's polyutils._add (sgn 1) / _sub (sgn -1): coefficients added
         ! term by term (lowest degree first), trimmed.
         real(kind=dp), intent(in) :: c1_in(:), c2_in(:)
         integer, intent(in) :: sgn
         real(kind=dp), allocatable :: r(:), c1(:), c2(:)
         c1 = opoly_trim(c1_in)
         c2 = opoly_trim(c2_in)
         if (size(c1) > size(c2)) then
            r = c1
            r(1:size(c2)) = r(1:size(c2)) + real(sgn, kind=dp) * c2
         else
            r = real(sgn, kind=dp) * c2
            r(1:size(c1)) = r(1:size(c1)) + c1
         end if
         r = opoly_trim(r)
      end function opoly_add

      pure function opoly_convolve(a, b) result(c)
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         integer :: i
         allocate(c(size(a) + size(b) - 1), source=0.0_dp)
         do i = 1, size(a)
            c(i:i + size(b) - 1) = c(i:i + size(b) - 1) + a(i) * b
         end do
      end function opoly_convolve

      pure function opoly_c2z(c) result(zs)
         ! numpy's chebyshev._cseries_to_zseries.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: zs(:)
         integer :: n
         n = size(c)
         allocate(zs(2 * n - 1), source=0.0_dp)
         zs(n:) = c / 2.0_dp
         zs = zs + zs(2 * n - 1:1:-1)
      end function opoly_c2z

      pure function opoly_z2c(zs) result(c)
         ! numpy's chebyshev._zseries_to_cseries.
         real(kind=dp), intent(in) :: zs(:)
         real(kind=dp), allocatable :: c(:)
         integer :: n
         n = (size(zs) + 1) / 2
         c = zs(n:)
         c(2:n) = c(2:n) * 2.0_dp
      end function opoly_z2c

      recursive pure function opoly_mul(fam, c1_in, c2_in) result(r)
         ! Product of two series in the same basis (numpy's <f>mul).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c1_in(:), c2_in(:)
         real(kind=dp), allocatable :: r(:), c(:), xs(:), c0(:), c1(:), tmp(:), a(:), b(:)
         real(kind=dp) :: nd
         integer :: i, n
         a = opoly_trim(c1_in)
         b = opoly_trim(c2_in)
         if (fam == 1) then
            r = opoly_trim(opoly_convolve(a, b))
            return
         end if
         if (fam == 2) then
            r = opoly_trim(opoly_z2c(opoly_convolve(opoly_c2z(a), opoly_c2z(b))))
            return
         end if
         if (size(a) > size(b)) then
            c = b
            xs = a
         else
            c = a
            xs = b
         end if
         n = size(c)
         if (n == 1) then
            c0 = c(1) * xs
            c1 = [0.0_dp]
         else if (n == 2) then
            c0 = c(1) * xs
            c1 = c(2) * xs
         else
            nd = real(n, kind=dp)
            c0 = c(n - 1) * xs
            c1 = c(n) * xs
            do i = 3, n
               tmp = c0
               nd = nd - 1.0_dp
               select case (fam)
               case (3)
                  c0 = opoly_add(c(n - i + 1) * xs, (c1 * (nd - 1.0_dp)) / nd, -1)
                  c1 = opoly_add(tmp, (opoly_mulx(3, c1) * (2.0_dp * nd - 1.0_dp)) / nd, 1)
               case (4)
                  c0 = opoly_add(c(n - i + 1) * xs, c1 * (2.0_dp * (nd - 1.0_dp)), -1)
                  c1 = opoly_add(tmp, opoly_mulx(4, c1) * 2.0_dp, 1)
               case (5)
                  c0 = opoly_add(c(n - i + 1) * xs, c1 * (nd - 1.0_dp), -1)
                  c1 = opoly_add(tmp, opoly_mulx(5, c1), 1)
               case default
                  c0 = opoly_add(c(n - i + 1) * xs, (c1 * (nd - 1.0_dp)) / nd, -1)
                  c1 = opoly_add(tmp, opoly_add((2.0_dp * nd - 1.0_dp) * c1, opoly_mulx(6, c1), -1) / nd, 1)
               end select
            end do
         end if
         select case (fam)
         case (3, 5)
            r = opoly_add(c0, opoly_mulx(fam, c1), 1)
         case (4)
            r = opoly_add(c0, opoly_mulx(4, c1) * 2.0_dp, 1)
         case default
            r = opoly_add(c0, opoly_add(c1, opoly_mulx(6, c1), -1), 1)
         end select
      end function opoly_mul

      pure subroutine opoly_div(fam, c1_in, c2_in, quo, rem)
         ! Quotient and remainder of two series in the same basis (numpy's
         ! <f>div).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c1_in(:), c2_in(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         real(kind=dp), allocatable :: c1(:), c2(:), z1(:), z2(:), p(:), e(:), qz(:)
         real(kind=dp) :: scl, q, rr
         integer :: lc1, lc2, i, j, dlen
         c1 = opoly_trim(c1_in)
         c2 = opoly_trim(c2_in)
         if (c2(size(c2)) == 0.0_dp) error stop "np.polynomial: division by zero"
         lc1 = size(c1)
         lc2 = size(c2)
         if (lc1 < lc2) then
            quo = c1(1:1) * 0.0_dp
            rem = c1
            return
         end if
         if (lc2 == 1) then
            quo = c1 / c2(lc2)
            rem = c1(1:1) * 0.0_dp
            return
         end if
         select case (fam)
         case (1)
            dlen = lc1 - lc2
            scl = c2(lc2)
            c2 = c2(1:lc2 - 1) / scl
            i = dlen
            j = lc1 - 1
            do while (i >= 0)
               c1(i + 1:j) = c1(i + 1:j) - c2 * c1(j + 1)
               i = i - 1
               j = j - 1
            end do
            quo = c1(j + 2:) / scl
            rem = opoly_trim(c1(1:j + 1))
         case (2)
            z1 = opoly_c2z(c1)
            z2 = opoly_c2z(c2)
            ! numpy's chebyshev._zseries_div
            dlen = size(z1) - size(z2)
            scl = z2(1)
            z2 = z2 / scl
            allocate(qz(dlen + 1))
            i = 0
            j = dlen
            do while (i < j)
               rr = z1(i + 1)
               qz(i + 1) = z1(i + 1)
               qz(dlen - i + 1) = rr
               z1(i + 1:i + size(z2)) = z1(i + 1:i + size(z2)) - rr * z2
               z1(j + 1:j + size(z2)) = z1(j + 1:j + size(z2)) - rr * z2
               i = i + 1
               j = j - 1
            end do
            rr = z1(i + 1)
            qz(i + 1) = rr
            z1(i + 1:i + size(z2)) = z1(i + 1:i + size(z2)) - rr * z2
            qz = qz / scl
            quo = opoly_trim(opoly_z2c(qz))
            rem = opoly_trim(opoly_z2c(z1(i + 2:i + size(z2) - 1)))
         case default
            ! numpy's polyutils._div with the basis product.
            allocate(quo(lc1 - lc2 + 1))
            rem = c1
            do i = lc1 - lc2, 0, -1
               allocate(e(i + 1), source=0.0_dp)
               e(i + 1) = 1.0_dp
               p = opoly_mul(fam, e, c2)
               deallocate(e)
               q = rem(size(rem)) / p(size(p))
               rem = rem(1:size(rem) - 1) - q * p(1:size(p) - 1)
               quo(i + 1) = q
            end do
            rem = opoly_trim(rem)
         end select
      end subroutine opoly_div

      pure function opoly_div_part(fam, c1, c2, part) result(r)
         ! <f>div(c1, c2)[part]: the quotient (0) or the remainder (1).
         integer, intent(in) :: fam, part
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:), q(:), rm(:)
         call opoly_div(fam, c1, c2, q, rm)
         if (part == 0) then
            r = q
         else
            r = rm
         end if
      end function opoly_div_part

      pure function opoly_pow(fam, c_in, power, maxpower) result(prd)
         ! The series to a non-negative integer power (numpy's <f>pow;
         ! maxpower defaults to 16, none for the power series).
         integer, intent(in) :: fam, power
         real(kind=dp), intent(in) :: c_in(:)
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: prd(:), c(:), zs(:)
         integer :: i, mx
         mx = merge(huge(1), 16, fam == 1)
         if (present(maxpower)) mx = maxpower
         c = opoly_trim(c_in)
         if (power < 0) error stop "np.polynomial: Power must be a non-negative integer."
         if (power > mx) error stop "np.polynomial: Power is too large"
         if (power == 0) then
            prd = [1.0_dp]
            return
         end if
         if (power == 1) then
            prd = c
            return
         end if
         if (fam == 1) then
            prd = c
            do i = 2, power
               prd = opoly_convolve(prd, c)
            end do
         else if (fam == 2) then
            zs = opoly_c2z(c)
            prd = zs
            do i = 2, power
               prd = opoly_convolve(prd, zs)
            end do
            prd = opoly_z2c(prd)
         else
            prd = c
            do i = 2, power
               prd = opoly_mul(fam, prd, c)
            end do
         end if
      end function opoly_pow

      pure function opoly_line(fam, off, scl) result(c)
         ! The series of off + scl*x (numpy's <f>line).
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         if (scl == 0.0_dp) then
            c = [off]
         else if (fam == 4) then
            c = [off, scl / 2.0_dp]
         else if (fam == 6) then
            c = [off + scl, -scl]
         else
            c = [off, scl]
         end if
      end function opoly_line

      pure function opoly_fromroots(fam, roots_in) result(c)
         ! The series with these real roots (numpy's <f>fromroots): the
         ! factors x - r are multiplied pairwise, as numpy does.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: roots_in(:)
         real(kind=dp), allocatable :: c(:), roots(:), flat(:), tmpf(:)
         integer, allocatable :: start(:), len_(:), tstart(:), tlen(:)
         real(kind=dp) :: t
         integer :: n, m, rr, i, j, k, pos
         if (size(roots_in) == 0) then
            c = [1.0_dp]
            return
         end if
         roots = roots_in
         do i = 2, size(roots)
            t = roots(i)
            j = i - 1
            do while (j >= 1)
               if (.not. roots(j) > t) exit
               roots(j + 1) = roots(j)
               j = j - 1
            end do
            roots(j + 1) = t
         end do
         ! The factors, stored back to back in flat.
         n = size(roots)
         allocate(start(n), len_(n))
         flat = [real(kind=dp) ::]
         do i = 1, n
            tmpf = opoly_line(fam, -roots(i), 1.0_dp)
            start(i) = size(flat) + 1
            len_(i) = size(tmpf)
            flat = [flat, tmpf]
         end do
         do while (n > 1)
            m = n / 2
            rr = mod(n, 2)
            allocate(tstart(m), tlen(m))
            tmpf = [real(kind=dp) ::]
            do i = 1, m
               c = opoly_mul(fam, flat(start(i):start(i) + len_(i) - 1), &
                  flat(start(i + m):start(i + m) + len_(i + m) - 1))
               if (i == 1 .and. rr == 1) c = opoly_mul(fam, c, flat(start(n):start(n) + len_(n) - 1))
               tstart(i) = size(tmpf) + 1
               tlen(i) = size(c)
               tmpf = [tmpf, c]
            end do
            flat = tmpf
            start = tstart
            len_ = tlen
            deallocate(tstart, tlen)
            n = m
         end do
         c = flat(start(1):start(1) + len_(1) - 1)
         k = 0
         pos = 0
      end function opoly_fromroots

      pure function opoly_to_pow(fam, c_in) result(r)
         ! <f>2poly: the same polynomial as a power series.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: c_in(:)
         real(kind=dp), allocatable :: r(:), c(:), c0(:), c1(:), tmp(:)
         integer :: n, i
         c = opoly_trim(c_in)
         n = size(c)
         if (fam == 1) then
            r = c
            return
         end if
         if (n == 1) then
            r = c
            return
         end if
         if (n == 2) then
            select case (fam)
            case (4)
               r = [c(1), 2.0_dp * c(2)]
               return
            case (2, 3, 5)
               r = c
               return
            end select
         end if
         c0 = [c(n - 1)]
         c1 = [c(n)]
         do i = n - 1, 2, -1
            tmp = c0
            select case (fam)
            case (2)
               c0 = opoly_add([c(i - 1)], c1, -1)
               c1 = opoly_add(tmp, opoly_mulx(1, c1) * 2.0_dp, 1)
            case (3)
               c0 = opoly_add([c(i - 1)], (c1 * real(i - 1, kind=dp)) / real(i, kind=dp), -1)
               c1 = opoly_add(tmp, (opoly_mulx(1, c1) * real(2 * i - 1, kind=dp)) / real(i, kind=dp), 1)
            case (4)
               c0 = opoly_add([c(i - 1)], c1 * real(2 * (i - 1), kind=dp), -1)
               c1 = opoly_add(tmp, opoly_mulx(1, c1) * 2.0_dp, 1)
            case (5)
               c0 = opoly_add([c(i - 1)], c1 * real(i - 1, kind=dp), -1)
               c1 = opoly_add(tmp, opoly_mulx(1, c1), 1)
            case default
               c0 = opoly_add([c(i - 1)], (c1 * real(i - 1, kind=dp)) / real(i, kind=dp), -1)
               c1 = opoly_add(tmp, opoly_add(real(2 * i - 1, kind=dp) * c1, opoly_mulx(1, c1), -1) &
                  / real(i, kind=dp), 1)
            end select
         end do
         select case (fam)
         case (4)
            r = opoly_add(c0, opoly_mulx(1, c1) * 2.0_dp, 1)
         case (6)
            r = opoly_add(c0, opoly_add(c1, opoly_mulx(1, c1), -1), 1)
         case default
            r = opoly_add(c0, opoly_mulx(1, c1), 1)
         end select
      end function opoly_to_pow

      pure function opoly_from_pow(fam, pol_in) result(res)
         ! poly2<f>: a power series in the basis of family fam.
         integer, intent(in) :: fam
         real(kind=dp), intent(in) :: pol_in(:)
         real(kind=dp), allocatable :: res(:), pol(:)
         integer :: i
         pol = opoly_trim(pol_in)
         if (fam == 1) then
            res = pol
            return
         end if
         res = [0.0_dp]
         do i = size(pol), 1, -1
            res = opoly_add(opoly_mulx(fam, res), [pol(i)], 1)
         end do
      end function opoly_from_pow

      pure function chebpts1(npts) result(x)
         ! Chebyshev points of the first kind (numpy's chebpts1).
         integer, intent(in) :: npts
         real(kind=dp), allocatable :: x(:)
         integer :: i
         if (npts < 1) error stop "np.polynomial: npts must be >= 1"
         x = [(sin(0.5_dp * acos(-1.0_dp) / real(npts, kind=dp) * real(-npts + 1 + 2 * i, kind=dp)), &
            i = 0, npts - 1)]
      end function chebpts1

      pure function chebpts2(npts) result(x)
         ! Chebyshev points of the second kind (numpy's chebpts2).
         integer, intent(in) :: npts
         real(kind=dp), allocatable :: x(:)
         if (npts < 2) error stop "np.polynomial: npts must be >= 2"
         x = cos(linspace(-acos(-1.0_dp), 0.0_dp, npts))
      end function chebpts2

      pure function powcompanion(c) result(m)
         ! Scaled companion matrix of the power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(1, c)
      end function powcompanion

      function powroots(c) result(r)
         ! Roots of the power series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(1, c)
      end function powroots

      function powrealroots(c, tol, lo, hi) result(x)
         ! Real roots of the power series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(1, c, tol, lo, hi)
      end function powrealroots

      pure function powfromroots(roots) result(c)
         ! The power series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(1, roots)
      end function powfromroots

      pure function powmulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(1, c)
      end function powmulx

      pure function powadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function powadd

      pure function powsub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function powsub

      pure function powmul(c1, c2) result(r)
         ! Product of two power series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(1, c1, c2)
      end function powmul

      pure subroutine powdiv(c1, c2, quo, rem)
         ! Quotient and remainder of two power series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(1, c1, c2, quo, rem)
      end subroutine powdiv

      pure function powpow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(1, c, power, maxpower)
      end function powpow

      pure function powline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(1, off, scl)
      end function powline

      pure function powtrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function powtrim

      pure function chebcompanion(c) result(m)
         ! Scaled companion matrix of the Chebyshev series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(2, c)
      end function chebcompanion

      function chebroots(c) result(r)
         ! Roots of the Chebyshev series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(2, c)
      end function chebroots

      function chebrealroots(c, tol, lo, hi) result(x)
         ! Real roots of the Chebyshev series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(2, c, tol, lo, hi)
      end function chebrealroots

      pure function chebfromroots(roots) result(c)
         ! The Chebyshev series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(2, roots)
      end function chebfromroots

      pure function chebmulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(2, c)
      end function chebmulx

      pure function chebadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function chebadd

      pure function chebsub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function chebsub

      pure function chebmul(c1, c2) result(r)
         ! Product of two Chebyshev series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(2, c1, c2)
      end function chebmul

      pure subroutine chebdiv(c1, c2, quo, rem)
         ! Quotient and remainder of two Chebyshev series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(2, c1, c2, quo, rem)
      end subroutine chebdiv

      pure function chebpow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(2, c, power, maxpower)
      end function chebpow

      pure function chebline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(2, off, scl)
      end function chebline

      pure function chebtrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function chebtrim

      pure function cheb2poly(c) result(r)
         ! The Chebyshev series as a power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_to_pow(2, c)
      end function cheb2poly

      pure function poly2cheb(pol) result(r)
         ! A power series as a Chebyshev series.
         real(kind=dp), intent(in) :: pol(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_from_pow(2, pol)
      end function poly2cheb

      subroutine chebgauss(deg, x, w)
         ! Gauss quadrature nodes and weights for the Chebyshev series weight.
         integer, intent(in) :: deg
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         call opoly_gauss(2, deg, x, w)
      end subroutine chebgauss

      pure function legcompanion(c) result(m)
         ! Scaled companion matrix of the Legendre series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(3, c)
      end function legcompanion

      function legroots(c) result(r)
         ! Roots of the Legendre series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(3, c)
      end function legroots

      function legrealroots(c, tol, lo, hi) result(x)
         ! Real roots of the Legendre series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(3, c, tol, lo, hi)
      end function legrealroots

      pure function legfromroots(roots) result(c)
         ! The Legendre series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(3, roots)
      end function legfromroots

      pure function legmulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(3, c)
      end function legmulx

      pure function legadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function legadd

      pure function legsub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function legsub

      pure function legmul(c1, c2) result(r)
         ! Product of two Legendre series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(3, c1, c2)
      end function legmul

      pure subroutine legdiv(c1, c2, quo, rem)
         ! Quotient and remainder of two Legendre series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(3, c1, c2, quo, rem)
      end subroutine legdiv

      pure function legpow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(3, c, power, maxpower)
      end function legpow

      pure function legline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(3, off, scl)
      end function legline

      pure function legtrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function legtrim

      pure function leg2poly(c) result(r)
         ! The Legendre series as a power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_to_pow(3, c)
      end function leg2poly

      pure function poly2leg(pol) result(r)
         ! A power series as a Legendre series.
         real(kind=dp), intent(in) :: pol(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_from_pow(3, pol)
      end function poly2leg

      pure function hermcompanion(c) result(m)
         ! Scaled companion matrix of the Hermite series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(4, c)
      end function hermcompanion

      function hermroots(c) result(r)
         ! Roots of the Hermite series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(4, c)
      end function hermroots

      function hermrealroots(c, tol, lo, hi) result(x)
         ! Real roots of the Hermite series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(4, c, tol, lo, hi)
      end function hermrealroots

      pure function hermfromroots(roots) result(c)
         ! The Hermite series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(4, roots)
      end function hermfromroots

      pure function hermmulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(4, c)
      end function hermmulx

      pure function hermadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function hermadd

      pure function hermsub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function hermsub

      pure function hermmul(c1, c2) result(r)
         ! Product of two Hermite series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(4, c1, c2)
      end function hermmul

      pure subroutine hermdiv(c1, c2, quo, rem)
         ! Quotient and remainder of two Hermite series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(4, c1, c2, quo, rem)
      end subroutine hermdiv

      pure function hermpow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(4, c, power, maxpower)
      end function hermpow

      pure function hermline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(4, off, scl)
      end function hermline

      pure function hermtrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function hermtrim

      pure function herm2poly(c) result(r)
         ! The Hermite series as a power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_to_pow(4, c)
      end function herm2poly

      pure function poly2herm(pol) result(r)
         ! A power series as a Hermite series.
         real(kind=dp), intent(in) :: pol(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_from_pow(4, pol)
      end function poly2herm

      subroutine hermgauss(deg, x, w)
         ! Gauss quadrature nodes and weights for the Hermite series weight.
         integer, intent(in) :: deg
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         call opoly_gauss(4, deg, x, w)
      end subroutine hermgauss

      pure function hermecompanion(c) result(m)
         ! Scaled companion matrix of the HermiteE series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(5, c)
      end function hermecompanion

      function hermeroots(c) result(r)
         ! Roots of the HermiteE series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(5, c)
      end function hermeroots

      function hermerealroots(c, tol, lo, hi) result(x)
         ! Real roots of the HermiteE series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(5, c, tol, lo, hi)
      end function hermerealroots

      pure function hermefromroots(roots) result(c)
         ! The HermiteE series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(5, roots)
      end function hermefromroots

      pure function hermemulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(5, c)
      end function hermemulx

      pure function hermeadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function hermeadd

      pure function hermesub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function hermesub

      pure function hermemul(c1, c2) result(r)
         ! Product of two HermiteE series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(5, c1, c2)
      end function hermemul

      pure subroutine hermediv(c1, c2, quo, rem)
         ! Quotient and remainder of two HermiteE series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(5, c1, c2, quo, rem)
      end subroutine hermediv

      pure function hermepow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(5, c, power, maxpower)
      end function hermepow

      pure function hermeline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(5, off, scl)
      end function hermeline

      pure function hermetrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function hermetrim

      pure function herme2poly(c) result(r)
         ! The HermiteE series as a power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_to_pow(5, c)
      end function herme2poly

      pure function poly2herme(pol) result(r)
         ! A power series as a HermiteE series.
         real(kind=dp), intent(in) :: pol(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_from_pow(5, pol)
      end function poly2herme

      subroutine hermegauss(deg, x, w)
         ! Gauss quadrature nodes and weights for the HermiteE series weight.
         integer, intent(in) :: deg
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         call opoly_gauss(5, deg, x, w)
      end subroutine hermegauss

      pure function lagcompanion(c) result(m)
         ! Scaled companion matrix of the Laguerre series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: m(:,:)
         m = opoly_companion(6, c)
      end function lagcompanion

      function lagroots(c) result(r)
         ! Roots of the Laguerre series, complex, sorted as numpy sorts them.
         real(kind=dp), intent(in) :: c(:)
         complex(kind=dp), allocatable :: r(:)
         r = opoly_roots(6, c)
      end function lagroots

      function lagrealroots(c, tol, lo, hi) result(x)
         ! Real roots of the Laguerre series, ascending, polished (not in numpy).
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol, lo, hi
         real(kind=dp), allocatable :: x(:)
         x = opoly_realroots(6, c, tol, lo, hi)
      end function lagrealroots

      pure function lagfromroots(roots) result(c)
         ! The Laguerre series with these real roots.
         real(kind=dp), intent(in) :: roots(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fromroots(6, roots)
      end function lagfromroots

      pure function lagmulx(c) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mulx(6, c)
      end function lagmulx

      pure function lagadd(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, 1)
      end function lagadd

      pure function lagsub(c1, c2) result(r)
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_add(c1, c2, -1)
      end function lagsub

      pure function lagmul(c1, c2) result(r)
         ! Product of two Laguerre series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_mul(6, c1, c2)
      end function lagmul

      pure subroutine lagdiv(c1, c2, quo, rem)
         ! Quotient and remainder of two Laguerre series coefficient arrays.
         real(kind=dp), intent(in) :: c1(:), c2(:)
         real(kind=dp), allocatable, intent(out) :: quo(:), rem(:)
         call opoly_div(6, c1, c2, quo, rem)
      end subroutine lagdiv

      pure function lagpow(c, power, maxpower) result(r)
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in) :: power
         integer, intent(in), optional :: maxpower
         real(kind=dp), allocatable :: r(:)
         r = opoly_pow(6, c, power, maxpower)
      end function lagpow

      pure function lagline(off, scl) result(c)
         real(kind=dp), intent(in) :: off, scl
         real(kind=dp), allocatable :: c(:)
         c = opoly_line(6, off, scl)
      end function lagline

      pure function lagtrim(c, tol) result(r)
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), intent(in), optional :: tol
         real(kind=dp), allocatable :: r(:)
         r = opoly_trimcoef(c, tol)
      end function lagtrim

      pure function lag2poly(c) result(r)
         ! The Laguerre series as a power series.
         real(kind=dp), intent(in) :: c(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_to_pow(6, c)
      end function lag2poly

      pure function poly2lag(pol) result(r)
         ! A power series as a Laguerre series.
         real(kind=dp), intent(in) :: pol(:)
         real(kind=dp), allocatable :: r(:)
         r = opoly_from_pow(6, pol)
      end function poly2lag

      subroutine laggauss(deg, x, w)
         ! Gauss quadrature nodes and weights for the Laguerre series weight.
         integer, intent(in) :: deg
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         call opoly_gauss(6, deg, x, w)
      end subroutine laggauss

      pure function powval_0(x, c) result(y)
         ! Value of the power series (np.polynomial.polynomial, lowest degree first) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(1, x, c)
      end function powval_0

      pure function powval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(1, x(i), c)
         end do
      end function powval_1

      pure function powval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(1, x(i, j), c)
            end do
         end do
      end function powval_2

      pure function powvander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the power series (np.polynomial.polynomial, lowest degree first): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(1, x, deg)
      end function powvander

      pure function powder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the power series (np.polynomial.polynomial, lowest degree first), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(1, c, m, scl)
      end function powder

      pure function powint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the power series (np.polynomial.polynomial, lowest degree first); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(1, c, m, k, lbnd, scl)
      end function powint

      function powfit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the power series (np.polynomial.polynomial, lowest degree first) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(1, x, y, deg, rcond, w)
      end function powfit

      pure function chebval_0(x, c) result(y)
         ! Value of the Chebyshev series (np.polynomial.chebyshev) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(2, x, c)
      end function chebval_0

      pure function chebval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(2, x(i), c)
         end do
      end function chebval_1

      pure function chebval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(2, x(i, j), c)
            end do
         end do
      end function chebval_2

      pure function chebvander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the Chebyshev series (np.polynomial.chebyshev): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(2, x, deg)
      end function chebvander

      pure function chebder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the Chebyshev series (np.polynomial.chebyshev), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(2, c, m, scl)
      end function chebder

      pure function chebint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the Chebyshev series (np.polynomial.chebyshev); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(2, c, m, k, lbnd, scl)
      end function chebint

      function chebfit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the Chebyshev series (np.polynomial.chebyshev) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(2, x, y, deg, rcond, w)
      end function chebfit

      pure function legval_0(x, c) result(y)
         ! Value of the Legendre series (np.polynomial.legendre) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(3, x, c)
      end function legval_0

      pure function legval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(3, x(i), c)
         end do
      end function legval_1

      pure function legval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(3, x(i, j), c)
            end do
         end do
      end function legval_2

      pure function legvander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the Legendre series (np.polynomial.legendre): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(3, x, deg)
      end function legvander

      pure function legder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the Legendre series (np.polynomial.legendre), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(3, c, m, scl)
      end function legder

      pure function legint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the Legendre series (np.polynomial.legendre); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(3, c, m, k, lbnd, scl)
      end function legint

      function legfit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the Legendre series (np.polynomial.legendre) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(3, x, y, deg, rcond, w)
      end function legfit

      pure function hermval_0(x, c) result(y)
         ! Value of the physicists' Hermite series (np.polynomial.hermite) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(4, x, c)
      end function hermval_0

      pure function hermval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(4, x(i), c)
         end do
      end function hermval_1

      pure function hermval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(4, x(i, j), c)
            end do
         end do
      end function hermval_2

      pure function hermvander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the physicists' Hermite series (np.polynomial.hermite): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(4, x, deg)
      end function hermvander

      pure function hermder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the physicists' Hermite series (np.polynomial.hermite), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(4, c, m, scl)
      end function hermder

      pure function hermint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the physicists' Hermite series (np.polynomial.hermite); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(4, c, m, k, lbnd, scl)
      end function hermint

      function hermfit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the physicists' Hermite series (np.polynomial.hermite) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(4, x, y, deg, rcond, w)
      end function hermfit

      pure function hermeval_0(x, c) result(y)
         ! Value of the probabilists' Hermite series (np.polynomial.hermite_e) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(5, x, c)
      end function hermeval_0

      pure function hermeval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(5, x(i), c)
         end do
      end function hermeval_1

      pure function hermeval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(5, x(i, j), c)
            end do
         end do
      end function hermeval_2

      pure function hermevander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the probabilists' Hermite series (np.polynomial.hermite_e): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(5, x, deg)
      end function hermevander

      pure function hermeder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the probabilists' Hermite series (np.polynomial.hermite_e), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(5, c, m, scl)
      end function hermeder

      pure function hermeint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the probabilists' Hermite series (np.polynomial.hermite_e); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(5, c, m, k, lbnd, scl)
      end function hermeint

      function hermefit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the probabilists' Hermite series (np.polynomial.hermite_e) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(5, x, y, deg, rcond, w)
      end function hermefit

      pure function lagval_0(x, c) result(y)
         ! Value of the Laguerre series (np.polynomial.laguerre) with coefficients c at x.
         real(kind=dp), intent(in) :: x, c(:)
         real(kind=dp) :: y
         y = opoly_val0(6, x, c)
      end function lagval_0

      pure function lagval_1(x, c) result(y)
         real(kind=dp), intent(in) :: x(:), c(:)
         real(kind=dp) :: y(size(x))
         integer :: i
         do i = 1, size(x)
            y(i) = opoly_val0(6, x(i), c)
         end do
      end function lagval_1

      pure function lagval_2(x, c) result(y)
         real(kind=dp), intent(in) :: x(:,:), c(:)
         real(kind=dp) :: y(size(x, 1), size(x, 2))
         integer :: i, j
         do j = 1, size(x, 2)
            do i = 1, size(x, 1)
               y(i, j) = opoly_val0(6, x(i, j), c)
            end do
         end do
      end function lagval_2

      pure function lagvander(x, deg) result(v)
         ! Pseudo-Vandermonde matrix of the Laguerre series (np.polynomial.laguerre): v(i, j+1) is the basis
         ! function of degree j at x(i).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: v(:,:)
         v = opoly_vander(6, x, deg)
      end function lagvander

      pure function lagder(c, m, scl) result(d)
         ! m-th derivative (default 1) of the Laguerre series (np.polynomial.laguerre), scaled by scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: scl
         real(kind=dp), allocatable :: d(:)
         d = opoly_der(6, c, m, scl)
      end function lagder

      pure function lagint(c, m, k, lbnd, scl) result(r)
         ! m-th integral (default 1) of the Laguerre series (np.polynomial.laguerre); constants k, lower bound
         ! lbnd, scale scl per step.
         real(kind=dp), intent(in) :: c(:)
         integer, intent(in), optional :: m
         real(kind=dp), intent(in), optional :: k(:), lbnd, scl
         real(kind=dp), allocatable :: r(:)
         r = opoly_int(6, c, m, k, lbnd, scl)
      end function lagint

      function lagfit(x, y, deg, rcond, w) result(c)
         ! Least-squares fit of the Laguerre series (np.polynomial.laguerre) of degree deg to (x, y),
         ! optionally weighted by w; coefficients lowest degree first.
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), intent(in), optional :: rcond, w(:)
         real(kind=dp), allocatable :: c(:)
         c = opoly_fit(6, x, y, deg, rcond, w)
      end function lagfit

      pure function np_window(kind_name, m, beta) result(w)
         ! np.hanning / hamming / blackman / bartlett / kaiser(m[, beta]) with
         ! numpy's formulas (n = arange(1-m, m, 2) for the cosine windows);
         ! m == 1 gives [1.0] and m < 1 an empty array, as numpy does.
         character(len=*), intent(in) :: kind_name
         integer, intent(in) :: m
         real(kind=dp), intent(in), optional :: beta
         real(kind=dp), allocatable :: w(:)
         real(kind=dp) :: pi, alpha, b
         real(kind=dp), allocatable :: n(:)
         integer :: i
         pi = acos(-1.0_dp)
         if (m < 1) then
            allocate(w(0))
            return
         end if
         if (m == 1) then
            w = [1.0_dp]
            return
         end if
         n = [(real(1 - m + 2 * i, kind=dp), i = 0, m - 1)]
         select case (kind_name)
         case ("hanning")
            w = 0.5_dp + 0.5_dp * cos(pi * n / real(m - 1, kind=dp))
         case ("hamming")
            w = 0.54_dp + 0.46_dp * cos(pi * n / real(m - 1, kind=dp))
         case ("blackman")
            w = 0.42_dp + 0.5_dp * cos(pi * n / real(m - 1, kind=dp)) &
               + 0.08_dp * cos(2.0_dp * pi * n / real(m - 1, kind=dp))
         case ("bartlett")
            w = merge(1.0_dp + n / real(m - 1, kind=dp), 1.0_dp - n / real(m - 1, kind=dp), n <= 0.0_dp)
         case ("kaiser")
            b = 0.0_dp
            if (present(beta)) b = beta
            alpha = real(m - 1, kind=dp) / 2.0_dp
            n = [(real(i, kind=dp), i = 0, m - 1)]
            w = i0_scalar(b * sqrt(1.0_dp - ((n - alpha) / alpha) ** 2)) / i0_scalar(b)
         case default
            error stop "np_window: unknown window"
         end select
      end function np_window

      pure function np_poly_roots(r) result(c)
         ! np.poly(roots): the monic polynomial with these roots, highest
         ! degree first.
         real(kind=dp), intent(in) :: r(:)
         real(kind=dp), allocatable :: c(:), nxt(:)
         integer :: k
         c = [1.0_dp]
         do k = 1, size(r)
            nxt = [c, 0.0_dp]
            nxt(2:) = nxt(2:) - r(k) * c
            c = nxt
         end do
      end function np_poly_roots

      pure function np_polyadd_real(a, b, sgn) result(c)
         ! np.polyadd(a, b) (sgn = 1) / np.polysub(a, b) (sgn = -1): the
         ! shorter is padded with leading zeros.
         real(kind=dp), intent(in) :: a(:), b(:)
         integer, intent(in) :: sgn
         real(kind=dp), allocatable :: c(:)
         integer :: n
         n = max(size(a), size(b))
         allocate(c(n), source=0.0_dp)
         c(n - size(a) + 1:) = a
         c(n - size(b) + 1:) = c(n - size(b) + 1:) + real(sgn, kind=dp) * b
      end function np_polyadd_real

      pure function np_polyadd_int(a, b, sgn) result(c)
         integer, intent(in) :: a(:), b(:)
         integer, intent(in) :: sgn
         integer, allocatable :: c(:)
         integer :: n
         n = max(size(a), size(b))
         allocate(c(n), source=0)
         c(n - size(a) + 1:) = a
         c(n - size(b) + 1:) = c(n - size(b) + 1:) + sgn * b
      end function np_polyadd_int

      pure function np_polymul_real(a, b) result(c)
         ! np.polymul(a, b): the full convolution of the coefficients.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), allocatable :: c(:)
         integer :: i
         allocate(c(max(size(a) + size(b) - 1, 0)), source=0.0_dp)
         do i = 1, size(a)
            c(i:i + size(b) - 1) = c(i:i + size(b) - 1) + a(i) * b
         end do
      end function np_polymul_real

      pure function np_polymul_int(a, b) result(c)
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: c(:)
         integer :: i
         allocate(c(max(size(a) + size(b) - 1, 0)), source=0)
         do i = 1, size(a)
            c(i:i + size(b) - 1) = c(i:i + size(b) - 1) + a(i) * b
         end do
      end function np_polymul_int

      pure function np_polydiv(u, v, part) result(res)
         ! np.polydiv(u, v)[part]: the quotient (part 0) or the remainder
         ! (part 1), with numpy's algorithm (leading remainder terms close to
         ! zero, allclose with rtol 1e-14, are dropped).
         real(kind=dp), intent(in) :: u(:), v(:)
         integer, intent(in) :: part
         real(kind=dp), allocatable :: res(:), q(:), r(:)
         real(kind=dp) :: scale, d
         integer :: m, n, k
         m = size(u) - 1
         n = size(v) - 1
         if (n < 0) error stop "np.polydiv: the divisor is empty"
         if (v(1) == 0.0_dp) error stop "np.polydiv: the divisor's leading coefficient is zero"
         scale = 1.0_dp / v(1)
         allocate(q(max(m - n + 1, 1)), source=0.0_dp)
         r = u
         do k = 1, m - n + 1
            d = scale * r(k)
            q(k) = d
            r(k:k + n) = r(k:k + n) - d * v
         end do
         do while (size(r) > 1)
            if (abs(r(1)) > 1.0e-8_dp) exit   ! numpy: allclose(r[0], 0, rtol=1e-14)
            r = r(2:)
         end do
         if (part == 0) then
            res = q
         else
            res = r
         end if
      end function np_polydiv

      pure function np_polydiv_complex(u, v, part) result(res)
         ! np.polydiv(u, v)[part] of complex polynomials: the quotient (part 0) or the remainder
         ! (part 1), with numpy's algorithm (leading remainder terms close to
         ! zero, allclose with rtol 1e-14, are dropped).
         complex(kind=dp), intent(in) :: u(:), v(:)
         integer, intent(in) :: part
         complex(kind=dp), allocatable :: res(:), q(:), r(:)
         complex(kind=dp) :: scale, d
         integer :: m, n, k
         m = size(u) - 1
         n = size(v) - 1
         if (n < 0) error stop "np.polydiv: the divisor is empty"
         if (v(1) == (0.0_dp, 0.0_dp)) error stop "np.polydiv: the divisor's leading coefficient is zero"
         scale = (1.0_dp, 0.0_dp) / v(1)
         allocate(q(max(m - n + 1, 1)), source=(0.0_dp, 0.0_dp))
         r = u
         do k = 1, m - n + 1
            d = scale * r(k)
            q(k) = d
            r(k:k + n) = r(k:k + n) - d * v
         end do
         do while (size(r) > 1)
            if (abs(r(1)) > 1.0e-8_dp) exit   ! numpy: allclose(r[0], 0, rtol=1e-14)
            r = r(2:)
         end do
         if (part == 0) then
            res = q
         else
            res = r
         end if
      end function np_polydiv_complex

      pure function np_polyint(p, m, k) result(y)
         ! np.polyint(p, m, k): m antiderivatives, integration constants k
         ! (a scalar for all, or one per integration; default 0).
         real(kind=dp), intent(in) :: p(:)
         integer, intent(in) :: m
         real(kind=dp), intent(in), optional :: k(:)
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: kk
         integer :: j, i, n
         if (m < 0) error stop "np.polyint: Order of integral must be positive (see polyder)"
         y = p
         do j = 1, m
            kk = 0.0_dp
            if (present(k)) then
               if (size(k) == 1) then
                  kk = k(1)
               else if (size(k) >= m) then
                  kk = k(j)
               else
                  error stop "np.polyint: k must be a scalar or a rank-1 array of length 1 or >m."
               end if
            end if
            n = size(y)
            y = [(y(i) / real(n - i + 1, kind=dp), i = 1, n), kk]
         end do
      end function np_polyint

      pure function nan_quantile_vec(x, q) result(v)
         ! np.nanquantile(x, q) of a vector: the quantile of the non-NaN
         ! values (NaN if there are none, as numpy gives with a warning).
         real(kind=dp), intent(in) :: x(:), q
         real(kind=dp) :: v
         real(kind=dp), allocatable :: y(:)
         y = pack(x, .not. ieee_is_nan(x))
         if (size(y) == 0) then
            v = ieee_value(1.0_dp, ieee_quiet_nan)
         else
            v = quantile_linear(y, q)
         end if
      end function nan_quantile_vec

      pure function nan_quantile_axis_2d(x, q, dim) result(out)
         ! np.nanquantile(x, q, axis=dim-1) of a matrix.
         real(kind=dp), intent(in) :: x(:,:), q
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:)
         integer :: i
         if (dim == 1) then
            allocate(out(size(x, 2)))
            do i = 1, size(x, 2)
               out(i) = nan_quantile_vec(x(:, i), q)
            end do
         else
            allocate(out(size(x, 1)))
            do i = 1, size(x, 1)
               out(i) = nan_quantile_vec(x(i, :), q)
            end do
         end if
      end function nan_quantile_axis_2d

      pure function nan_quantile_qvec(x, q) result(v)
         ! np.nanquantile(x, q) of a vector at each probability of q.
         real(kind=dp), intent(in) :: x(:), q(:)
         real(kind=dp) :: v(size(q))
         integer :: k
         do k = 1, size(q)
            v(k) = nan_quantile_vec(x, q(k))
         end do
      end function nan_quantile_qvec

      pure function nan_quantile_axis_2d_q(x, q, dim) result(out)
         ! np.nanquantile(x, q, axis=dim-1) of a matrix for a vector q: numpy's
         ! shape (size(q), the other extent), row k for q(k).
         real(kind=dp), intent(in) :: x(:,:), q(:)
         integer, intent(in) :: dim
         real(kind=dp), allocatable :: out(:,:)
         integer :: k
         allocate(out(size(q), size(x, 3 - dim)))
         do k = 1, size(q)
            out(k, :) = nan_quantile_axis_2d(x, q(k), dim)
         end do
      end function nan_quantile_axis_2d_q

      pure function np_trapezoid_1d(y, dx, x) result(s)
         ! np.trapezoid(y, x=x | dx=dx) of a vector, summed as numpy does:
         ! sum(d * (y[1:] + y[:-1]) / 2).
         real(kind=dp), intent(in) :: y(:)
         real(kind=dp), intent(in), optional :: dx
         real(kind=dp), intent(in), optional :: x(:)
         real(kind=dp) :: s, d
         integer :: n
         n = size(y)
         s = 0.0_dp
         if (present(x)) then
            if (size(x) /= n) error stop "np.trapezoid: x and y must have the same length"
            if (n >= 2) s = sum((x(2:n) - x(1:n-1)) * (y(2:n) + y(1:n-1)) / 2.0_dp)
         else
            d = 1.0_dp
            if (present(dx)) d = dx
            if (n >= 2) s = sum(d * (y(2:n) + y(1:n-1)) / 2.0_dp)
         end if
      end function np_trapezoid_1d

      pure function np_gradient_1d(f, edge_order, dx, x) result(g)
         ! np.gradient(f, [dx | x], edge_order=...) of a vector, with numpy's
         ! formulas: second-order interior differences (for uneven
         ! coordinates x too), first- or second-order one-sided edges.
         ! Evenly spaced coordinates are treated as uniform, as numpy does.
         real(kind=dp), intent(in) :: f(:)
         integer, intent(in) :: edge_order
         real(kind=dp), intent(in), optional :: dx
         real(kind=dp), intent(in), optional :: x(:)
         real(kind=dp), allocatable :: g(:), h(:), dx1(:), dx2(:)
         real(kind=dp) :: s, a, b, c, d1, d2
         logical :: uniform
         integer :: n
         n = size(f)
         if (edge_order /= 1 .and. edge_order /= 2) error stop "np.gradient: edge_order must be 1 or 2"
         if (n < edge_order + 1) error stop "np.gradient: shape of array too small to calculate a numerical " // &
            "gradient, at least (edge_order + 1) elements are required"
         allocate(g(n))
         s = 1.0_dp
         if (present(dx)) s = dx
         uniform = .true.
         if (present(x)) then
            if (size(x) /= n) error stop "np.gradient: when 1d, distances must match the length of the " // &
               "corresponding dimension"
            h = x(2:n) - x(1:n-1)
            if (all(h == h(1))) then
               s = h(1)
            else
               uniform = .false.
            end if
         end if
         if (uniform) then
            g(2:n-1) = (f(3:n) - f(1:n-2)) / (2.0_dp * s)
         else
            dx1 = h(1:n-2)
            dx2 = h(2:n-1)
            g(2:n-1) = -(dx2) / (dx1 * (dx1 + dx2)) * f(1:n-2) + (dx2 - dx1) / (dx1 * dx2) * f(2:n-1) &
               + dx1 / (dx2 * (dx1 + dx2)) * f(3:n)
         end if
         if (edge_order == 1) then
            if (uniform) then
               g(1) = (f(2) - f(1)) / s
               g(n) = (f(n) - f(n-1)) / s
            else
               g(1) = (f(2) - f(1)) / h(1)
               g(n) = (f(n) - f(n-1)) / h(n-1)
            end if
         else
            if (uniform) then
               a = -1.5_dp / s
               b = 2.0_dp / s
               c = -0.5_dp / s
            else
               d1 = h(1)
               d2 = h(2)
               a = -(2.0_dp * d1 + d2) / (d1 * (d1 + d2))
               b = (d1 + d2) / (d1 * d2)
               c = -d1 / (d2 * (d1 + d2))
            end if
            g(1) = a * f(1) + b * f(2) + c * f(3)
            if (uniform) then
               a = 0.5_dp / s
               b = -2.0_dp / s
               c = 1.5_dp / s
            else
               d1 = h(n-2)
               d2 = h(n-1)
               a = d2 / (d1 * (d1 + d2))
               b = -(d2 + d1) / (d1 * d2)
               c = (2.0_dp * d2 + d1) / (d2 * (d1 + d2))
            end if
            g(n) = a * f(n-2) + b * f(n-1) + c * f(n)
         end if
      end function np_gradient_1d

      pure function np_gradient_2d(f, dim, edge_order, dx, x) result(g)
         ! np.gradient(f, ..., axis=dim-1) of a matrix: each column (dim 1)
         ! or row (dim 2) differentiated by np_gradient_1d.
         real(kind=dp), intent(in) :: f(:,:)
         integer, intent(in) :: dim, edge_order
         real(kind=dp), intent(in), optional :: dx
         real(kind=dp), intent(in), optional :: x(:)
         real(kind=dp), allocatable :: g(:,:)
         integer :: k
         allocate(g(size(f, 1), size(f, 2)))
         if (dim == 1) then
            do k = 1, size(f, 2)
               g(:, k) = np_gradient_1d(f(:, k), edge_order, dx, x)
            end do
         else
            do k = 1, size(f, 1)
               g(k, :) = np_gradient_1d(f(k, :), edge_order, dx, x)
            end do
         end if
      end function np_gradient_2d

      pure function unwrap_1d(x) result(y)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         integer :: n, i
         real(kind=dp) :: twopi, offset, delta, pi
         n = size(x)
         allocate(y(1:n))
         if (n <= 0) return
         pi = acos(-1.0_dp)
         twopi = 2.0_dp * pi
         offset = 0.0_dp
         y(1) = x(1)
         do i = 2, n
            delta = x(i) - x(i - 1)
            if (delta > pi) then
               offset = offset - twopi
            else if (delta < -pi) then
               offset = offset + twopi
            end if
            y(i) = x(i) + offset
         end do
      end function unwrap_1d

      pure function bitwise_count_int(x) result(y)
         integer, intent(in) :: x(:)
         integer, allocatable :: y(:)
         integer :: i
         allocate(y(size(x)))
         do i = 1, size(x)
            ! numpy counts the 1 bits of abs(x).
            y(i) = popcnt(abs(x(i)))
         end do
      end function bitwise_count_int

      pure elemental function i0_scalar(x) result(y)
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y
         real(kind=dp) :: ax, t
         ax = abs(x)
         if (ax < 3.75_dp) then
            t = (x / 3.75_dp) ** 2
            y = 1.0_dp + t * (3.5156229_dp + t * (3.0899424_dp + t * (1.2067492_dp + &
               t * (0.2659732_dp + t * (0.0360768_dp + t * 0.0045813_dp)))))
         else
            t = 3.75_dp / ax
            y = (exp(ax) / sqrt(ax)) * (0.39894228_dp + t * (0.01328592_dp + &
               t * (0.00225319_dp + t * (-0.00157565_dp + t * (0.00916281_dp + &
               t * (-0.02057706_dp + t * (0.02635537_dp + t * (-0.01647633_dp + &
               t * 0.00392377_dp))))))))
         end if
      end function i0_scalar

      pure elemental function sinc_scalar(x) result(y)
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y, pix
         if (abs(x) < 1.0e-12_dp) then
            y = 1.0_dp
         else
            pix = acos(-1.0_dp) * x
            y = sin(pix) / pix
         end if
      end function sinc_scalar

      pure elemental function signbit_real(x) result(y)
         real(kind=dp), intent(in) :: x
         logical :: y
         integer(kind=int64) :: bits
         bits = transfer(x, bits)
         y = bits < 0_int64
      end function signbit_real

      pure elemental function gcd_int_scalar(a, b) result(g)
         integer, intent(in) :: a, b
         integer :: g, x, y, t
         x = abs(a)
         y = abs(b)
         do while (y /= 0)
            t = modulo(x, y)
            x = y
            y = t
         end do
         g = x
      end function gcd_int_scalar

      pure elemental function lcm_int_scalar(a, b) result(l)
         integer, intent(in) :: a, b
         integer :: l, g
         if (a == 0 .or. b == 0) then
            l = 0
            return
         end if
         g = gcd_int_scalar(a, b)
         l = abs((a / g) * b)
      end function lcm_int_scalar

      pure function gcd_int(a) result(g)
         integer, intent(in) :: a(:)
         integer :: g, i
         if (size(a) == 0) then
            g = 0
            return
         end if
         g = abs(a(1))
         do i = 2, size(a)
            g = gcd_int_scalar(g, a(i))
         end do
      end function gcd_int

      pure function lcm_int(a) result(l)
         integer, intent(in) :: a(:)
         integer :: l, i
         if (size(a) == 0) then
            l = 1
            return
         end if
         l = abs(a(1))
         do i = 2, size(a)
            l = lcm_int_scalar(l, a(i))
         end do
      end function lcm_int

      pure function interp_periodic_1d(x, xp, fp, period) result(y)
         ! np.interp(x, xp, fp, period=p): x and xp are reduced modulo |p|,
         ! xp sorted (fp with it) and extended by one point at each end
         ! across the period boundary, as numpy does.
         real(kind=dp), intent(in) :: x(:), xp(:), fp(:), period
         real(kind=dp), allocatable :: y(:), xs(:), xpe(:), fpe(:)
         integer, allocatable :: idx(:)
         real(kind=dp) :: p
         integer :: n
         p = abs(period)
         if (p == 0.0_dp) error stop "np.interp: period must be a non-zero value"
         n = size(xp)
         if (n /= size(fp)) error stop "np.interp: fp and xp are not of the same length"
         if (n == 0) error stop "np.interp: array of sample points is empty"
         xs = modulo(xp, p)
         allocate(idx(n))
         call argsort_real(xs, idx)
         allocate(xpe(n + 2), fpe(n + 2))
         xpe(2:n+1) = xs(idx + 1)
         fpe(2:n+1) = fp(idx + 1)
         xpe(1) = xpe(n + 1) - p
         fpe(1) = fpe(n + 1)
         xpe(n + 2) = xpe(2) + p
         fpe(n + 2) = fpe(2)
         y = interp_1d(modulo(x, p), xpe, fpe)
      end function interp_periodic_1d

      pure function interp_periodic_0d(x, xp, fp, period) result(y)
         real(kind=dp), intent(in) :: x, xp(:), fp(:), period
         real(kind=dp) :: y, r(1)
         r = interp_periodic_1d([x], xp, fp, period)
         y = r(1)
      end function interp_periodic_0d

      pure function interp_0d(x, xp, fp, left, right) result(y)
         ! np.interp of a scalar x.
         real(kind=dp), intent(in) :: x, xp(:), fp(:)
         real(kind=dp), intent(in), optional :: left, right
         real(kind=dp) :: y, r(1)
         r = interp_1d([x], xp, fp, left, right)
         y = r(1)
      end function interp_0d

      pure function interp_1d(x, xp, fp, left, right) result(y)
         ! np.interp(x, xp, fp, left=, right=) as numpy computes it: j is the
         ! last index with xp(j) <= x (so with repeated xp values the last
         ! one is used), y = fp(j) where x == xp(j), else
         ! slope * (x - xp(j)) + fp(j); outside xp, left (default fp(1)) and
         ! right (default fp(n)); a NaN x gives NaN.
         real(kind=dp), intent(in) :: x(:), xp(:), fp(:)
         real(kind=dp), intent(in), optional :: left, right
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: lval, rval, slope, xv
         integer :: i, j, lo, hi, mid, m
         m = size(xp)
         if (m /= size(fp)) error stop "np.interp: fp and xp are not of the same length"
         if (m == 0) error stop "np.interp: array of sample points is empty"
         allocate(y(size(x)))
         lval = fp(1)
         if (present(left)) lval = left
         rval = fp(m)
         if (present(right)) rval = right
         do i = 1, size(x)
            xv = x(i)
            if (xv /= xv) then
               y(i) = xv
               cycle
            end if
            if (xv < xp(1)) then
               y(i) = lval
               cycle
            end if
            if (xv > xp(m)) then
               y(i) = rval
               cycle
            end if
            if (xv == xp(m)) then
               y(i) = fp(m)
               cycle
            end if
            ! xp(lo) <= xv < xp(hi)
            lo = 1
            hi = m
            do while (hi - lo > 1)
               mid = (lo + hi) / 2
               if (xp(mid) <= xv) then
                  lo = mid
               else
                  hi = mid
               end if
            end do
            j = lo
            if (xp(j) == xv) then
               y(i) = fp(j)
            else
               slope = (fp(j + 1) - fp(j)) / (xp(j + 1) - xp(j))
               y(i) = slope * (xv - xp(j)) + fp(j)
               if (y(i) /= y(i)) then
                  y(i) = slope * (xv - xp(j + 1)) + fp(j + 1)
                  if (y(i) /= y(i) .and. fp(j) == fp(j + 1)) y(i) = fp(j)
               end if
            end if
         end do
      end function interp_1d

      subroutine linalg_lstsq_mat(a, b, x, residuals, rnk, s, rcond)
         real(dp), intent(in) :: a(:,:), b(:,:)
         real(dp), allocatable, intent(out) :: x(:,:), residuals(:), s(:)
         integer, intent(out) :: rnk
         real(dp), optional, intent(in) :: rcond
         real(dp), allocatable :: u(:,:), vt(:,:), projected(:,:)
         real(dp) :: cutoff
         integer :: m, n, k, j
         m = size(a,1)
         n = size(a,2)
         k = min(m,n)
         if (size(b,1) /= m) error stop "linalg_lstsq: rhs row mismatch"
         allocate(x(n,size(b,2)), source=0.0_dp)
         rnk = 0
         if (k == 0) then
            allocate(s(0))
         else
            call linalg_svd_econ(a, u, s, vt)
            cutoff = epsilon(1.0_dp) * real(max(m,n), dp)
            if (present(rcond)) then
               cutoff = rcond
               if (cutoff < 0.0_dp) cutoff = epsilon(1.0_dp)
            end if
            cutoff = cutoff * s(1)
            rnk = count(s > cutoff)
            projected = matmul(transpose(u), b)
            do j = 1, k
               if (s(j) > cutoff) then
                  projected(j,:) = projected(j,:) / s(j)
               else
                  projected(j,:) = 0.0_dp
               end if
            end do
            x = matmul(transpose(vt), projected)
         end if
         ! NumPy reports residual sums only for full-column-rank,
         ! overdetermined systems, even if other systems have nonzero error.
         if (rnk == n .and. m > n) then
            residuals = sum((b - matmul(a,x))**2, dim=1)
         else
            allocate(residuals(0))
         end if
      end subroutine linalg_lstsq_mat

      subroutine linalg_lstsq_vec(a, b, x, residuals, rnk, s, rcond)
         real(dp), intent(in) :: a(:,:), b(:)
         real(dp), allocatable, intent(out) :: x(:), residuals(:), s(:)
         integer, intent(out) :: rnk
         real(dp), optional, intent(in) :: rcond
         real(dp), allocatable :: xm(:,:)
         call linalg_lstsq_mat(a, reshape(b, [size(b),1]), xm, residuals, rnk, s, rcond)
         x = xm(:,1)
      end subroutine linalg_lstsq_vec

      function linalg_lstsq_x_mat(a, b, rcond) result(x)
         real(dp), intent(in) :: a(:,:), b(:,:)
         real(dp), optional, intent(in) :: rcond
         real(dp), allocatable :: x(:,:), residuals(:), s(:)
         integer :: rnk
         call linalg_lstsq_mat(a, b, x, residuals, rnk, s, rcond)
      end function linalg_lstsq_x_mat

      function linalg_lstsq_x_vec(a, b, rcond) result(x)
         real(dp), intent(in) :: a(:,:), b(:)
         real(dp), optional, intent(in) :: rcond
         real(dp), allocatable :: x(:), residuals(:), s(:)
         integer :: rnk
         call linalg_lstsq_vec(a, b, x, residuals, rnk, s, rcond)
      end function linalg_lstsq_x_vec

      function linalg_solve_vec(a, b) result(x)
         real(kind=dp), intent(in) :: a(:,:), b(:)
         real(kind=dp), allocatable :: x(:)
         real(kind=dp), allocatable :: ac(:,:), bc(:,:)
         integer, allocatable :: ipiv(:)
         integer :: n, info
         interface
            subroutine dgesv(n, nrhs, a, lda, ipiv, b, ldb, info)
               integer, intent(in) :: n, nrhs, lda, ldb
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*), b(ldb,*)
            end subroutine dgesv
         end interface
         n = size(a, 1)
         if (size(a,2) /= n) stop "linalg_solve: matrix must be square"
         if (size(b) /= n) stop "linalg_solve: rhs size mismatch"
         allocate(ac(1:n,1:n), source=a)
         allocate(bc(1:n,1), source=0.0_dp)
         bc(:,1) = b
         allocate(ipiv(1:n))
         call dgesv(n, 1, ac, n, ipiv, bc, n, info)
         if (info /= 0) stop "linalg_solve: dgesv failed"
         allocate(x(1:n))
         x = bc(:,1)
      end function linalg_solve_vec

      subroutine linalg_solve_safe_vec(a, b, x, ok)
         real(kind=dp), intent(in) :: a(:,:), b(:)
         real(kind=dp), allocatable, intent(out) :: x(:)
         logical, intent(out) :: ok
         real(kind=dp), allocatable :: ac(:,:), bc(:,:)
         integer, allocatable :: ipiv(:)
         integer :: n, info
         interface
            subroutine dgesv(n, nrhs, a, lda, ipiv, b, ldb, info)
               integer, intent(in) :: n, nrhs, lda, ldb
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*), b(ldb,*)
            end subroutine dgesv
         end interface
         n = size(a, 1)
         allocate(ac(1:n,1:n), source=a)
         allocate(bc(1:n,1), source=0.0_dp)
         bc(:,1) = b
         allocate(ipiv(1:n))
         call dgesv(n, 1, ac, n, ipiv, bc, n, info)
         if (info /= 0) then
            allocate(x(1:size(b)))
            x = 0.0_dp
            ok = .false.
            return
         end if
         allocate(x(1:n))
         x = bc(:,1)
         ok = .true.
      end subroutine linalg_solve_safe_vec

      function linalg_solve_mat(a, b) result(x)
         real(kind=dp), intent(in) :: a(:,:), b(:,:)
         real(kind=dp), allocatable :: x(:,:)
         real(kind=dp), allocatable :: ac(:,:), bc(:,:)
         integer, allocatable :: ipiv(:)
         integer :: n, nrhs, info
         interface
            subroutine dgesv(n, nrhs, a, lda, ipiv, b, ldb, info)
               integer, intent(in) :: n, nrhs, lda, ldb
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*), b(ldb,*)
            end subroutine dgesv
         end interface
         n = size(a, 1)
         if (size(a,2) /= n) stop "linalg_solve: matrix must be square"
         if (size(b,1) /= n) stop "linalg_solve: rhs row mismatch"
         nrhs = size(b,2)
         allocate(ac(1:n,1:n), source=a)
         allocate(bc(1:n,1:nrhs), source=b)
         allocate(ipiv(1:n))
         call dgesv(n, nrhs, ac, n, ipiv, bc, n, info)
         if (info /= 0) stop "linalg_solve: dgesv failed"
         allocate(x(1:n,1:nrhs))
         x = bc
      end function linalg_solve_mat

      function linalg_solve_complex_vec(a, b) result(x)
         complex(dp), intent(in) :: a(:,:), b(:)
         complex(dp), allocatable :: x(:), xm(:,:)
         xm = linalg_solve_complex_mat(a, reshape(b, [size(b), 1]))
         x = xm(:,1)
      end function linalg_solve_complex_vec

      function linalg_solve_complex_mat(a, b) result(x)
         complex(dp), intent(in) :: a(:,:), b(:,:)
         complex(dp), allocatable :: x(:,:)
         real(dp), allocatable :: ac(:,:), bc(:,:)
         integer, allocatable :: ipiv(:)
         integer :: n, nrhs, info
         interface
            subroutine dgesv(n, nrhs, a, lda, ipiv, b, ldb, info)
               integer, intent(in) :: n, nrhs, lda, ldb
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*), b(ldb,*)
            end subroutine dgesv
         end interface
         n = size(a, 1)
         if (size(a,2) /= n) error stop "linalg_solve: matrix must be square"
         if (size(b,1) /= n) error stop "linalg_solve: rhs row mismatch"
         nrhs = size(b,2)
         allocate(x(n,nrhs))
         if (n == 0 .or. nrhs == 0) return
         ! A X = B is equivalent to [Re(A),-Im(A); Im(A),Re(A)]
         ! times [Re(X); Im(X)] = [Re(B); Im(B)]. Reuse the bundled
         ! pivoted LAPACK solver, without introducing a complex LAPACK dependency.
         allocate(ac(2*n,2*n), bc(2*n,nrhs), ipiv(2*n))
         ac(1:n,1:n) = real(a, dp)
         ac(1:n,n+1:2*n) = -aimag(a)
         ac(n+1:2*n,1:n) = aimag(a)
         ac(n+1:2*n,n+1:2*n) = real(a, dp)
         bc(1:n,:) = real(b, dp)
         bc(n+1:2*n,:) = aimag(b)
         call dgesv(2*n, nrhs, ac, 2*n, ipiv, bc, 2*n, info)
         if (info > 0) error stop "linalg_solve: singular matrix"
         if (info < 0) error stop "linalg_solve: dgesv invalid argument"
         x = cmplx(bc(1:n,:), bc(n+1:2*n,:), dp)
      end function linalg_solve_complex_mat

      function linalg_cholesky(a) result(l)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: l(:,:)
         integer :: n, i, j, info
         interface
            subroutine dpotrf(uplo, n, a, lda, info)
               character(len=1), intent(in) :: uplo
               integer, intent(in) :: n, lda
               double precision, intent(inout) :: a(lda,*)
               integer, intent(out) :: info
            end subroutine dpotrf
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_cholesky: matrix must be square"
         allocate(l(1:n,1:n), source=a)
         call dpotrf('L', n, l, n, info)
         if (info < 0) stop "linalg_cholesky: dpotrf argument error"
         if (info > 0) stop "linalg_cholesky: matrix is not positive definite"
         do i = 1, n
            do j = i + 1, n
               l(i,j) = 0.0_dp
            end do
         end do
      end function linalg_cholesky

      function linalg_det(a) result(detv)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp) :: detv
         real(kind=dp), allocatable :: ac(:,:)
         integer, allocatable :: ipiv(:)
         integer :: n, i, info, sgn
         interface
            subroutine dgetrf(m, n, a, lda, ipiv, info)
               integer, intent(in) :: m, n, lda
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*)
            end subroutine dgetrf
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_det: matrix must be square"
         allocate(ac(1:n,1:n), source=a)
         allocate(ipiv(1:n))
         call dgetrf(n, n, ac, n, ipiv, info)
         if (info < 0) stop "linalg_det: dgetrf argument error"
         if (info > 0) then
            detv = 0.0_dp
            return
         end if
         sgn = 1
         do i = 1, n
            if (ipiv(i) /= i) sgn = -sgn
         end do
         detv = real(sgn, kind=dp)
         do i = 1, n
            detv = detv * ac(i,i)
         end do
      end function linalg_det

      function linalg_inv(a) result(ai)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: ai(:,:)
         real(kind=dp), allocatable :: ac(:,:), work(:)
         integer, allocatable :: ipiv(:)
         integer :: n, info, lwork
         interface
            subroutine dgetrf(m, n, a, lda, ipiv, info)
               integer, intent(in) :: m, n, lda
               integer, intent(out) :: ipiv(*), info
               double precision, intent(inout) :: a(lda,*)
            end subroutine dgetrf
            subroutine dgetri(n, a, lda, ipiv, work, lwork, info)
               integer, intent(in) :: n, lda, lwork
               integer, intent(in) :: ipiv(*)
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*), work(*)
            end subroutine dgetri
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_inv: matrix must be square"
         allocate(ac(1:n,1:n), source=a)
         allocate(ipiv(1:n))
         call dgetrf(n, n, ac, n, ipiv, info)
         if (info /= 0) stop "linalg_inv: dgetrf failed"
         allocate(work(1))
         lwork = -1
         call dgetri(n, ac, n, ipiv, work, lwork, info)
         if (info /= 0) stop "linalg_inv: dgetri workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgetri(n, ac, n, ipiv, work, lwork, info)
         if (info /= 0) stop "linalg_inv: dgetri failed"
         allocate(ai(1:n,1:n))
         ai = ac
      end function linalg_inv

      function linalg_cond(a) result(cnd)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp) :: cnd
         real(kind=dp), allocatable :: u(:,:), s(:), vt(:,:)
         real(kind=dp) :: smax, smin

         call linalg_svd(a, u, s, vt)
         if (size(s) <= 0) then
            cnd = huge(1.0_dp)
            return
         end if
         smax = maxval(abs(s))
         smin = minval(abs(s))
         if (smin <= tiny(1.0_dp)) then
            cnd = huge(1.0_dp)
         else
            cnd = smax / smin
         end if
      end function linalg_cond

      integer function linalg_matrix_rank(a) result(rnk)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: u(:,:), s(:), vt(:,:)
         real(kind=dp) :: smax, tol
         integer :: m, n

         m = size(a, 1)
         n = size(a, 2)
         call linalg_svd(a, u, s, vt)
         if (size(s) <= 0) then
            rnk = 0
            return
         end if
         smax = maxval(abs(s))
         tol = smax * real(max(m, n), kind=dp) * epsilon(1.0_dp)
         rnk = count(abs(s) > tol)
      end function linalg_matrix_rank

      function linalg_eigvals_real(a) result(w)
         real(kind=dp), intent(in) :: a(:,:)
         complex(kind=dp), allocatable :: w(:)
         real(kind=dp), allocatable :: ac(:,:), wr(:), wi(:), vr_dummy(:,:), vl_dummy(:,:), work(:)
         integer :: n, info, lwork
         interface
            subroutine dgeev(jobvl, jobvr, n, a, lda, wr, wi, vl, ldvl, vr, ldvr, work, lwork, info)
               character(len=1), intent(in) :: jobvl, jobvr
               integer, intent(in) :: n, lda, ldvl, ldvr, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*)
               double precision, intent(out) :: wr(*), wi(*), vl(ldvl,*), vr(ldvr,*), work(*)
            end subroutine dgeev
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_eigvals: matrix must be square"
         allocate(ac(1:n,1:n), source=a)
         allocate(wr(1:n), wi(1:n))
         allocate(vr_dummy(1,1), vl_dummy(1,1))
         allocate(work(1))
         lwork = -1
         call dgeev('N', 'N', n, ac, n, wr, wi, vl_dummy, 1, vr_dummy, 1, work, lwork, info)
         if (info /= 0) stop "linalg_eigvals: dgeev workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgeev('N', 'N', n, ac, n, wr, wi, vl_dummy, 1, vr_dummy, 1, work, lwork, info)
         if (info /= 0) stop "linalg_eigvals: dgeev failed"
         allocate(w(1:n))
         w = cmplx(wr, wi, kind=dp)
      end function linalg_eigvals_real

      pure function linalg_eigvals_complex(a) result(w)
         use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
         complex(dp), intent(in) :: a(:,:)
         complex(dp), allocatable :: w(:)
         real(dp), allocatable :: ar(:,:), ai(:,:), wr(:), wi(:), zr(:,:), zi(:,:)
         real(dp) :: matrix_scale
         integer :: n, ierr

         n = size(a, 1)
         if (size(a, 2) /= n) error stop "linalg_eigvals: matrix must be square"
         allocate(w(n))
         if (n == 0) return
         if (.not. all(ieee_is_finite(real(a, dp))) .or. &
             .not. all(ieee_is_finite(aimag(a)))) &
            error stop "linalg_eigvals: matrix must contain only finite values"
         ! DCEIGV destroys its input. Scale the copies to protect the QR
         ! algorithm's products from overflow/underflow for uniformly scaled A.
         matrix_scale = max(maxval(abs(real(a, dp))), maxval(abs(aimag(a))))
         if (matrix_scale == 0.0_dp) then
            w = cmplx(0.0_dp, 0.0_dp, dp)
            return
         end if
         ar = real(a, dp) / matrix_scale
         ai = aimag(a) / matrix_scale
         allocate(wr(n), wi(n), zr(n,n), zi(n,n))
         call dceigv(.true., ar, ai, n, wr, wi, zr, zi, ierr)
         if (ierr /= 0) error stop "linalg_eigvals: dceigv failed to converge"
         w = cmplx(wr * matrix_scale, wi * matrix_scale, dp)
      end function linalg_eigvals_complex

      subroutine linalg_eig(a, w, v)
         real(kind=dp), intent(in) :: a(:,:)
         complex(kind=dp), allocatable, intent(out) :: w(:), v(:,:)
         real(kind=dp), allocatable :: ac(:,:), wr(:), wi(:), vr(:,:), vl_dummy(:,:), work(:)
         integer :: n, info, lwork, j
         interface
            subroutine dgeev(jobvl, jobvr, n, a, lda, wr, wi, vl, ldvl, vr, ldvr, work, lwork, info)
               character(len=1), intent(in) :: jobvl, jobvr
               integer, intent(in) :: n, lda, ldvl, ldvr, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*)
               double precision, intent(out) :: wr(*), wi(*), vl(ldvl,*), vr(ldvr,*), work(*)
            end subroutine dgeev
         end interface
         n = size(a,1)
         if (size(a,2) /= n) error stop "linalg_eig: matrix must be square"
         allocate(w(n), v(n,n))
         if (n == 0) return
         allocate(ac(1:n,1:n), source=a)
         allocate(wr(1:n), wi(1:n))
         allocate(vr(1:n,1:n))
         allocate(vl_dummy(1,1))
         allocate(work(1))
         lwork = -1
         call dgeev('N', 'V', n, ac, n, wr, wi, vl_dummy, 1, vr, n, work, lwork, info)
         if (info /= 0) error stop "linalg_eig: dgeev workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgeev('N', 'V', n, ac, n, wr, wi, vl_dummy, 1, vr, n, work, lwork, info)
         if (info /= 0) error stop "linalg_eig: dgeev failed"
         w = cmplx(wr, wi, kind=dp)
         ! DGEEV stores a conjugate pair's eigenvectors in two real columns:
         ! VR(:,j) + i*VR(:,j+1), followed by its complex conjugate.
         j = 1
         do while (j <= n)
            if (wi(j) == 0.0_dp) then
               v(:,j) = cmplx(vr(:,j), 0.0_dp, kind=dp)
               j = j + 1
            else
               v(:,j) = cmplx(vr(:,j), vr(:,j+1), kind=dp)
               v(:,j+1) = conjg(v(:,j))
               j = j + 2
            end if
         end do
      end subroutine linalg_eig

      subroutine linalg_eigh(a, w, v)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable, intent(out) :: w(:), v(:,:)
         real(kind=dp), allocatable :: ac(:,:), work(:)
         integer :: n, info, lwork
         interface
            subroutine dsyev(jobz, uplo, n, a, lda, w, work, lwork, info)
               character(len=1), intent(in) :: jobz, uplo
               integer, intent(in) :: n, lda, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*), work(*)
               double precision, intent(out) :: w(*)
            end subroutine dsyev
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_eigh: matrix must be square"
         ! As numpy (UPLO='L'), only the lower triangle of a is read.
         allocate(ac(1:n,1:n), source=a)
         allocate(w(1:n))
         allocate(work(1))
         lwork = -1
         call dsyev('V', 'L', n, ac, n, w, work, lwork, info)
         if (info /= 0) stop "linalg_eigh: dsyev workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dsyev('V', 'L', n, ac, n, w, work, lwork, info)
         if (info /= 0) stop "linalg_eigh: dsyev failed"
         allocate(v(1:n,1:n), source=ac)
      end subroutine linalg_eigh

      function linalg_eigvalsh(a) result(w)
         ! Eigenvalues only of a real symmetric matrix, matching
         ! numpy.linalg.eigvalsh -- same LAPACK DSYEV as linalg_eigh but
         ! with jobz='N' (skip computing eigenvectors).
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: w(:)
         real(kind=dp), allocatable :: ac(:,:), work(:)
         integer :: n, info, lwork
         interface
            subroutine dsyev(jobz, uplo, n, a, lda, w, work, lwork, info)
               character(len=1), intent(in) :: jobz, uplo
               integer, intent(in) :: n, lda, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*), work(*)
               double precision, intent(out) :: w(*)
            end subroutine dsyev
         end interface
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_eigvalsh: matrix must be square"
         allocate(ac(1:n,1:n), source=a)
         allocate(w(1:n))
         allocate(work(1))
         lwork = -1
         call dsyev('N', 'L', n, ac, n, w, work, lwork, info)
         if (info /= 0) stop "linalg_eigvalsh: dsyev workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dsyev('N', 'L', n, ac, n, w, work, lwork, info)
         if (info /= 0) stop "linalg_eigvalsh: dsyev failed"
      end function linalg_eigvalsh

      function linalg_pinv(a) result(ap)
         ! Moore-Penrose pseudo-inverse via economy SVD (A = U S V^T):
         ! pinv(A) = V * diag(1/s_i, s_i > tol else 0) * U^T, matching
         ! numpy.linalg.pinv's default rcond-based singular-value cutoff
         ! (same tol formula numpy itself uses: max(m,n)*eps*largest
         ! singular value).
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable :: ap(:,:)
         real(kind=dp), allocatable :: u(:,:), s(:), vt(:,:), sinv_ut(:,:)
         real(kind=dp) :: tol, smax
         integer :: m, n, k, i
         call linalg_svd_econ(a, u, s, vt)
         m = size(a,1)
         n = size(a,2)
         k = size(s)
         smax = 0.0_dp
         do i = 1, k
            if (s(i) > smax) smax = s(i)
         end do
         tol = real(max(m,n), kind=dp) * epsilon(1.0_dp) * smax
         allocate(sinv_ut(1:k, 1:m))
         do i = 1, k
            if (s(i) > tol) then
               sinv_ut(i, :) = u(:, i) / s(i)
            else
               sinv_ut(i, :) = 0.0_dp
            end if
         end do
         ap = matmul(transpose(vt), sinv_ut)
      end function linalg_pinv

      function linalg_matrix_power(a, p) result(ap)
         ! Integer matrix power, matching numpy.linalg.matrix_power: p=0
         ! gives the identity, p>0 repeated matmul, p<0 repeated matmul
         ! of linalg_inv(a).
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: p
         real(kind=dp), allocatable :: ap(:,:)
         real(kind=dp), allocatable :: base(:,:)
         integer :: n, i, pp
         n = size(a,1)
         if (size(a,2) /= n) stop "linalg_matrix_power: matrix must be square"
         allocate(ap(1:n,1:n), source=0.0_dp)
         do i = 1, n
            ap(i, i) = 1.0_dp
         end do
         if (p == 0) return
         pp = abs(p)
         if (p > 0) then
            base = a
         else
            base = linalg_inv(a)
         end if
         do i = 1, pp
            ap = matmul(ap, base)
         end do
      end function linalg_matrix_power

      subroutine linalg_qr_reduced(a, q, r)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable, intent(out) :: q(:,:), r(:,:)
         real(kind=dp), allocatable :: ac(:,:), tau(:), work(:)
         integer :: m, n, k, info, lwork, i_r, j_r
         interface
            subroutine dgeqrf(m, n, a, lda, tau, work, lwork, info)
               integer, intent(in) :: m, n, lda, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*), tau(*), work(*)
            end subroutine dgeqrf
            subroutine dorgqr(m, n, k, a, lda, tau, work, lwork, info)
               integer, intent(in) :: m, n, k, lda, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*), tau(*), work(*)
            end subroutine dorgqr
         end interface
         m = size(a,1)
         n = size(a,2)
         k = min(m, n)
         allocate(ac(1:m,1:n), source=a)
         allocate(tau(1:k))
         allocate(work(1))
         lwork = -1
         call dgeqrf(m, n, ac, m, tau, work, lwork, info)
         if (info /= 0) stop "linalg_qr_reduced: dgeqrf workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgeqrf(m, n, ac, m, tau, work, lwork, info)
         if (info /= 0) stop "linalg_qr_reduced: dgeqrf failed"
         allocate(r(1:k,1:n), source=0.0_dp)
         do i_r = 1, k
            do j_r = i_r, n
               r(i_r,j_r) = ac(i_r,j_r)
            end do
         end do
         if (k < n) ac(:,k+1:n) = 0.0_dp
         deallocate(work)
         allocate(work(1))
         lwork = -1
         call dorgqr(m, k, k, ac, m, tau, work, lwork, info)
         if (info /= 0) stop "linalg_qr_reduced: dorgqr workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dorgqr(m, k, k, ac, m, tau, work, lwork, info)
         if (info /= 0) stop "linalg_qr_reduced: dorgqr failed"
         allocate(q(1:m,1:k), source=ac(:,1:k))
      end subroutine linalg_qr_reduced

      function matrix_norm2_real(a) result(value)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp) :: value
         real(kind=dp), allocatable :: u(:,:), s(:), vt(:,:)
         if (min(size(a,1), size(a,2)) == 0) error stop "matrix_norm2: empty matrix"
         call linalg_svd_econ(a, u, s, vt)
         value = maxval(s)
      end function matrix_norm2_real

      function matrix_norm2_complex(a) result(value)
         complex(kind=dp), intent(in) :: a(:,:)
         real(kind=dp) :: value
         real(kind=dp), allocatable :: block_a(:,:)
         integer :: m, n
         ! Real representation has the same singular values, each twice.
         ! Reuse DGESVD without forming A**H*A (which squares conditioning).
         m = size(a,1)
         n = size(a,2)
         allocate(block_a(2*m,2*n))
         block_a(:m,:n) = real(a,kind=dp)
         block_a(:m,n+1:) = -aimag(a)
         block_a(m+1:,:n) = aimag(a)
         block_a(m+1:,n+1:) = real(a,kind=dp)
         value = matrix_norm2_real(block_a)
      end function matrix_norm2_complex

      subroutine linalg_svd(a, u, s, vt)
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable, intent(out) :: u(:,:), s(:), vt(:,:)
         real(kind=dp), allocatable :: ac(:,:), work(:)
         integer :: m, n, k, info, lwork
         interface
            subroutine dgesvd(jobu, jobvt, m, n, a, lda, s, u, ldu, vt, ldvt, work, lwork, info)
               character(len=1), intent(in) :: jobu, jobvt
               integer, intent(in) :: m, n, lda, ldu, ldvt, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*)
               double precision, intent(out) :: s(*), u(ldu,*), vt(ldvt,*), work(*)
            end subroutine dgesvd
         end interface
         m = size(a,1)
         n = size(a,2)
         k = min(m,n)
         allocate(ac(1:m,1:n), source=a)
         allocate(u(1:m,1:m), source=0.0_dp)
         allocate(s(1:k), source=0.0_dp)
         allocate(vt(1:n,1:n), source=0.0_dp)
         allocate(work(1))
         lwork = -1
         call dgesvd('A', 'A', m, n, ac, m, s, u, m, vt, n, work, lwork, info)
         if (info /= 0) stop "linalg_svd: dgesvd workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgesvd('A', 'A', m, n, ac, m, s, u, m, vt, n, work, lwork, info)
         if (info /= 0) stop "linalg_svd: dgesvd failed"
      end subroutine linalg_svd

      subroutine linalg_svd_econ(a, u, s, vt)
         ! Economy/reduced SVD, matching numpy's
         ! np.linalg.svd(a, full_matrices=False): u is (m, k), vt is
         ! (k, n), k = min(m, n) -- vs linalg_svd's full (m, m)/(n, n).
         ! Uses LAPACK DGESVD with jobu='S', jobvt='S' instead of 'A','A'.
         real(kind=dp), intent(in) :: a(:,:)
         real(kind=dp), allocatable, intent(out) :: u(:,:), s(:), vt(:,:)
         real(kind=dp), allocatable :: ac(:,:), work(:)
         integer :: m, n, k, info, lwork
         interface
            subroutine dgesvd(jobu, jobvt, m, n, a, lda, s, u, ldu, vt, ldvt, work, lwork, info)
               character(len=1), intent(in) :: jobu, jobvt
               integer, intent(in) :: m, n, lda, ldu, ldvt, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*)
               double precision, intent(out) :: s(*), u(ldu,*), vt(ldvt,*), work(*)
            end subroutine dgesvd
         end interface
         m = size(a,1)
         n = size(a,2)
         k = min(m,n)
         allocate(ac(1:m,1:n), source=a)
         allocate(u(1:m,1:k), source=0.0_dp)
         allocate(s(1:k), source=0.0_dp)
         allocate(vt(1:k,1:n), source=0.0_dp)
         allocate(work(1))
         lwork = -1
         call dgesvd('S', 'S', m, n, ac, m, s, u, m, vt, k, work, lwork, info)
         if (info /= 0) stop "linalg_svd_econ: dgesvd workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(1:lwork))
         call dgesvd('S', 'S', m, n, ac, m, s, u, m, vt, k, work, lwork, info)
         if (info /= 0) stop "linalg_svd_econ: dgesvd failed"
      end subroutine linalg_svd_econ

      pure subroutine leggauss(n, x, w)
         ! Gauss-Legendre quadrature nodes and weights on [-1, 1], matching
         ! numpy.polynomial.legendre.leggauss(n). Classic Newton-iteration
         ! algorithm (nodes are the roots of the degree-n Legendre
         ! polynomial P_n, found via the three-term recurrence for P_n and
         ! its derivative; weights follow from P_n'(x_i)) -- see e.g.
         ! Numerical Recipes' gauleg. Converges to full double precision,
         ! so results match numpy's own (eigenvalue-based) implementation
         ! to within the run-diff numeric tolerance.
         integer, intent(in) :: n
         real(kind=dp), allocatable, intent(out) :: x(:), w(:)
         real(kind=dp), parameter :: eps = 1.0e-15_dp
         real(kind=dp) :: p1, p2, p3, pp, z, z1
         integer :: i, j, m
         allocate(x(1:n), source=0.0_dp)
         allocate(w(1:n), source=0.0_dp)
         m = (n + 1) / 2
         do i = 1, m
            z = cos(acos(-1.0_dp) * (real(i, kind=dp) - 0.25_dp) / (real(n, kind=dp) + 0.5_dp))
            do
               p1 = 1.0_dp
               p2 = 0.0_dp
               do j = 1, n
                  p3 = p2
                  p2 = p1
                  p1 = ((2.0_dp * j - 1.0_dp) * z * p2 - (j - 1.0_dp) * p3) / real(j, kind=dp)
               end do
               pp = real(n, kind=dp) * (z * p1 - p2) / (z * z - 1.0_dp)
               z1 = z
               z = z1 - p1 / pp
               if (abs(z - z1) <= eps) exit
            end do
            x(i) = -z
            x(n + 1 - i) = z
            w(i) = 2.0_dp / ((1.0_dp - z * z) * pp * pp)
            w(n + 1 - i) = w(i)
         end do
      end subroutine leggauss

      pure real(kind=dp) function quantile_linear(x, q)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in) :: q
         real(kind=dp), allocatable :: xs(:)
         real(kind=dp) :: qq, pos, frac
         integer :: n, lo, hi
         n = size(x)
         if (n <= 0) then
            quantile_linear = 0.0_dp
            return
         end if
         if (any(ieee_is_nan(x))) then
            quantile_linear = ieee_value(1.0_dp, ieee_quiet_nan)
            return
         end if
         allocate(xs(1:n), source=x)
         call sort_vec(xs)
         qq = max(0.0_dp, min(1.0_dp, q))
         if (n == 1) then
            quantile_linear = xs(1)
            return
         end if
         pos = qq * real(n - 1, kind=dp) + 1.0_dp
         lo = int(floor(pos))
         hi = min(n, lo + 1)
         frac = pos - real(lo, kind=dp)
         ! numpy's interpolation, exact at the data points (so an infinite
         ! neighbour does not give NaN); halfway, the mean of the two, as
         ! np.median takes.
         if (frac == 0.0_dp) then
            quantile_linear = xs(lo)
         else if (frac == 0.5_dp) then
            quantile_linear = (xs(lo) + xs(hi)) / 2.0_dp
         else if (frac < 0.5_dp) then
            quantile_linear = xs(lo) + (xs(hi) - xs(lo)) * frac
         else
            quantile_linear = xs(hi) - (xs(hi) - xs(lo)) * (1.0_dp - frac)
         end if
      end function quantile_linear

      pure function quantile_linear_vec(x, q) result(out)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in) :: q(:)
         real(kind=dp) :: out(size(q))
         integer :: i
         do i = 1, size(q)
            out(i) = quantile_linear(x, q(i))
         end do
      end function quantile_linear_vec

      pure function statistics_quantiles_real(x, n) result(q)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: n
         real(kind=dp), allocatable :: q(:)
         real(kind=dp), allocatable :: xs(:)
         real(kind=dp) :: h, frac
         integer :: m, nq, i, lo, hi

         nq = max(0, n - 1)
         allocate(q(nq), source=0.0_dp)
         m = size(x)
         if (m <= 0 .or. n <= 1) return
         allocate(xs(m), source=x)
         call sort_real_vec(xs)
         do i = 1, nq
            h = real(i * (m + 1), kind=dp) / real(n, kind=dp)
            if (h <= 1.0_dp) then
               q(i) = xs(1)
            else if (h >= real(m, kind=dp)) then
               q(i) = xs(m)
            else
               lo = int(floor(h))
               hi = lo + 1
               frac = h - real(lo, kind=dp)
               q(i) = (1.0_dp - frac) * xs(lo) + frac * xs(hi)
            end if
         end do
      end function statistics_quantiles_real

      pure real(kind=dp) function var(x, ddof)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         integer :: n, d
         real(kind=dp) :: mu
         n = size(x)
         if (present(ddof)) then
            d = ddof
         else
            d = 0
         end if
         if (n <= d .or. n <= 0) then
            var = 0.0_dp
            return
         end if
         mu = mean(x)
         var = sum((x - mu)**2) / real(n - d, kind=dp)
      end function var

      pure real(kind=dp) function mean(x)
         real(kind=dp), intent(in) :: x(:)
         if (size(x) <= 0) then
            mean = 0.0_dp
         else
            mean = sum(x) / real(size(x), kind=dp)
         end if
      end function mean

      pure real(kind=dp) function std(x, ddof)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         if (present(ddof)) then
            std = sqrt(var(x, ddof))
         else
            std = sqrt(var(x))
         end if
      end function std

      pure elemental real(kind=dp) function log2(x)
         real(kind=dp), intent(in) :: x
         real(kind=dp), parameter :: log2_base = log(2.0_dp)
         log2 = log(x) / log2_base
      end function log2

      pure real(kind=dp) function nansum(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i
         nansum = 0.0_dp
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) nansum = nansum + x(i)
         end do
      end function nansum

      pure real(kind=dp) function nanmean(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i, cnt
         nanmean = 0.0_dp
         cnt = 0
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               nanmean = nanmean + x(i)
               cnt = cnt + 1
            end if
         end do
         if (cnt <= 0) then
            nanmean = ieee_value(0.0_dp, ieee_quiet_nan)
         else
            nanmean = nanmean / real(cnt, kind=dp)
         end if
      end function nanmean

      pure real(kind=dp) function nanvar(x, ddof)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         integer :: i, cnt, d
         real(kind=dp) :: mu, ss
         if (present(ddof)) then
            d = ddof
         else
            d = 0
         end if
         mu = nanmean(x)
         if (ieee_is_nan(mu)) then
            nanvar = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         cnt = 0
         ss = 0.0_dp
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               cnt = cnt + 1
               ss = ss + (x(i) - mu)**2
            end if
         end do
         if (cnt - d <= 0) then
            nanvar = ieee_value(0.0_dp, ieee_quiet_nan)
         else
            nanvar = ss / real(cnt - d, kind=dp)
         end if
      end function nanvar

      pure real(kind=dp) function nanstd(x, ddof)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         if (present(ddof)) then
            nanstd = sqrt(nanvar(x, ddof))
         else
            nanstd = sqrt(nanvar(x))
         end if
      end function nanstd

      pure real(kind=dp) function nanmin(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i
         logical :: found
         found = .false.
         nanmin = ieee_value(0.0_dp, ieee_quiet_nan)
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               if (.not. found) then
                  nanmin = x(i)
                  found = .true.
               else
                  if (x(i) < nanmin) nanmin = x(i)
               end if
            end if
         end do
      end function nanmin

      pure real(kind=dp) function nanmax(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i
         logical :: found
         found = .false.
         nanmax = ieee_value(0.0_dp, ieee_quiet_nan)
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               if (.not. found) then
                  nanmax = x(i)
                  found = .true.
               else
                  if (x(i) > nanmax) nanmax = x(i)
               end if
            end if
         end do
      end function nanmax

      pure integer function nanargmin(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i, best
         logical :: found
         found = .false.
         best = -1
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               if (.not. found) then
                  best = i
                  found = .true.
               else
                  if (x(i) < x(best)) best = i
               end if
            end if
         end do
         if (found) then
            nanargmin = best - 1
         else
            nanargmin = -1
         end if
      end function nanargmin

      pure integer function nanargmax(x)
         real(kind=dp), intent(in) :: x(:)
         integer :: i, best
         logical :: found
         found = .false.
         best = -1
         do i = 1, size(x)
            if (.not. ieee_is_nan(x(i))) then
               if (.not. found) then
                  best = i
                  found = .true.
               else
                  if (x(i) > x(best)) best = i
               end if
            end if
         end do
         if (found) then
            nanargmax = best - 1
         else
            nanargmax = -1
         end if
      end function nanargmax

      pure subroutine unique_int_counts(a, u, cnt)
         integer, intent(in) :: a(:)
         integer, allocatable, intent(out) :: u(:), cnt(:)
         integer :: i, j
         u = unique_int(a)
         allocate(cnt(size(u)))
         cnt = 0
         do i = 1, size(a)
            do j = 1, size(u)
               if (a(i) == u(j)) then
                  cnt(j) = cnt(j) + 1
                  exit
               end if
            end do
         end do
      end subroutine unique_int_counts

      pure function tri_int(n, m, k) result(t)
         integer, intent(in) :: n, m
         integer, intent(in), optional :: k
         integer, allocatable :: t(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         allocate(t(n, m))
         t = 0
         do i = 1, n
            do j = 1, m
               if (j <= i + kk) t(i, j) = 1
            end do
         end do
      end function tri_int

      pure function tri_real(n, m, k) result(t)
         integer, intent(in) :: n, m
         integer, intent(in), optional :: k
         real(kind=dp), allocatable :: t(:,:)
         integer :: i, j, kk
         kk = 0
         if (present(k)) kk = k
         allocate(t(n, m))
         t = 0.0_dp
         do i = 1, n
            do j = 1, m
               if (j <= i + kk) t(i, j) = 1.0_dp
            end do
         end do
      end function tri_real

      pure function moveaxis3_int(a, src, dst) result(b)
         integer, intent(in) :: a(:,:,:)
         integer, intent(in) :: src, dst
         integer, allocatable :: b(:,:,:)
         integer :: s, d
         s = src; d = dst
         if (s < 0) s = s + 3
         if (d < 0) d = d + 3
         if (s == 0 .and. d == 2) then
            allocate(b(size(a,2), size(a,3), size(a,1)))
            b = reshape(a, [size(a,2), size(a,3), size(a,1)], order=[2,3,1])
         elseif (s == 2 .and. d == 0) then
            allocate(b(size(a,3), size(a,1), size(a,2)))
            b = reshape(a, [size(a,3), size(a,1), size(a,2)], order=[3,1,2])
         else
            allocate(b(size(a,1), size(a,2), size(a,3)))
            b = a
         end if
      end function moveaxis3_int

      pure function moveaxis3_real(a, src, dst) result(b)
         real(kind=dp), intent(in) :: a(:,:,:)
         integer, intent(in) :: src, dst
         real(kind=dp), allocatable :: b(:,:,:)
         integer :: s, d
         s = src; d = dst
         if (s < 0) s = s + 3
         if (d < 0) d = d + 3
         if (s == 0 .and. d == 2) then
            allocate(b(size(a,2), size(a,3), size(a,1)))
            b = reshape(a, [size(a,2), size(a,3), size(a,1)], order=[2,3,1])
         elseif (s == 2 .and. d == 0) then
            allocate(b(size(a,3), size(a,1), size(a,2)))
            b = reshape(a, [size(a,3), size(a,1), size(a,2)], order=[3,1,2])
         else
            allocate(b(size(a,1), size(a,2), size(a,3)))
            b = a
         end if
      end function moveaxis3_real

      pure function moveaxis3_logical(a, src, dst) result(b)
         logical, intent(in) :: a(:,:,:)
         integer, intent(in) :: src, dst
         logical, allocatable :: b(:,:,:)
         integer :: s, d
         s = src; d = dst
         if (s < 0) s = s + 3
         if (d < 0) d = d + 3
         if (s == 0 .and. d == 2) then
            allocate(b(size(a,2), size(a,3), size(a,1)))
            b = reshape(a, [size(a,2), size(a,3), size(a,1)], order=[2,3,1])
         elseif (s == 2 .and. d == 0) then
            allocate(b(size(a,3), size(a,1), size(a,2)))
            b = reshape(a, [size(a,3), size(a,1), size(a,2)], order=[3,1,2])
         else
            allocate(b(size(a,1), size(a,2), size(a,3)))
            b = a
         end if
      end function moveaxis3_logical

      pure function pad2d_int(a, pt, pb, pl, pr, c) result(out)
         integer, intent(in) :: a(:,:)
         integer, intent(in) :: pt, pb, pl, pr, c
         integer, allocatable :: out(:,:)
         integer :: n0, n1
         n0 = size(a,1); n1 = size(a,2)
         allocate(out(n0 + pt + pb, n1 + pl + pr))
         out = c
         out(pt+1:pt+n0, pl+1:pl+n1) = a
      end function pad2d_int

      pure function pad2d_real(a, pt, pb, pl, pr, c) result(out)
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: pt, pb, pl, pr
         real(kind=dp), intent(in) :: c
         real(kind=dp), allocatable :: out(:,:)
         integer :: n0, n1
         n0 = size(a,1); n1 = size(a,2)
         allocate(out(n0 + pt + pb, n1 + pl + pr))
         out = c
         out(pt+1:pt+n0, pl+1:pl+n1) = a
      end function pad2d_real

      pure logical function allclose_real(a, b, rtol, atol, equal_nan)
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), intent(in), optional :: rtol, atol
         logical, intent(in), optional :: equal_nan
         real(kind=dp) :: rtolv, atolv
         logical :: eqnan
         integer :: i
         rtolv = 1.0e-5_dp
         atolv = 1.0e-8_dp
         eqnan = .false.
         if (present(rtol)) rtolv = rtol
         if (present(atol)) atolv = atol
         if (present(equal_nan)) eqnan = equal_nan
         if (size(a) /= size(b)) then
            allclose_real = .false.
            return
         end if
         allclose_real = .true.
         do i = 1, size(a)
            if (ieee_is_nan(a(i)) .or. ieee_is_nan(b(i))) then
               if (.not. (eqnan .and. ieee_is_nan(a(i)) .and. ieee_is_nan(b(i)))) then
                  allclose_real = .false.
                  return
               end if
            else if (a(i) /= b(i)) then
               ! Equal values (also equal infinities) are close; a
               ! non-finite value otherwise is not (numpy's rule).
               if (.not. (ieee_is_finite(a(i)) .and. ieee_is_finite(b(i)))) then
                  allclose_real = .false.
                  return
               end if
               if (abs(a(i) - b(i)) > atolv + rtolv * abs(b(i))) then
                  allclose_real = .false.
                  return
               end if
            end if
         end do
      end function allclose_real

      pure logical function allclose_integer(a, b, rtol, atol)
         integer, intent(in) :: a(:), b(:)
         real(kind=dp), intent(in), optional :: rtol, atol
         real(kind=dp) :: rtolv, atolv
         integer :: i
         rtolv = 1.0e-5_dp
         atolv = 1.0e-8_dp
         if (present(rtol)) rtolv = rtol
         if (present(atol)) atolv = atol
         if (size(a) /= size(b)) then
            allclose_integer = .false.
            return
         end if
         allclose_integer = .true.
         do i = 1, size(a)
            if (abs(real(a(i), kind=dp) - real(b(i), kind=dp)) > atolv + rtolv * abs(real(b(i), kind=dp))) then
               allclose_integer = .false.
               return
            end if
         end do
      end function allclose_integer

      pure function isclose_real(a, b, rtol, atol, equal_nan) result(mask)
         ! Element-wise version of allclose_real's same tolerance test
         ! (abs(a-b) <= atol + rtol*abs(b)) and the same NaN handling
         ! (a NaN element is never "close" unless equal_nan is true and
         ! both sides are NaN), matching numpy.isclose. Explicit
         ! if/else control flow (not an elemental expression combining
         ! the NaN check and the comparison via .and.) so the unsafe
         ! ordered comparison never actually runs on a NaN operand --
         ! Fortran's .and. is not guaranteed to short-circuit, and this
         ! project's -ffpe-trap=invalid build turns an ordered
         ! comparison against a real NaN into a SIGFPE crash. a or b
         ! (but not both) may have length 1 to broadcast against the
         ! other, matching numpy's scalar-broadcasting for this call
         ! shape.
         real(kind=dp), intent(in) :: a(:), b(:)
         real(kind=dp), intent(in), optional :: rtol, atol
         logical, intent(in), optional :: equal_nan
         logical, allocatable :: mask(:)
         real(kind=dp) :: rtolv, atolv, av, bv
         logical :: eqnan
         integer :: i, n
         rtolv = 1.0e-5_dp
         atolv = 1.0e-8_dp
         eqnan = .false.
         if (present(rtol)) rtolv = rtol
         if (present(atol)) atolv = atol
         if (present(equal_nan)) eqnan = equal_nan
         ! numpy broadcasting: an empty operand gives an empty result.
         n = max(size(a), size(b))
         if (size(a) == 0 .or. size(b) == 0) n = 0
         allocate(mask(1:n))
         do i = 1, n
            if (size(a) == 1) then
               av = a(1)
            else
               av = a(i)
            end if
            if (size(b) == 1) then
               bv = b(1)
            else
               bv = b(i)
            end if
            if (ieee_is_nan(av) .or. ieee_is_nan(bv)) then
               mask(i) = eqnan .and. ieee_is_nan(av) .and. ieee_is_nan(bv)
            else if (av == bv) then
               ! Also equal infinities.
               mask(i) = .true.
            else if (.not. (ieee_is_finite(av) .and. ieee_is_finite(bv))) then
               mask(i) = .false.
            else
               mask(i) = abs(av - bv) <= atolv + rtolv * abs(bv)
            end if
         end do
      end function isclose_real

      pure function isclose_scalar_real(a, b, rtol, atol, equal_nan) result(is_close)
         ! Scalar counterpart of isclose_real, same tolerance test and
         ! NaN handling -- needed because a plain (non-pointer) array-
         ! valued function's result can't be indexed at the call site in
         ! standard Fortran (`isclose_real([a], [b], ...)(1)` is a
         ! syntax error, not just non-idiomatic: confirmed directly with
         ! gfortran), which is what xp2f.py used to emit whenever BOTH
         ! np.isclose() arguments were scalar. Found mining
         ! TheAlgorithms/Python's own linear_algebra/gauss_jordan.py:
         ! `not np.isclose(scalar, 0)`.
         real(kind=dp), intent(in) :: a, b
         real(kind=dp), intent(in), optional :: rtol, atol
         logical, intent(in), optional :: equal_nan
         logical :: is_close
         real(kind=dp) :: rtolv, atolv
         logical :: eqnan
         rtolv = 1.0e-5_dp
         atolv = 1.0e-8_dp
         eqnan = .false.
         if (present(rtol)) rtolv = rtol
         if (present(atol)) atolv = atol
         if (present(equal_nan)) eqnan = equal_nan
         if (ieee_is_nan(a) .or. ieee_is_nan(b)) then
            is_close = eqnan .and. ieee_is_nan(a) .and. ieee_is_nan(b)
         else if (a == b) then
            is_close = .true.
         else if (.not. (ieee_is_finite(a) .and. ieee_is_finite(b))) then
            is_close = .false.
         else
            is_close = abs(a - b) <= atolv + rtolv * abs(b)
         end if
      end function isclose_scalar_real

      pure function cov2_real(x, y, ddof) result(c)
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in), optional :: ddof
         real(kind=dp), allocatable :: c(:,:)
         real(kind=dp) :: mx, my, vxx, vyy, vxy, den
         integer :: n, d
         n = min(size(x), size(y))
         d = 1
         if (present(ddof)) d = ddof
         mx = sum(x(1:n)) / real(n, kind=dp)
         my = sum(y(1:n)) / real(n, kind=dp)
         den = real(max(1, n - d), kind=dp)
         vxx = sum((x(1:n) - mx)**2) / den
         vyy = sum((y(1:n) - my)**2) / den
         vxy = sum((x(1:n) - mx) * (y(1:n) - my)) / den
         allocate(c(2,2))
         c(1,1) = vxx; c(1,2) = vxy
         c(2,1) = vxy; c(2,2) = vyy
      end function cov2_real

      pure function cov_matrix_rows_real(x, ddof) result(c)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: ddof
         real(kind=dp), allocatable :: c(:,:)
         real(kind=dp), allocatable :: xc(:,:), mu(:)
         integer :: n, p, d
         n = size(x, 1)
         p = size(x, 2)
         d = 1
         if (present(ddof)) d = ddof
         allocate(c(p, p))
         if (n <= 0 .or. p <= 0) then
            c = 0.0_dp
            return
         end if
         allocate(mu(p), xc(n, p))
         mu = sum(x, dim=1) / real(n, kind=dp)
         xc = x - spread(mu, dim=1, ncopies=n)
         c = matmul(transpose(xc), xc) / real(max(1, n - d), kind=dp)
      end function cov_matrix_rows_real

      pure function corrcoef2_real(x, y) result(r)
         real(kind=dp), intent(in) :: x(:), y(:)
         real(kind=dp), allocatable :: r(:,:)
         real(kind=dp), allocatable :: c(:,:)
         real(kind=dp) :: sx, sy
         c = cov2_real(x, y, 1)
         sx = sqrt(max(c(1,1), 0.0_dp))
         sy = sqrt(max(c(2,2), 0.0_dp))
         allocate(r(2,2))
         if (sx <= tiny(1.0_dp) .or. sy <= tiny(1.0_dp)) then
            r = 0.0_dp
            r(1,1) = 1.0_dp
            r(2,2) = 1.0_dp
         else
            r(1,1) = 1.0_dp
            r(2,2) = 1.0_dp
            r(1,2) = c(1,2) / (sx * sy)
            r(2,1) = r(1,2)
         end if
      end function corrcoef2_real

      pure real(kind=dp) function corr2_1d(x, y)
         ! Pearson correlation of two 1D real vectors, as a plain scalar
         ! -- a thin wrapper around corrcoef2_real (whose 2x2 matrix
         ! result can't be subscripted inline in the same expression as
         ! the call itself, not being a Fortran variable). Shared by
         ! autocorr_1d (x against a shifted copy of itself) and
         ! DataFrame.corrwith(other) (each column against `other`).
         real(kind=dp), intent(in) :: x(:), y(:)
         real(kind=dp), allocatable :: r(:,:)
         r = corrcoef2_real(x, y)
         corr2_1d = r(1, 2)
      end function corr2_1d

      pure real(kind=dp) function autocorr_1d(x, lag)
         ! pandas Series.autocorr(lag) -- lag-k serial correlation of a
         ! vector with itself.
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: lag
         integer :: k, n
         k = 1
         if (present(lag)) k = lag
         n = size(x)
         if (k <= 0 .or. k >= n) then
            autocorr_1d = ieee_value(0.0_dp, ieee_quiet_nan)
            return
         end if
         autocorr_1d = corr2_1d(x(1:n - k), x(1 + k:n))
      end function autocorr_1d

      pure function corrcoef_matrix_rows_real(x) result(r)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: r(:,:)
         real(kind=dp), allocatable :: c(:,:), s(:)
         integer :: i, j, p
         c = cov_matrix_rows_real(x, 1)
         p = size(c, 1)
         allocate(r(p, p), s(p))
         do i = 1, p
            s(i) = sqrt(max(c(i,i), 0.0_dp))
         end do
         r = 0.0_dp
         do i = 1, p
            r(i,i) = 1.0_dp
            do j = i + 1, p
               if (s(i) > tiny(1.0_dp) .and. s(j) > tiny(1.0_dp)) then
                  r(i,j) = c(i,j) / (s(i) * s(j))
                  r(j,i) = r(i,j)
               end if
            end do
         end do
      end function corrcoef_matrix_rows_real

      function convolve_real(x, h, mode, np_same) result(y)
         ! 1-D convolution, mode full/same/valid. "same": the length of x,
         ! centered (scipy.signal.convolve), or with np_same numpy's
         ! np.convolve: the longer length, from (min(nx, nh) - 1) / 2.
         real(kind=dp), intent(in) :: x(:), h(:)
         character(len=*), intent(in), optional :: mode
         logical, intent(in), optional :: np_same
         real(kind=dp), allocatable :: y(:), full(:)
         integer :: i, j, nx, nh, ny, start, stop
         character(len=:), allocatable :: m
         nx = size(x)
         nh = size(h)
         if (nx <= 0 .or. nh <= 0) then
            allocate(y(0))
            return
         end if
         allocate(full(nx + nh - 1))
         full = 0.0_dp
         do i = 1, nx
            do j = 1, nh
               full(i + j - 1) = full(i + j - 1) + x(i) * h(j)
            end do
         end do
         m = "full"
         if (present(mode)) m = to_lower(trim(mode))
         if (m == "full") then
            y = full
            return
         end if
         if (m == "same") then
            ny = nx
            start = (nh - 1) / 2 + 1
            if (present(np_same)) then
               if (np_same) then
                  ny = max(nx, nh)
                  start = (min(nx, nh) - 1) / 2 + 1
               end if
            end if
            stop = start + ny - 1
            y = full(start:stop)
            return
         end if
         if (m == "valid") then
            ny = max(nx, nh) - min(nx, nh) + 1
            if (ny <= 0) then
               allocate(y(0))
            else
               start = min(nx, nh)
               stop = start + ny - 1
               y = full(start:stop)
            end if
            return
         end if
         y = full
      end function convolve_real

      pure function diff_axis0_real_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         if (size(x, 1) <= 1) then
            allocate(y(0, size(x, 2)))
            return
         end if
         y = x(2:, :) - x(:size(x, 1) - 1, :)
      end function diff_axis0_real_2d

      pure function diff_axis1_real_2d(x) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         real(kind=dp), allocatable :: y(:,:)
         if (size(x, 2) <= 1) then
            allocate(y(size(x, 1), 0))
            return
         end if
         y = x(:, 2:) - x(:, :size(x, 2) - 1)
      end function diff_axis1_real_2d


      pure function sliding_window_view_axis0_real_2d(a, window) result(out)
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: window
         real(kind=dp), allocatable :: out(:,:,:)
         integer :: i, j, k, nwin
         if (window <= 0) then
            allocate(out(0, size(a, 2), 0))
            return
         end if
         nwin = max(0, size(a, 1) - window + 1)
         allocate(out(nwin, size(a, 2), window))
         do i = 1, nwin
            do j = 1, size(a, 2)
               do k = 1, window
                  out(i, j, k) = a(i + k - 1, j)
               end do
            end do
         end do
      end function sliding_window_view_axis0_real_2d


      function convolve_int(x, h, mode, np_same) result(y)
         ! 1-D convolution, mode full/same/valid. "same": the length of x,
         ! centered (scipy.signal.convolve), or with np_same numpy's
         ! np.convolve: the longer length, from (min(nx, nh) - 1) / 2.
         integer, intent(in) :: x(:), h(:)
         character(len=*), intent(in), optional :: mode
         logical, intent(in), optional :: np_same
         integer, allocatable :: y(:), full(:)
         integer :: i, j, nx, nh, ny, start, stop
         character(len=:), allocatable :: m
         nx = size(x)
         nh = size(h)
         if (nx <= 0 .or. nh <= 0) then
            allocate(y(0))
            return
         end if
         allocate(full(nx + nh - 1))
         full = 0
         do i = 1, nx
            do j = 1, nh
               full(i + j - 1) = full(i + j - 1) + x(i) * h(j)
            end do
         end do
         m = "full"
         if (present(mode)) m = to_lower(trim(mode))
         if (m == "full") then
            y = full
            return
         end if
         if (m == "same") then
            ny = nx
            start = (nh - 1) / 2 + 1
            if (present(np_same)) then
               if (np_same) then
                  ny = max(nx, nh)
                  start = (min(nx, nh) - 1) / 2 + 1
               end if
            end if
            stop = start + ny - 1
            y = full(start:stop)
            return
         end if
         if (m == "valid") then
            ny = max(nx, nh) - min(nx, nh) + 1
            if (ny <= 0) then
               allocate(y(0))
            else
               start = min(nx, nh)
               stop = start + ny - 1
               y = full(start:stop)
            end if
            return
         end if
         y = full
      end function convolve_int

      function correlate_real(x, y, mode, np_same) result(out)
         ! scipy.signal.correlate(x, y) = convolve(x, conj(y[::-1])) for
         ! real inputs -- reuse convolve_real with y time-reversed. "same"
         ! with np_same: np.correlate's, the longer length, from
         ! (k - 1) / 2 of the full correlation (k / 2 when x is the
         ! shorter, k = min(nx, ny)).
         real(kind=dp), intent(in) :: x(:), y(:)
         character(len=*), intent(in), optional :: mode
         logical, intent(in), optional :: np_same
         real(kind=dp), allocatable :: out(:), full(:)
         integer :: k, start
         logical :: nps
         nps = .false.
         if (present(np_same)) nps = np_same
         if (present(mode) .and. nps .and. size(x) > 0 .and. size(y) > 0) then
            if (to_lower(trim(mode)) == "same") then
               full = convolve_real(x, y(size(y):1:-1))
               k = min(size(x), size(y))
               start = (k - 1) / 2
               if (size(x) < size(y)) start = k / 2
               out = full(start + 1:start + max(size(x), size(y)))
               return
            end if
         end if
         if (present(mode)) then
            out = convolve_real(x, y(size(y):1:-1), mode)
         else
            out = convolve_real(x, y(size(y):1:-1))
         end if
      end function correlate_real

      pure function lfilter_real(b, a, x, zi) result(y)
         ! scipy.signal.lfilter(b, a, x), zero initial conditions unless
         ! zi is given: Direct Form II Transposed IIR/FIR recursion (the
         ! same structure scipy's own Fortran/C backend uses). b and a
         ! are zero-padded to a common length k = max(size(b), size(a))
         ! and normalized by a(1); z holds the k-1 filter delay states.
         real(kind=dp), intent(in) :: b(:), a(:), x(:)
         real(kind=dp), intent(in), optional :: zi(:)
         real(kind=dp), allocatable :: y(:)
         real(kind=dp), allocatable :: bn(:), an(:), z(:)
         integer :: nb, na, k, n, i, j
         real(kind=dp) :: a0

         nb = size(b)
         na = size(a)
         k = max(nb, na)
         a0 = a(1)
         allocate(bn(k), an(k))
         bn = 0.0_dp
         an = 0.0_dp
         bn(1:nb) = b / a0
         an(1:na) = a / a0

         n = size(x)
         allocate(y(n))
         allocate(z(max(k - 1, 1)))
         z = 0.0_dp
         if (present(zi)) z(1:size(zi)) = zi

         do i = 1, n
            y(i) = bn(1) * x(i) + z(1)
            do j = 1, k - 2
               z(j) = bn(j + 1) * x(i) + z(j + 1) - an(j + 1) * y(i)
            end do
            if (k >= 2) z(k - 1) = bn(k) * x(i) - an(k) * y(i)
         end do
      end function lfilter_real

      function lfilter_zi_real(b, a) result(zi)
         ! scipy.signal.lfilter_zi(b, a): steady-state initial filter
         ! state for a unit step input, found by solving
         ! (I - companion(a).T) @ zi = b(2:) - a(2:)*b(1) for normalized
         ! b, a (a(1) = 1). Used by filtfilt_real to avoid startup
         ! transients on both the forward and backward pass.
         real(kind=dp), intent(in) :: b(:), a(:)
         real(kind=dp), allocatable :: zi(:)
         real(kind=dp), allocatable :: bn(:), an(:), iminusa(:,:), rhs(:)
         integer :: nb, na, n, m, i
         real(kind=dp) :: a0

         nb = size(b)
         na = size(a)
         n = max(nb, na)
         a0 = a(1)
         allocate(bn(n), an(n))
         bn = 0.0_dp
         an = 0.0_dp
         bn(1:nb) = b / a0
         an(1:na) = a / a0

         m = n - 1
         if (m <= 0) then
            allocate(zi(0))
            return
         end if

         allocate(iminusa(m, m), rhs(m))
         iminusa = 0.0_dp
         do i = 1, m
            iminusa(i, 1) = an(i + 1)
            iminusa(i, i) = iminusa(i, i) + 1.0_dp
            if (i < m) iminusa(i, i + 1) = iminusa(i, i + 1) - 1.0_dp
            rhs(i) = bn(i + 1) - an(i + 1) * bn(1)
         end do
         zi = linalg_solve_vec(iminusa, rhs)
      end function lfilter_zi_real

      function filtfilt_real(b, a, x) result(y)
         ! scipy.signal.filtfilt(b, a, x): zero-phase filtering, forward
         ! pass then backward pass, each seeded with lfilter_zi-based
         ! steady-state initial conditions scaled by the pass's first
         ! sample -- this matches scipy's own filtfilt(..., padtype=None)
         ! exactly. scipy's *default* additionally pads the signal
         ! (padtype='odd', padlen=3*max(len(a),len(b))) before filtering
         ! to further damp edge transients, which this does not
         ! reproduce -- results match closely away from the signal's
         ! edges, less so near them.
         real(kind=dp), intent(in) :: b(:), a(:), x(:)
         real(kind=dp), allocatable :: y(:), tmp(:), zi(:)
         zi = lfilter_zi_real(b, a)
         tmp = lfilter_real(b, a, x, zi * x(1))
         tmp = tmp(size(tmp):1:-1)
         tmp = lfilter_real(b, a, tmp, zi * tmp(1))
         y = tmp(size(tmp):1:-1)
      end function filtfilt_real

      pure function detrend_real(x, dtype) result(y)
         ! scipy.signal.detrend(x, type='linear'|'constant').
         real(kind=dp), intent(in) :: x(:)
         character(len=*), intent(in), optional :: dtype
         real(kind=dp), allocatable :: y(:)
         character(len=:), allocatable :: dt
         integer :: n, i
         real(kind=dp) :: mean_x, mean_t, sxt, stt, slope, intercept, t

         n = size(x)
         dt = "linear"
         if (present(dtype)) dt = to_lower(trim(dtype))

         if (dt == "constant") then
            mean_x = sum(x) / real(n, kind=dp)
            y = x - mean_x
            return
         end if

         mean_t = real(n - 1, kind=dp) / 2.0_dp
         mean_x = sum(x) / real(n, kind=dp)
         sxt = 0.0_dp
         stt = 0.0_dp
         do i = 1, n
            t = real(i - 1, kind=dp)
            sxt = sxt + (t - mean_t) * (x(i) - mean_x)
            stt = stt + (t - mean_t)**2
         end do
         if (stt <= 0.0_dp) then
            slope = 0.0_dp
         else
            slope = sxt / stt
         end if
         intercept = mean_x - slope * mean_t
         allocate(y(n))
         do i = 1, n
            t = real(i - 1, kind=dp)
            y(i) = x(i) - (intercept + slope * t)
         end do
      end function detrend_real

      pure function find_peaks_int(x, height, distance) result(peaks)
         ! scipy.signal.find_peaks(x, height=None, distance=None), peak
         ! indices only (0-based, numpy-compatible) -- the properties
         ! dict scipy also returns is not reproduced. Peaks are strict
         ! local maxima (x(i) > both neighbors); flat-top plateaus, which
         ! scipy resolves to their midpoint, are not detected here.
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in), optional :: height
         integer, intent(in), optional :: distance
         integer, allocatable :: peaks(:)
         integer, allocatable :: cand(:), kept(:)
         logical, allocatable :: keep(:), alive(:)
         integer :: n, i, nc, best
         real(kind=dp) :: bestval

         n = size(x)
         allocate(cand(0))
         do i = 2, n - 1
            if (x(i) > x(i - 1) .and. x(i) > x(i + 1)) then
               cand = [cand, i]
            end if
         end do

         if (present(height)) then
            kept = pack(cand, x(cand) >= height)
            cand = kept
         end if
         nc = size(cand)

         if (present(distance) .and. nc > 0) then
            allocate(keep(nc), alive(nc))
            keep = .false.
            alive = .true.
            do while (any(alive))
               best = 0
               bestval = -huge(1.0_dp)
               do i = 1, nc
                  if (alive(i) .and. x(cand(i)) > bestval) then
                     bestval = x(cand(i))
                     best = i
                  end if
               end do
               keep(best) = .true.
               alive(best) = .false.
               do i = 1, nc
                  if (alive(i) .and. abs(cand(i) - cand(best)) < distance) alive(i) = .false.
               end do
            end do
            cand = pack(cand, keep)
            call sort_int_vec(cand)
         end if

         allocate(peaks(size(cand)))
         peaks = cand - 1
      end function find_peaks_int

      pure real(kind=dp) function polyval_real_scalar(p, x) result(y)
         real(kind=dp), intent(in) :: p(:)
         real(kind=dp), intent(in) :: x
         integer :: i
         if (size(p) <= 0) then
            y = 0.0_dp
            return
         end if
         y = p(1)
         do i = 2, size(p)
            y = y * x + p(i)
         end do
      end function polyval_real_scalar

      pure function polyval_real_vec(p, x) result(y)
         real(kind=dp), intent(in) :: p(:)
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x)))
         do i = 1, size(x)
            y(i) = polyval_real_scalar(p, x(i))
         end do
      end function polyval_real_vec

      pure complex(kind=dp) function polyval_complex_scalar(p, x) result(y)
         ! np.polyval(p, x) of complex coefficients or a complex x (Horner).
         complex(kind=dp), intent(in) :: p(:)
         complex(kind=dp), intent(in) :: x
         integer :: i
         y = (0.0_dp, 0.0_dp)
         if (size(p) <= 0) return
         y = p(1)
         do i = 2, size(p)
            y = y * x + p(i)
         end do
      end function polyval_complex_scalar

      pure function polyval_complex_vec(p, x) result(y)
         complex(kind=dp), intent(in) :: p(:)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), allocatable :: y(:)
         integer :: i
         allocate(y(size(x)))
         do i = 1, size(x)
            y(i) = polyval_complex_scalar(p, x(i))
         end do
      end function polyval_complex_vec

      function polyfit_real(x, y, deg) result(coeffs)
         ! Least-squares polynomial fit, matching numpy.polyfit(x, y, deg):
         ! returns deg+1 coefficients, highest degree first (same
         ! convention as polyval/roots). Builds the Vandermonde matrix and
         ! solves the normal equations (V^T V) c = V^T y via linalg_solve.
         ! numpy itself uses an SVD-based least-squares solve for extra
         ! numerical stability on ill-conditioned fits; the normal-
         ! equations approach here matches it closely for well-conditioned
         ! data (run-diff's numeric tolerance covers the difference).
         real(kind=dp), intent(in) :: x(:), y(:)
         integer, intent(in) :: deg
         real(kind=dp), allocatable :: coeffs(:)
         real(kind=dp), allocatable :: v(:,:)
         integer :: n, m, i, j
         n = size(x)
         m = deg + 1
         allocate(v(1:n, 1:m))
         do i = 1, n
            do j = 1, m
               v(i, j) = x(i) ** (deg - (j - 1))
            end do
         end do
         coeffs = linalg_solve(matmul(transpose(v), v), matmul(transpose(v), y))
      end function polyfit_real

      pure function digitize_real(x, bins) result(idx)
         ! Bin index of each x(i) against increasing bin edges, matching
         ! numpy.digitize(x, bins) with its default right=False: idx(i)
         ! is the count of bin edges <= x(i) (0 if x(i) < bins(1), size
         ! (bins) if x(i) >= bins(last)). Decreasing bins and right=True
         ! are not handled.
         real(kind=dp), intent(in) :: x(:), bins(:)
         integer, allocatable :: idx(:)
         integer :: i, j, n, nb
         n = size(x)
         nb = size(bins)
         allocate(idx(1:n))
         do i = 1, n
            j = 0
            do while (j < nb)
               if (x(i) >= bins(j + 1)) then
                  j = j + 1
               else
                  exit
               end if
            end do
            idx(i) = j
         end do
      end function digitize_real

      pure function isin_real(a, b) result(mask)
         ! mask(i) = a(i) is present (exactly) in b, matching
         ! numpy.isin(a, b) (and its older alias numpy.in1d) for real
         ! arrays.
         real(kind=dp), intent(in) :: a(:), b(:)
         logical, allocatable :: mask(:)
         integer :: i
         allocate(mask(1:size(a)))
         do i = 1, size(a)
            mask(i) = any(a(i) == b)
         end do
      end function isin_real

      pure function isin_int(a, b) result(mask)
         ! Integer counterpart of isin_real.
         integer, intent(in) :: a(:), b(:)
         logical, allocatable :: mask(:)
         integer :: i
         allocate(mask(1:size(a)))
         do i = 1, size(a)
            mask(i) = any(a(i) == b)
         end do
      end function isin_int

      subroutine np_save_1d_real(filename, x)
         ! Writes a 1D float64 array to a real .npy file (NumPy's binary
         ! array format: an 8-byte preamble of a magic string, a 2-byte
         ! version, and a 2-byte little-endian header length, followed by
         ! a Python-dict-literal-style ASCII header padded with spaces
         ! and a trailing newline so the whole preamble is a multiple of
         ! 64 bytes, then the raw data), matching numpy.save(path, x) for
         ! a 1D real array -- interoperable with numpy.load on the
         ! Python side and vice versa (see np_load_1d_real).
         character(len=*), intent(in) :: filename
         real(kind=dp), intent(in) :: x(:)
         character(len=:), allocatable :: base_header, header, n_str
         integer :: unit, n, unpadded_len, total_before_pad, pad, header_len
         n = size(x)
         allocate(character(len=20) :: n_str)
         write(n_str, '(I0)') n
         n_str = trim(n_str)
         base_header = "{'descr': '<f8', 'fortran_order': False, 'shape': (" &
            & // n_str // ",), }"
         unpadded_len = len(base_header) + 1
         total_before_pad = 10 + unpadded_len
         pad = 0
         if (mod(total_before_pad, 64) /= 0) pad = 64 - mod(total_before_pad, 64)
         header = base_header // repeat(' ', pad) // achar(10)
         header_len = len(header)
         open(newunit=unit, file=filename, access='stream', form='unformatted', status='replace')
         write(unit) achar(147) // 'NUMPY' // achar(1) // achar(0)
         write(unit) achar(iand(header_len, 255)), achar(iand(ishft(header_len, -8), 255))
         write(unit) header
         write(unit) x
         close(unit)
      end subroutine np_save_1d_real

      function np_load_1d_real(filename) result(x)
         ! Reads a 1D float64 array from a .npy file written by
         ! numpy.save (or np_save_1d_real). The array length is derived
         ! from the file size minus the preamble+header size rather than
         ! by parsing the header's 'shape' field, since the raw data is
         ! always float64 regardless of the exact header text.
         character(len=*), intent(in) :: filename
         real(kind=dp), allocatable :: x(:)
         character(len=8) :: preamble
         character(len=2) :: hl_bytes
         integer :: unit, header_len, n
         integer(kind=8) :: fsize
         open(newunit=unit, file=filename, access='stream', form='unformatted', status='old', action='read')
         inquire(unit=unit, size=fsize)
         read(unit) preamble
         read(unit) hl_bytes
         header_len = iachar(hl_bytes(1:1)) + 256 * iachar(hl_bytes(2:2))
         block
            character(len=header_len) :: hdr
            read(unit) hdr
         end block
         n = int((fsize - (10_8 + int(header_len, kind=8))) / 8_8)
         allocate(x(1:n))
         read(unit) x
         close(unit)
      end function np_load_1d_real

      pure function polyder_real(p, m) result(dpcoef)
         real(kind=dp), intent(in) :: p(:)
         integer, intent(in), optional :: m
         real(kind=dp), allocatable :: dpcoef(:)
         real(kind=dp), allocatable :: cur(:), nxt(:)
         integer :: i, k, order, ncur
         if (present(m)) then
            order = m
         else
            order = 1
         end if
         if (order <= 0) then
            allocate(dpcoef(size(p)))
            dpcoef = p
            return
         end if
         if (order >= size(p)) then
            ! numpy: the derivative of a constant is an empty array.
            allocate(dpcoef(0))
            return
         end if
         allocate(cur(size(p)))
         cur = p
         do k = 1, order
            ncur = size(cur) - 1
            allocate(nxt(ncur))
            do i = 1, ncur
               nxt(i) = cur(i) * real(ncur - i + 1, kind=dp)
            end do
            call move_alloc(nxt, cur)
         end do
         allocate(dpcoef(size(cur)))
         dpcoef = cur
      end function polyder_real

      function polyroots_real(p) result(r)
         real(kind=dp), intent(in) :: p(:)
         complex(kind=dp), allocatable :: r(:)
         real(kind=dp), allocatable :: ac(:,:), wr(:), wi(:), work(:), vl_dummy(:,:), vr_dummy(:,:)
         integer :: n, i, info, lwork
         interface
            subroutine dgeev(jobvl, jobvr, n, a, lda, wr, wi, vl, ldvl, vr, ldvr, work, lwork, info)
               character(len=1), intent(in) :: jobvl, jobvr
               integer, intent(in) :: n, lda, ldvl, ldvr, lwork
               integer, intent(out) :: info
               double precision, intent(inout) :: a(lda,*)
               double precision, intent(out) :: wr(*), wi(*), vl(ldvl,*), vr(ldvr,*), work(*)
            end subroutine dgeev
         end interface

         n = size(p) - 1
         if (n <= 0) then
            allocate(r(0))
            return
         end if
         if (abs(p(1)) <= tiny(1.0_dp)) stop "polyroots_real: leading coefficient must be nonzero"

         allocate(ac(n, n), source=0.0_dp)
         ac(1, :) = -p(2:n + 1) / p(1)
         do i = 2, n
            ac(i, i - 1) = 1.0_dp
         end do

         allocate(wr(n), wi(n))
         allocate(vl_dummy(1, 1), vr_dummy(1, 1))
         allocate(work(1))
         lwork = -1
         call dgeev('N', 'N', n, ac, n, wr, wi, vl_dummy, 1, vr_dummy, 1, work, lwork, info)
         if (info /= 0) stop "polyroots_real: dgeev workspace query failed"
         lwork = max(1, int(work(1)))
         deallocate(work)
         allocate(work(lwork))
         call dgeev('N', 'N', n, ac, n, wr, wi, vl_dummy, 1, vr_dummy, 1, work, lwork, info)
         if (info /= 0) stop "polyroots_real: dgeev failed"

         allocate(r(n))
         do i = 1, n
            r(i) = cmplx(wr(i), wi(i), kind=dp)
         end do
      end function polyroots_real

      pure logical function fft_is_power_of_two(n)
         integer, intent(in) :: n
         fft_is_power_of_two = n > 0 .and. iand(n, n - 1) == 0
      end function fft_is_power_of_two


      pure subroutine fft_dft_forward(x, y)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), intent(out) :: y(:)
         integer :: j, k, nn
         real(kind=dp) :: ang, twopi
         complex(kind=dp) :: w

         nn = size(x)
         twopi = 2.0_dp * acos(-1.0_dp)
         do k = 1, nn
            y(k) = cmplx(0.0_dp, 0.0_dp, kind=dp)
            do j = 1, nn
               ang = -twopi * real((k - 1) * (j - 1), kind=dp) / real(nn, kind=dp)
               w = cmplx(cos(ang), sin(ang), kind=dp)
               y(k) = y(k) + x(j) * w
            end do
         end do
      end subroutine fft_dft_forward


      pure subroutine fft_dft_inverse(x, y)
         complex(kind=dp), intent(in) :: x(:)
         complex(kind=dp), intent(out) :: y(:)
         integer :: j, k, nn
         real(kind=dp) :: ang, twopi
         complex(kind=dp) :: w

         nn = size(x)
         twopi = 2.0_dp * acos(-1.0_dp)
         do k = 1, nn
            y(k) = cmplx(0.0_dp, 0.0_dp, kind=dp)
            do j = 1, nn
               ang = twopi * real((k - 1) * (j - 1), kind=dp) / real(nn, kind=dp)
               w = cmplx(cos(ang), sin(ang), kind=dp)
               y(k) = y(k) + x(j) * w
            end do
            y(k) = y(k) / real(nn, kind=dp)
         end do
      end subroutine fft_dft_inverse


      pure subroutine fft_radix2_inplace(a, inverse)
         complex(kind=dp), intent(inout) :: a(:)
         logical, intent(in) :: inverse
         integer :: i, j, m, mmax, istep, n
         real(kind=dp) :: pi, theta, wi, wpi, wpr, wr, wtemp
         complex(kind=dp) :: temp

         n = size(a)
         if (n <= 1) return

         j = 1
         do i = 1, n
            if (i < j) then
               temp = a(j)
               a(j) = a(i)
               a(i) = temp
            end if
            m = n / 2
            do while (m >= 1 .and. j > m)
               j = j - m
               m = m / 2
            end do
            j = j + m
         end do

         pi = acos(-1.0_dp)
         mmax = 1
         do while (n > mmax)
            istep = 2 * mmax
            if (inverse) then
               theta = pi / real(mmax, kind=dp)
            else
               theta = -pi / real(mmax, kind=dp)
            end if
            wtemp = sin(0.5_dp * theta)
            wpr = -2.0_dp * wtemp * wtemp
            wpi = sin(theta)
            wr = 1.0_dp
            wi = 0.0_dp
            do m = 1, mmax
               do i = m, n, istep
                  j = i + mmax
                  temp = cmplx(wr, wi, kind=dp) * a(j)
                  a(j) = a(i) - temp
                  a(i) = a(i) + temp
               end do
               wtemp = wr
               wr = wr * wpr - wi * wpi + wr
               wi = wi * wpr + wtemp * wpi + wi
            end do
            mmax = istep
         end do

         if (inverse) a = a / real(n, kind=dp)
      end subroutine fft_radix2_inplace


      pure function fft_fft_real(x, n) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: n
         complex(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: xc(:)
         integer :: i, nn

         if (present(n)) then
            nn = n
         else
            nn = size(x)
         end if
         if (nn < 0) nn = 0
         allocate(y(nn))
         if (nn <= 0) return
         allocate(xc(nn))
         xc = cmplx(0.0_dp, 0.0_dp, kind=dp)
         do i = 1, min(size(x), nn)
            xc(i) = cmplx(x(i), 0.0_dp, kind=dp)
         end do
         if (fft_use_fast .and. fft_is_power_of_two(nn)) then
            y = xc
            call fft_radix2_inplace(y, .false.)
         else
            call fft_dft_forward(xc, y)
         end if
      end function fft_fft_real


      pure function fft_fft_complex(x, n) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: n
         complex(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: xc(:)
         integer :: i, nn

         if (present(n)) then
            nn = n
         else
            nn = size(x)
         end if
         if (nn < 0) nn = 0
         allocate(y(nn))
         if (nn <= 0) return
         allocate(xc(nn))
         xc = cmplx(0.0_dp, 0.0_dp, kind=dp)
         do i = 1, min(size(x), nn)
            xc(i) = x(i)
         end do
         if (fft_use_fast .and. fft_is_power_of_two(nn)) then
            y = xc
            call fft_radix2_inplace(y, .false.)
         else
            call fft_dft_forward(xc, y)
         end if
      end function fft_fft_complex


      pure function fft_ifft(x, n) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: n
         complex(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: xc(:)
         integer :: i, nn

         if (present(n)) then
            nn = n
         else
            nn = size(x)
         end if
         if (nn < 0) nn = 0
         allocate(y(nn))
         if (nn <= 0) return
         allocate(xc(nn))
         xc = cmplx(0.0_dp, 0.0_dp, kind=dp)
         do i = 1, min(size(x), nn)
            xc(i) = x(i)
         end do
         if (fft_use_fast .and. fft_is_power_of_two(nn)) then
            y = xc
            call fft_radix2_inplace(y, .true.)
         else
            call fft_dft_inverse(xc, y)
         end if
      end function fft_ifft


      pure function fft_rfft(x, n) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: n
         complex(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: full(:)
         integer :: nn, m

         full = fft_fft_real(x, n)
         nn = size(full)
         m = nn / 2 + 1
         allocate(y(m))
         y = full(1:m)
      end function fft_rfft


      pure function fft_irfft(x, n) result(y)
         complex(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: n
         real(kind=dp), allocatable :: y(:)
         complex(kind=dp), allocatable :: full(:), ctmp(:)
         integer :: k, m, nn, idx

         if (present(n)) then
            nn = n
         else
            nn = 2 * max(0, size(x) - 1)
         end if
         if (nn < 0) nn = 0
         allocate(full(nn))
         full = cmplx(0.0_dp, 0.0_dp, kind=dp)
         if (nn == 0) then
            allocate(y(0))
            return
         end if
         m = min(size(x), nn / 2 + 1)
         if (m > 0) full(1:m) = x(1:m)
         ! Mirror the positive frequencies 1 .. (nn - 1)/2 (for an even nn,
         ! the Nyquist term nn/2 is its own mirror).
         do k = 2, min(m, (nn + 1) / 2)
            idx = nn - k + 2
            if (1 <= idx .and. idx <= nn) then
               full(idx) = conjg(x(k))
            end if
         end do
         ctmp = fft_ifft(full, nn)
         allocate(y(nn))
         y = real(ctmp, kind=dp)
      end function fft_irfft


      pure function fft_axis_2d(x, dim, n, inverse) result(y)
         ! The complex FFT (inverse if inverse) of each column (dim=1, numpy
         ! axis 0) or row (dim=2, axis 1) of x, cropped or zero-padded to
         ! length n (default: unchanged).
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, intent(in), optional :: n
         logical, intent(in), optional :: inverse
         complex(kind=dp), allocatable :: y(:,:)
         integer :: i, nn
         logical :: inv
         inv = .false.
         if (present(inverse)) inv = inverse
         nn = size(x, dim)
         if (present(n)) nn = max(0, n)
         if (dim == 1) then
            allocate(y(nn, size(x, 2)))
            do i = 1, size(x, 2)
               if (inv) then
                  y(:, i) = fft_ifft(x(:, i), nn)
               else
                  y(:, i) = fft_fft_complex(x(:, i), nn)
               end if
            end do
         else
            allocate(y(size(x, 1), nn))
            do i = 1, size(x, 1)
               if (inv) then
                  y(i, :) = fft_ifft(x(i, :), nn)
               else
                  y(i, :) = fft_fft_complex(x(i, :), nn)
               end if
            end do
         end if
      end function fft_axis_2d

      pure function rfft_axis_2d(x, dim, n) result(y)
         ! np.fft.rfft of each column (dim=1) or row (dim=2) of a real x:
         ! the n/2 + 1 nonnegative-frequency terms (n default size(x, dim)).
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, intent(in), optional :: n
         complex(kind=dp), allocatable :: y(:,:)
         integer :: i, nn
         nn = size(x, dim)
         if (present(n)) nn = max(0, n)
         if (dim == 1) then
            allocate(y(nn / 2 + 1, size(x, 2)))
            do i = 1, size(x, 2)
               y(:, i) = fft_rfft(x(:, i), nn)
            end do
         else
            allocate(y(size(x, 1), nn / 2 + 1))
            do i = 1, size(x, 1)
               y(i, :) = fft_rfft(x(i, :), nn)
            end do
         end if
      end function rfft_axis_2d

      pure function irfft_axis_2d(x, dim, n) result(y)
         ! np.fft.irfft of each column (dim=1) or row (dim=2) of x: real
         ! signals of length n (default 2*(size(x, dim) - 1)).
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in) :: dim
         integer, intent(in), optional :: n
         real(kind=dp), allocatable :: y(:,:)
         integer :: i, nn
         nn = 2 * max(0, size(x, dim) - 1)
         if (present(n)) nn = max(0, n)
         if (dim == 1) then
            allocate(y(nn, size(x, 2)))
            do i = 1, size(x, 2)
               y(:, i) = fft_irfft(x(:, i), nn)
            end do
         else
            allocate(y(size(x, 1), nn))
            do i = 1, size(x, 1)
               y(i, :) = fft_irfft(x(i, :), nn)
            end do
         end if
      end function irfft_axis_2d

      pure function fft2_complex(x, n1, n2) result(y)
         ! np.fft.fft2 (or fftn) of a matrix, each axis cropped or padded to
         ! n1, n2 (numpy's s=).
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: n1, n2
         complex(kind=dp), allocatable :: y(:,:)
         y = fft_axis_2d(fft_axis_2d(x, 2, n2), 1, n1)
      end function fft2_complex

      pure function fft2_real(x, n1, n2) result(y)
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: n1, n2
         complex(kind=dp), allocatable :: y(:,:)
         y = fft2_complex(cmplx(x, 0.0_dp, kind=dp), n1, n2)
      end function fft2_real

      pure function ifft2(x, n1, n2) result(y)
         ! np.fft.ifft2 (or ifftn) of a matrix.
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: n1, n2
         complex(kind=dp), allocatable :: y(:,:)
         y = fft_axis_2d(fft_axis_2d(x, 2, n2, .true.), 1, n1, .true.)
      end function ifft2

      pure function rfft2(x, n1, n2) result(y)
         ! np.fft.rfft2 (or rfftn) of a real matrix: rfft along axis 1, then
         ! fft along axis 0; size(y, 2) = n2/2 + 1.
         real(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: n1, n2
         complex(kind=dp), allocatable :: y(:,:)
         y = fft_axis_2d(rfft_axis_2d(x, 2, n2), 1, n1)
      end function rfft2

      pure function irfft2(x, n1, n2) result(y)
         ! np.fft.irfft2 (or irfftn): the inverse of rfft2; n2 (default
         ! 2*(size(x, 2) - 1)) is the length of the real signal's axis 1.
         complex(kind=dp), intent(in) :: x(:,:)
         integer, intent(in), optional :: n1, n2
         real(kind=dp), allocatable :: y(:,:)
         y = irfft_axis_2d(fft_axis_2d(x, 1, n1, .true.), 2, n2)
      end function irfft2


      pure function fft_fftfreq(n, d) result(f)
         integer, intent(in) :: n
         real(kind=dp), intent(in), optional :: d
         real(kind=dp), allocatable :: f(:)
         integer :: i, k
         real(kind=dp) :: dopt, den

         dopt = 1.0_dp
         if (present(d)) dopt = d
         if (n < 0) then
            allocate(f(0))
            return
         end if
         allocate(f(n))
         if (n == 0) return
         den = real(n, kind=dp) * dopt
         do i = 1, n
            k = i - 1
            if (k <= (n - 1) / 2) then
               f(i) = real(k, kind=dp) / den
            else
               f(i) = real(k - n, kind=dp) / den
            end if
         end do
      end function fft_fftfreq


      pure function fft_rfftfreq(n, d) result(f)
         integer, intent(in) :: n
         real(kind=dp), intent(in), optional :: d
         real(kind=dp), allocatable :: f(:)
         integer :: i, m
         real(kind=dp) :: dopt, den

         dopt = 1.0_dp
         if (present(d)) dopt = d
         if (n < 0) then
            allocate(f(0))
            return
         end if
         m = n / 2 + 1
         allocate(f(m))
         if (m == 0) return
         den = real(max(1, n), kind=dp) * dopt
         do i = 1, m
            f(i) = real(i - 1, kind=dp) / den
         end do
      end function fft_rfftfreq


      pure function itertools_product2_int(a, b) result(out)
         integer, intent(in) :: a(:), b(:)
         integer, allocatable :: out(:,:)
         integer :: i, j, k, na, nb

         na = size(a)
         nb = size(b)
         allocate(out(na * nb, 2))
         k = 0
         do i = 1, na
            do j = 1, nb
               k = k + 1
               out(k, 1) = a(i)
               out(k, 2) = b(j)
            end do
         end do
      end function itertools_product2_int


      pure function itertools_combinations_int(x, r) result(out)
         integer, intent(in) :: x(:), r
         integer, allocatable :: out(:,:)
         integer :: i, j, k, n

         n = size(x)
         if (r /= 2) then
            allocate(out(0, max(1, r)))
            return
         end if
         if (n < 2) then
            allocate(out(0, 2))
            return
         end if
         allocate(out((n * (n - 1)) / 2, 2))
         k = 0
         do i = 1, n - 1
            do j = i + 1, n
               k = k + 1
               out(k, 1) = x(i)
               out(k, 2) = x(j)
            end do
         end do
      end function itertools_combinations_int


      pure function itertools_combinations_wr_int(x, r) result(out)
         integer, intent(in) :: x(:), r
         integer, allocatable :: out(:,:)
         integer :: i, j, k, n

         n = size(x)
         if (r /= 2) then
            allocate(out(0, max(1, r)))
            return
         end if
         if (n <= 0) then
            allocate(out(0, 2))
            return
         end if
         allocate(out((n * (n + 1)) / 2, 2))
         k = 0
         do i = 1, n
            do j = i, n
               k = k + 1
               out(k, 1) = x(i)
               out(k, 2) = x(j)
            end do
         end do
      end function itertools_combinations_wr_int


      pure function itertools_permutations_int(x, r) result(out)
         integer, intent(in) :: x(:), r
         integer, allocatable :: out(:,:)
         integer :: i, j, k, n

         n = size(x)
         if (r /= 2) then
            allocate(out(0, max(1, r)))
            return
         end if
         if (n < 2) then
            allocate(out(0, 2))
            return
         end if
         allocate(out(n * (n - 1), 2))
         k = 0
         do i = 1, n
            do j = 1, n
               if (j == i) cycle
               k = k + 1
               out(k, 1) = x(i)
               out(k, 2) = x(j)
            end do
         end do
      end function itertools_permutations_int


      function file_read(u) result(s)
         integer, intent(in) :: u
         character(len=:), allocatable :: s
         character(len=4096) :: line
         integer :: ios

         s = ""
         do
            read(u, "(A)", iostat=ios) line
            if (ios /= 0) exit
            if (len(s) == 0) then
               s = trim(line)
            else
               s = s // new_line("a") // trim(line)
            end if
         end do
      end function file_read


      pure function py_float(s) result(x)
         character(len=*), intent(in) :: s
         real(kind=dp) :: x
         integer :: ios

         read(s, *, iostat=ios) x
         if (ios /= 0) x = ieee_value(0.0_dp, ieee_quiet_nan)
      end function py_float

      pure function py_int(s) result(x)
         character(len=*), intent(in) :: s
         integer :: x
         integer :: ios

         read(s, *, iostat=ios) x
         if (ios /= 0) x = 0
      end function py_int


      function sys_argv_init() result(argv)
         character(len=:), allocatable :: argv(:)
         integer :: i, narg, l, maxlen

         narg = command_argument_count() + 1
         maxlen = 1
         do i = 0, narg - 1
            call get_command_argument(i, length=l)
            if (l > maxlen) maxlen = l
         end do
         allocate(character(len=maxlen) :: argv(narg))
         do i = 0, narg - 1
            call get_command_argument(i, argv(i + 1))
         end do
      end function sys_argv_init


      pure subroutine sys_argv_delete(argv, idx1)
         character(len=:), allocatable, intent(inout) :: argv(:)
         integer, intent(in) :: idx1
         character(len=:), allocatable :: tmp(:)
         integer :: n

         if (.not. allocated(argv)) return
         n = size(argv)
         if (idx1 < 1 .or. idx1 > n) return
         if (n == 1) then
            deallocate(argv)
            allocate(character(len=1) :: argv(0))
            return
         end if
         allocate(character(len=len(argv)) :: tmp(n - 1))
         if (idx1 > 1) tmp(1:idx1 - 1) = argv(1:idx1 - 1)
         if (idx1 < n) tmp(idx1:n - 1) = argv(idx1 + 1:n)
         call move_alloc(tmp, argv)
      end subroutine sys_argv_delete

      pure function rolling_mean_1d(x, window) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: window
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: mean, sumsq, dev, dev_old
         integer :: n, i, cnt

         n = size(x)
         allocate(y(n))
         y = ieee_value(0.0_dp, ieee_quiet_nan)
         if (window <= 0 .or. window > n) return

         mean = 0.0_dp
         sumsq = 0.0_dp
         cnt = 0
         do i = 1, n
            cnt = cnt + 1
            dev = x(i) - mean
            mean = mean + dev / real(cnt, kind=dp)
            sumsq = sumsq + dev * (x(i) - mean)
            if (cnt > window) then
               cnt = cnt - 1
               dev_old = x(i - window) - mean
               mean = mean - dev_old / real(cnt, kind=dp)
               sumsq = sumsq - dev_old * (x(i - window) - mean)
            end if
            if (cnt >= window) y(i) = mean
         end do
      end function rolling_mean_1d

      pure function rolling_std_1d(x, window, ddof) result(y)
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in) :: window
         integer, intent(in), optional :: ddof
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: mean, sumsq, dev, dev_old
         integer :: n, i, cnt, d

         d = 1
         if (present(ddof)) d = ddof
         n = size(x)
         allocate(y(n))
         y = ieee_value(0.0_dp, ieee_quiet_nan)
         if (window <= 0 .or. window > n) return

         mean = 0.0_dp
         sumsq = 0.0_dp
         cnt = 0
         do i = 1, n
            cnt = cnt + 1
            dev = x(i) - mean
            mean = mean + dev / real(cnt, kind=dp)
            sumsq = sumsq + dev * (x(i) - mean)
            if (cnt > window) then
               cnt = cnt - 1
               dev_old = x(i - window) - mean
               mean = mean - dev_old / real(cnt, kind=dp)
               sumsq = sumsq - dev_old * (x(i - window) - mean)
            end if
            if (cnt >= window .and. cnt > d) then
               y(i) = sqrt(max(sumsq, 0.0_dp) / real(cnt - d, kind=dp))
            end if
         end do
      end function rolling_std_1d

      pure function expanding_mean_1d(x) result(y)
         ! pandas Series/DataFrame.expanding().mean() -- a growing-window
         ! (from row 1 through row i) running mean, one value per row from
         ! the very first row on (min_periods=1, pandas' default) --
         ! Welford's online update, same as rolling_mean_1d but never
         ! downdating (no fixed trailing window to slide out of).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: mean, dev
         integer :: n, i
         n = size(x)
         allocate(y(n))
         mean = 0.0_dp
         do i = 1, n
            dev = x(i) - mean
            mean = mean + dev / real(i, kind=dp)
            y(i) = mean
         end do
      end function expanding_mean_1d

      pure function expanding_std_1d(x, ddof) result(y)
         ! pandas Series/DataFrame.expanding().std() -- growing-window
         ! sample standard deviation (NaN while fewer than ddof+1 rows
         ! have accumulated, pandas' default ddof=1 meaning row 1 alone is
         ! always NaN) -- Welford's online update, same as rolling_std_1d
         ! but never downdating.
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: ddof
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: mean, sumsq, dev
         integer :: n, i, d
         d = 1
         if (present(ddof)) d = ddof
         n = size(x)
         allocate(y(n))
         y = ieee_value(0.0_dp, ieee_quiet_nan)
         mean = 0.0_dp
         sumsq = 0.0_dp
         do i = 1, n
            dev = x(i) - mean
            mean = mean + dev / real(i, kind=dp)
            sumsq = sumsq + dev * (x(i) - mean)
            if (i > d) y(i) = sqrt(max(sumsq, 0.0_dp) / real(i - d, kind=dp))
         end do
      end function expanding_std_1d

      pure function ewm_mean_1d(x, alpha) result(y)
         ! pandas Series/DataFrame.ewm(...).mean() with adjust=True
         ! (pandas' default): y(t) = sum_{j<=t} w_j*x(j) / sum_{j<=t} w_j,
         ! weight w_j = (1-alpha)**(t-j) (most recent observation weighted
         ! 1) -- via the standard num/den recursion num(t) = x(t) +
         ! (1-alpha)*num(t-1), den(t) = 1 + (1-alpha)*den(t-1).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in) :: alpha
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: num, den, r
         integer :: n, i
         n = size(x)
         allocate(y(n))
         if (n == 0) return
         r = 1.0_dp - alpha
         num = x(1)
         den = 1.0_dp
         y(1) = num / den
         do i = 2, n
            num = x(i) + r*num
            den = 1.0_dp + r*den
            y(i) = num / den
         end do
      end function ewm_mean_1d

      pure function ewm_std_1d(x, alpha) result(y)
         ! pandas Series/DataFrame.ewm(...).std() with adjust=True and
         ! bias=False (both pandas' defaults) -- an exponentially
         ! weighted sample standard deviation, Bessel-corrected the same
         ! way a weighted sample variance with "reliability weights" is:
         ! var = var_biased * (sum_w)**2 / ((sum_w)**2 - sum_w2), where
         ! var_biased is the weighted variance about the running weighted
         ! mean. NaN for the first row (a single observation has no
         ! variance) -- pandas' own behavior. Verified by direct
         ! comparison against pandas' own ewm(...).std() output (its
         ! exact recursive update, not independently re-derived).
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), intent(in) :: alpha
         real(kind=dp), allocatable :: y(:)
         real(kind=dp) :: mean, cov, den, den2, r, old_wt, old_mean, denom
         integer :: n, i
         n = size(x)
         allocate(y(n))
         y = ieee_value(0.0_dp, ieee_quiet_nan)
         if (n == 0) return
         r = 1.0_dp - alpha
         mean = x(1)
         cov = 0.0_dp
         den = 1.0_dp
         den2 = 1.0_dp
         do i = 2, n
            old_wt = r*den
            old_mean = mean
            mean = (old_wt*old_mean + x(i)) / (old_wt + 1.0_dp)
            cov = (old_wt*(cov + (old_mean - mean)**2) + (x(i) - mean)**2) / (old_wt + 1.0_dp)
            den = old_wt + 1.0_dp
            den2 = r*r*den2 + 1.0_dp
            denom = den**2 - den2
            if (denom > 0.0_dp) y(i) = sqrt(max(cov*den**2/denom, 0.0_dp))
         end do
      end function ewm_std_1d

      pure function shift_1d(x, periods, fill_value) result(y)
         ! pandas Series.shift(periods[, fill_value]) -- shift values by
         ! `periods` positions (positive shifts toward higher indices,
         ! negative toward lower), filling the vacated positions with
         ! fill_value (NaN by default). Mirrors dataframe_str_index.f90's
         ! shift_str/dataframe_index_date.f90's shift (axis=0 case) for a
         ! plain rank-1 array -- needed for a Series extracted from a
         ! DataFrame column (e.g. `df[name].shift(-1)` inside a `for name
         ! in ...:` loop, where `name` is a runtime column-name
         ! expression, not a whole-DataFrame .shift()).
         real(kind=dp), intent(in) :: x(:)
         integer, intent(in), optional :: periods
         real(kind=dp), intent(in), optional :: fill_value
         real(kind=dp), allocatable :: y(:)
         integer :: p, k, n
         real(kind=dp) :: fill
         p = 1
         if (present(periods)) p = periods
         fill = ieee_value(0.0_dp, ieee_quiet_nan)
         if (present(fill_value)) fill = fill_value
         n = size(x)
         allocate(y(n))
         y = fill
         if (n <= 0 .or. p == 0) then
            if (p == 0) y = x
            return
         end if
         if (p > 0) then
            if (p < n) y(p + 1:n) = x(1:n - p)
         else
            k = -p
            if (k < n) y(1:n - k) = x(k + 1:n)
         end if
      end function shift_1d

      elemental function np_rint(x) result(r)
         ! numpy rint/round/around: the nearest integer, ties to even
         ! (np.round(2.5) == 2.0, np.round(-0.5) == -0.0); ANINT rounds
         ! ties away from zero. np.round(x, d) is np_rint(x*10**d)/10**d.
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: r
         r = anint(x)
         if (abs(x - aint(x)) == 0.5_dp) r = 2.0_dp * anint(0.5_dp * x)
      end function np_rint

      elemental function py_round_ndigits(x, ndigits) result(rnd)
         ! Python 3's round() rounds ties to even ("banker's rounding");
         ! Fortran's NINT/ANINT round ties away from zero instead (e.g.
         ! round(2.5) == 2 and round(-2.5) == -2 in Python, but
         ! NINT(2.5) == 3 and NINT(-2.5) == -3). Adapted from pyccel's
         ! pyc_bankers_round_float
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         real(kind=dp), intent(in) :: x
         integer, intent(in) :: ndigits
         real(kind=dp) :: rnd
         real(kind=dp) :: scaled, diff
         integer(kind=int64) :: n
         scaled = x * 10.0_dp**ndigits
         n = nint(scaled, kind=int64)
         diff = scaled - real(n, kind=dp)
         if (ndigits <= 0 .and. (diff == 0.5_dp .or. diff == -0.5_dp)) then
            n = nint(scaled * 0.5_dp, kind=int64) * 2_int64
         end if
         rnd = real(n, kind=dp) * 10.0_dp**(-ndigits)
      end function py_round_ndigits

      elemental function floor_div_real(x, y) result(q)
         ! Python's // on floats is floor(x / y), returned as a float --
         ! not the same operation as ordinary real division, which is
         ! what plain Fortran "/" gives.
         real(kind=dp), intent(in) :: x, y
         real(kind=dp) :: q
         real(kind=dp) :: md, dv
         ! numpy's floor_divide (npy_divmod), in floats: x // 0 is x / 0,
         ! inf // y is NaN, x // inf is 0 or -1.
         if (y == 0.0_dp) then
            q = x / y
            return
         end if
         if (ieee_is_finite(x) .and. .not. ieee_is_finite(y) .and. .not. ieee_is_nan(y)) then
            md = x
         else
            md = mod(x, y)
         end if
         dv = (x - md) / y
         if (md /= 0.0_dp .and. ((y < 0.0_dp) .neqv. (md < 0.0_dp))) dv = dv - 1.0_dp
         if (dv /= 0.0_dp) then
            q = aint(dv)
            if (q > dv) q = q - 1.0_dp
            if (dv - q > 0.5_dp) q = q + 1.0_dp
         else
            q = sign(0.0_dp, x / y)
         end if
      end function floor_div_real

      pure elemental integer function py_round_int32(x, mold) result(r)
         real(kind=dp), intent(in) :: x
         integer, intent(in), optional :: mold
         integer(kind=int64) :: wide
         wide = py_round_int64(x, 0_int64)
         if (wide > int(huge(r), int64) .or. wide < -int(huge(r), int64)-1_int64) then
            error stop 'round(): result exceeds default integer range; use --int-kind int64'
         end if
         r = int(wide)
      end function py_round_int32

      pure elemental function py_round_int64(x, mold) result(r)
         use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
         real(kind=dp), intent(in) :: x
         integer(kind=int64), intent(in) :: mold
         integer(kind=int64) :: r
         ! REAL(HUGE(int64)) rounds up to 2**63, an exclusive upper bound.
         if (.not. ieee_is_finite(x)) error stop 'round(): non-finite input'
         if (x >= real(huge(r), dp) .or. x < -real(huge(r), dp)) then
            error stop 'round(): result exceeds int64 range'
         end if
         ! Beyond 2**52 every representable double is already integral.
         ! INT also handles -2**63 without a rounding intermediate overflow.
         if (abs(x) >= 4503599627370496.0_dp) then
            r = int(x, kind=int64)
         else
            r = nint(x, kind=int64)
            if (abs(x-real(r, dp)) == 0.5_dp .and. modulo(r, 2_int64) /= 0_int64) then
               r = r - sign(1_int64, r)
            end if
         end if
      end function py_round_int64

      elemental function csign_complex(x) result(s)
         ! Fortran's SIGN intrinsic doesn't accept complex operands at
         ! all, so a literal `sign(1.0_dp, x)` translation of np.sign on
         ! a complex-typed value isn't valid Fortran. Adapted from
         ! pyccel's csign/sign_c64
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         complex(kind=dp), intent(in) :: x
         complex(kind=dp) :: s
         real(kind=dp) :: m
         m = abs(x)
         if (m == 0.0_dp) then
            s = (0.0_dp, 0.0_dp)
         else
            s = x / m
         end if
      end function csign_complex

      pure elemental function py_rshift(x, shift) result(r)
         use, intrinsic :: iso_fortran_env, only: int64
         integer(kind=int64), intent(in) :: x, shift
         integer(kind=int64) :: r
         ! Python right shifts sign-extend; counts beyond the word width
         ! yield 0 or -1. Clamp before narrowing the count to default kind.
         if (shift < 0_int64) error stop 'ValueError: negative shift count'
         r = shifta(x, int(min(shift, 63_int64)))
      end function py_rshift

      elemental integer function floor_div_int(x, y) result(q)
         ! Python // floors toward negative infinity; Fortran's own
         ! integer "/" truncates toward zero instead, giving the wrong
         ! answer whenever x and y have opposite signs and don't divide
         ! evenly (e.g. -7 // 2 == -4 in Python, but -7 / 2 == -3 via
         ! plain Fortran truncation). Formula adapted from pyccel's
         ! pyc_floor_div_i32/pyc_floor_div_i64
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         integer, intent(in) :: x, y
         q = x / y - merge(1, 0, mod(x, y) /= 0 .and. ((x < 0) .neqv. (y < 0)))
      end function floor_div_int

      elemental function log1p(x) result(y)
         ! A literal log(1.0_dp + x) suffers the same catastrophic
         ! cancellation as the naive expm1 formula above, for the same
         ! reason (forming 1 + x first discards x's own low-order bits
         ! once x is small). The C library's own log1p() avoids this.
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y
         interface
            pure function c_log1p(x) bind(c, name="log1p") result(r)
               import :: dp
               real(kind=dp), intent(in), value :: x
               real(kind=dp) :: r
            end function c_log1p
         end interface
         y = c_log1p(x)
      end function log1p

      elemental function expm1(x) result(y)
         ! A literal exp(x) - 1.0_dp loses most significant digits to
         ! catastrophic cancellation once x is small (confirmed against
         ! Python's own math.expm1: at x = 1e-12 the naive formula is
         ! off by a relative error of ~9e-5, and by ~11% at x = 1e-15).
         ! The C library's own expm1() (the same routine Python's
         ! math.expm1/numpy.expm1 are themselves backed by) avoids this.
         ! Adapted from pyccel's own c_expm1 binding
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y
         interface
            pure function c_expm1(x) bind(c, name="expm1") result(r)
               import :: dp
               real(kind=dp), intent(in), value :: x
               real(kind=dp) :: r
            end function c_expm1
         end interface
         y = c_expm1(x)
      end function expm1

      elemental function math_remainder(x, y) result(r)
         ! math.remainder is the IEEE 754 remainder (x - n*y where n =
         ! round(x/y), ties to even) -- distinct from x % y (floors) and
         ! Fortran's own MOD (truncates). Built on the same round-half-
         ! to-even rule as py_round_ndigits, to avoid depending on the
         ! ieee_arithmetic module's own IEEE_REM (which needs its own
         ! per-unit `use` plumbing this project doesn't otherwise carry).
         real(kind=dp), intent(in) :: x, y
         real(kind=dp) :: r
         real(kind=dp) :: q
         integer(kind=int64) :: n
         q = x / y
         n = nint(q, kind=int64)
         if (abs(q - real(n, kind=dp)) == 0.5_dp) then
            n = nint(q * 0.5_dp, kind=int64) * 2_int64
         end if
         r = x - real(n, kind=dp) * y
      end function math_remainder

      elemental function expm1_complex(x) result(y)
         ! np.expm1/cmath-style expm1 on a complex argument. Uses the
         ! standard complex identity exp(a+bi) - 1 = (exp(a)*cos(b) - 1)
         ! + i*exp(a)*sin(b), with exp(a)*cos(b) - 1 rewritten via the
         ! real expm1 (above) plus a half-angle term to avoid the same
         ! cancellation the real case avoids. Adapted from pyccel's own
         ! pyc_expm1_c64
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         complex(kind=dp), intent(in) :: x
         complex(kind=dp) :: y
         real(kind=dp) :: half_sin, re, im
         re = real(x, kind=dp)
         im = aimag(x)
         half_sin = sin(im * 0.5_dp)
         y = cmplx(expm1(re) * cos(im) - 2.0_dp * half_sin * half_sin, exp(re) * sin(im), kind=dp)
      end function expm1_complex

      elemental function log1p_complex(x) result(y)
         complex(kind=dp), intent(in) :: x
         complex(kind=dp) :: y
         y = log(cmplx(1.0_dp, 0.0_dp, kind=dp) + x)
      end function log1p_complex

      pure function complex_amin(arr) result(m)
         complex(kind=dp), intent(in) :: arr(:)
         complex(kind=dp) :: m
         complex(kind=dp) :: a
         integer :: i
         m = arr(1)
         do i = 2, size(arr)
            a = arr(i)
            if (real(a, kind=dp) < real(m, kind=dp) .or. &
                (real(a, kind=dp) == real(m, kind=dp) .and. aimag(a) < aimag(m))) then
               m = a
            end if
         end do
      end function complex_amin

      pure function complex_amax(arr) result(m)
         ! Adapted from pyccel's own amax_4/amax_8
         ! (pyccel/stdlib/math/pyc_math_f90.F90, MIT licensed).
         complex(kind=dp), intent(in) :: arr(:)
         complex(kind=dp) :: m
         complex(kind=dp) :: a
         integer :: i
         m = arr(1)
         do i = 2, size(arr)
            a = arr(i)
            if (real(a, kind=dp) > real(m, kind=dp) .or. &
                (real(a, kind=dp) == real(m, kind=dp) .and. aimag(a) > aimag(m))) then
               m = a
            end if
         end do
      end function complex_amax

! Complex eigensolver adapted from https://jblevins.org/mirror/amiller/dceigv.f90
! Local changes: private python_mod procedures; use the module's dp and
! intrinsic RADIX/EPSILON instead of constants_NSWC; correct DCBABK's
! eigenvector arguments to INTENT(IN OUT), since they are read and updated.
!                     EIGENVALUES AND EIGENVECTORS
!                 OF DOUBLE PRECISION COMPLEX MATRICES

! Adapted from the NSWC Mathematics Library, based upon Eispack routines.
! This version by Alan Miller
! Alan.Miller @ vic.cmis.csiro.au
! http://www.ozemail.com.au/~milleraj

! Latest revision - 26 August 1998




pure FUNCTION dcpabs(x, y) RESULT(fn_val)

REAL (dp), INTENT(IN) :: x
REAL (dp), INTENT(IN) :: y
REAL (dp)             :: fn_val

!     --------------------------------------
!     EVALUATION OF SQRT(X*X + Y*Y)
!     --------------------------------------
REAL (dp) :: a

IF (ABS(x) > ABS(y)) THEN
  a = y / x
  fn_val = ABS(x)*SQRT(1.0_dp + a*a)
  RETURN
END IF

IF (y == 0.0_dp) THEN
  fn_val = 0.0_dp
  RETURN
END IF

a = x / y
fn_val = ABS(y)*SQRT(1.0_dp + a*a)
RETURN

END FUNCTION dcpabs



pure SUBROUTINE dcsqrt (z, w)

REAL (dp), INTENT(IN)   :: z(:)
REAL (dp), INTENT(OUT)  :: w(:)

! ----------------------------------------------------------------------
!          W = SQRT(Z) FOR THE COMPLEX NUMBER Z

!                       -----------

!   Z AND W ARE INTERPRETED AS COMPLEX NUMBERS.
!   IT IS ASSUMED THAT Z(1) AND Z(2) ARE THE REAL AND IMAGINARY PARTS OF
!   THE COMPLEX NUMBER Z, AND THAT W(1) AND W(2) ARE THE REAL AND IMAGINARY
!   PARTS OF W.
! ----------------------------------------------------------------------
REAL (dp)            :: x, y, r
REAL (dp), PARAMETER :: half = 0.5_dp

x = z(1)
y = z(2)
IF (x < 0.0_dp) THEN
  GO TO 30
ELSE IF (x > 0.0_dp) THEN
  GO TO 20
END IF

IF (y /= 0.0_dp) GO TO 11
w(1) = 0.0_dp
w(2) = 0.0_dp
RETURN

11 w(1) = SQRT(half * ABS(y))
w(2) = SIGN(w(1), y)
RETURN

20 IF (y /= 0.0_dp) GO TO 21
w(1) = SQRT(x)
w(2) = 0.0_dp
RETURN

21 r = dcpabs(x,y)
w(1) = SQRT(half * (r + x))
w(2) = half * y / w(1)
RETURN

30 IF (y /= 0.0_dp) GO TO 31
w(1) = 0.0_dp
w(2) = SQRT(ABS(x))
RETURN

31 r = dcpabs(x, y)
w(2) = SQRT(half * (r - x))
w(2) = SIGN(w(2), y)
w(1) = half * y / w(2)
RETURN
END SUBROUTINE dcsqrt



pure SUBROUTINE dceigv (ibal, ar, ai, n, wr, wi, zr, zi, ierr)
!-----------------------------------------------------------------------
!           EIGENVALUES AND EIGENVECTORS OF COMPLEX MATRICES
!
!  ibal = .TRUE. if balancing is required
!  ar, ai = the real and imaginary parts of the matrix (destroyed)
!  wr, wi = the real and imaginary parts of the eigenvalues
!  zr, zi = the real and imaginary parts of the eigenvectors
!
!-----------------------------------------------------------------------

LOGICAL, INTENT(IN)        :: ibal
REAL (dp), INTENT(IN OUT)  :: ar(:,:)     ! ar(ka,n)
REAL (dp), INTENT(IN OUT)  :: ai(:,:)     ! ai(ka,n)
INTEGER, INTENT(IN)        :: n
REAL (dp), INTENT(OUT)     :: wr(:)
REAL (dp), INTENT(OUT)     :: wi(:)
REAL (dp), INTENT(OUT)     :: zr(:,:)     ! zr(ka,n)
REAL (dp), INTENT(OUT)     :: zi(:,:)     ! zi(ka,n)
INTEGER, INTENT(OUT)       :: ierr

! Local variables
REAL (dp) :: ortr(n), orti(n), scale(n)
INTEGER   :: high, low

low = 1
high = n
IF (ibal) CALL dcbal(n, ar, ai, low, high, scale)
CALL dcorth(n, low, high, ar, ai, ortr, orti)
CALL dcmqr2(n, low, high, ortr, orti, ar, ai, wr, wi, zr, zi, ierr)
IF (ierr /= 0) RETURN
IF (ibal) CALL dcbabk(n, low, high, scale, n, zr, zi)
RETURN
END SUBROUTINE dceigv



pure SUBROUTINE dcbal(n, ar, ai, low, igh, scale)

INTEGER, INTENT(IN)        :: n
REAL (dp), INTENT(IN OUT)  :: ar(:,:)      ! ar(nm,n)
REAL (dp), INTENT(IN OUT)  :: ai(:,:)      ! ai(nm,n)
INTEGER, INTENT(OUT)       :: low
INTEGER, INTENT(OUT)       :: igh
REAL (dp), INTENT(OUT)     :: scale(:)

!-----------------------------------------------------------------------

!     THIS SUBROUTINE IS A TRANSLATION OF THE ALGOL PROCEDURE
!     CBALANCE, WHICH IS A COMPLEX VERSION OF BALANCE,
!     NUM. MATH. 13, 293-304(1969) BY PARLETT AND REINSCH.
!     HANDBOOK FOR AUTO. COMP., VOL.II-LINEAR ALGEBRA, 315-326(1971).

!     DCBAL BALANCES A COMPLEX MATRIX AND
!     ISOLATES EIGENVALUES WHENEVER POSSIBLE.

!     ON INPUT-

!        N IS THE ORDER OF THE MATRIX,

!        AR AND AI CONTAIN THE REAL AND IMAGINARY PARTS,
!          RESPECTIVELY, OF THE COMPLEX MATRIX TO BE BALANCED.

!     ON OUTPUT-

!        AR AND AI CONTAIN THE REAL AND IMAGINARY PARTS,
!          RESPECTIVELY, OF THE BALANCED MATRIX,

!        LOW AND IGH ARE TWO INTEGERS SUCH THAT AR(I,J) AND AI(I,J)
!          ARE EQUAL TO ZERO IF
!           (1) I IS GREATER THAN J AND
!           (2) J=1,...,LOW-1 OR I=IGH+1,...,N,

!        SCALE CONTAINS INFORMATION DETERMINING THE
!           PERMUTATIONS AND SCALING FACTORS USED.

!     SUPPOSE THAT THE PRINCIPAL SUBMATRIX IN ROWS LOW THROUGH IGH
!     HAS BEEN BALANCED, THAT P(J) DENOTES THE INDEX INTERCHANGED
!     WITH J DURING THE PERMUTATION STEP, AND THAT THE ELEMENTS
!     OF THE DIAGONAL MATRIX USED ARE DENOTED BY D(I,J).  THEN
!        SCALE(J) = P(J),    FOR J = 1,...,LOW-1
!                 = D(J,J)       J = LOW,...,IGH
!                 = P(J)         J = IGH+1,...,N.
!     THE ORDER IN WHICH THE INTERCHANGES ARE MADE IS N TO IGH+1,
!     THEN 1 TO LOW-1.

!     NOTE THAT 1 IS RETURNED FOR IGH IF IGH IS ZERO FORMALLY.

!     THE ALGOL PROCEDURE EXC CONTAINED IN CBALANCE APPEARS IN DCBAL IN LINE.
!     (NOTE THAT THE ALGOL ROLES OF IDENTIFIERS K, L HAVE BEEN REVERSED.)

!-----------------------------------------------------------------------
INTEGER   :: i, j, k, l, m, iexc
REAL (dp) :: c, f, g, r, s, b2, machine_radix
LOGICAL   :: noconv

!     ********** RADIX IS A MACHINE DEPENDENT PARAMETER SPECIFYING
!                THE BASE OF THE MACHINE FLOATING POINT REPRESENTATION.

machine_radix = real(radix(1.0_dp), dp)

!                **********

b2 = machine_radix * machine_radix
k = 1
l = n
GO TO 100
!     ********** IN-LINE PROCEDURE FOR ROW AND COLUMN EXCHANGE **********
20 scale(m) = j
IF (j == m) GO TO 50

DO i = 1, l
  f = ar(i,j)
  ar(i,j) = ar(i,m)
  ar(i,m) = f
  f = ai(i,j)
  ai(i,j) = ai(i,m)
  ai(i,m) = f
END DO

DO i = k, n
  f = ar(j,i)
  ar(j,i) = ar(m,i)
  ar(m,i) = f
  f = ai(j,i)
  ai(j,i) = ai(m,i)
  ai(m,i) = f
END DO

50 IF (iexc == 2) GO TO 130
!  ******** SEARCH FOR ROWS ISOLATING AN EIGENVALUE AND PUSH THEM DOWN *******
IF (l == 1) GO TO 280
l = l - 1
!     ********** FOR J=L STEP -1 UNTIL 1 DO -- **********
100 loop120: DO j = l, 1, -1

  DO i = 1, l
    IF (i == j) CYCLE
    IF (ar(j,i) /= 0.0_dp .OR. ai(j,i) /= 0.0_dp) CYCLE loop120
  END DO

  m = l
  iexc = 1
  GO TO 20
END DO loop120

GO TO 140
!     ********** SEARCH FOR COLUMNS ISOLATING AN EIGENVALUE
!                AND PUSH THEM LEFT **********
130 k = k + 1

140 loop170: DO j = k, l

  DO i = k, l
    IF (i == j) CYCLE
    IF (ar(i,j) /= 0.0_dp .OR. ai(i,j) /= 0.0_dp) CYCLE loop170
  END DO

  m = k
  iexc = 2
  GO TO 20
END DO loop170
!     ********** NOW BALANCE THE SUBMATRIX IN ROWS K TO L **********
scale(k:l) = 1.0_dp
!     ********** ITERATIVE LOOP FOR NORM REDUCTION **********
190 noconv = .false.

DO i = k, l
  c = 0.0_dp
  r = 0.0_dp

  DO j = k, l
    IF (j == i) CYCLE
    c = c + ABS(ar(j,i)) + ABS(ai(j,i))
    r = r + ABS(ar(i,j)) + ABS(ai(i,j))
  END DO
!     ********** GUARD AGAINST ZERO C OR R DUE TO UNDERFLOW **********
  IF (c == 0.0_dp .OR. r == 0.0_dp) CYCLE
  g = r / machine_radix
  f = 1.0_dp
  s = c + r
  210 IF (c >= g) GO TO 220
  f = f * machine_radix
  c = c * b2
  GO TO 210
  220 g = r * machine_radix
  230 IF (c < g) GO TO 240
  f = f / machine_radix
  c = c / b2
  GO TO 230
!     ********** NOW BALANCE **********
  240 IF ((c + r) / f >= 0.95D0 * s) CYCLE
  g = 1.0_dp / f
  scale(i) = scale(i) * f
  noconv = .true.

  DO j = k, n
    ar(i,j) = ar(i,j) * g
    ai(i,j) = ai(i,j) * g
  END DO

  DO j = 1, l
    ar(j,i) = ar(j,i) * f
    ai(j,i) = ai(j,i) * f
  END DO

END DO

IF (noconv) GO TO 190

280 low = k
igh = l
RETURN
!     ********** LAST CARD OF DCBAL **********
END SUBROUTINE dcbal



pure SUBROUTINE dcorth(n, low, igh, ar, ai, ortr, orti)

INTEGER, INTENT(IN)       :: n
INTEGER, INTENT(IN)       :: low
INTEGER, INTENT(IN)       :: igh
REAL (dp), INTENT(IN OUT) :: ar(:,:)      ! ar(nm,n)
REAL (dp), INTENT(IN OUT) :: ai(:,:)      ! ai(nm,n)
REAL (dp), INTENT(OUT)    :: ortr(:)      ! ortr(igh)
REAL (dp), INTENT(OUT)    :: orti(:)      ! orti(igh)
!-----------------------------------------------------------------------

!     THIS SUBROUTINE IS A TRANSLATION OF A COMPLEX ANALOGUE OF THE ALGOL
!     PROCEDURE ORTHES, NUM. MATH. 12, 349-368(1968) BY MARTIN AND WILKINSON.
!     HANDBOOK FOR AUTO. COMP., VOL.II-LINEAR ALGEBRA, 339-358(1971).

!     GIVEN A COMPLEX MATRIX, DCORTH REDUCES A SUBMATRIX SITUATED IN ROWS
!     AND COLUMNS LOW THROUGH IGH TO UPPER HESSENBERG FORM BY UNITARY
!     SIMILARITY TRANSFORMATIONS.

!     ON INPUT-

!        N IS THE ORDER OF THE MATRIX,

!        LOW AND IGH ARE INTEGERS DETERMINED BY THE BALANCING SUBROUTINE DCBAL.
!          IF DCBAL HAS NOT BEEN USED, SET LOW=1, IGH=N,

!        AR AND AI CONTAIN THE REAL AND IMAGINARY PARTS,
!          RESPECTIVELY, OF THE COMPLEX INPUT MATRIX.

!     ON OUTPUT-

!        AR AND AI CONTAIN THE REAL AND IMAGINARY PARTS, RESPECTIVELY, OF THE
!          HESSENBERG MATRIX.  INFORMATION ABOUT THE UNITARY TRANSFORMATIONS
!          USED IN THE REDUCTION IS STORED IN THE REMAINING TRIANGLES UNDER
!          THE HESSENBERG MATRIX,

!        ORTR AND ORTI CONTAIN FURTHER INFORMATION ABOUT THE
!          TRANSFORMATIONS.  ONLY ELEMENTS LOW THROUGH IGH ARE USED.

!-----------------------------------------------------------------------

INTEGER   :: i, j, m, la, kp1
REAL (dp) :: f, g, h, fi, fr, scale

la = igh - 1
kp1 = low + 1
IF (la < kp1) GO TO 200

DO m = kp1, la
  h = 0.0_dp
  ortr(m) = 0.0_dp
  orti(m) = 0.0_dp
  scale = 0.0_dp
!     ********** SCALE COLUMN (ALGOL TOL THEN NOT NEEDED) **********
  DO i = m, igh
    scale = scale + ABS(ar(i,m-1)) + ABS(ai(i,m-1))
  END DO

  IF (scale == 0.0_dp) CYCLE
!     ********** FOR I=IGH STEP -1 UNTIL M DO -- **********
  DO i = igh, m, -1
    ortr(i) = ar(i,m-1) / scale
    orti(i) = ai(i,m-1) / scale
    h = h + ortr(i) * ortr(i) + orti(i) * orti(i)
  END DO

  g = SQRT(h)
  f = dcpabs(ortr(m), orti(m))
  IF (f == 0.0_dp) GO TO 103
  h = h + f * g
  g = g / f
  ortr(m) = (1.0_dp + g) * ortr(m)
  orti(m) = (1.0_dp + g) * orti(m)
  GO TO 105

  103 ortr(m) = g
  ar(m,m-1) = scale
!     ********** FORM (I-(U*UT)/H) * A **********
  105 DO j = m, n
    fr = 0.0_dp
    fi = 0.0_dp
!     ********** FOR I=IGH STEP -1 UNTIL M DO -- **********
    DO i = igh, m, -1
      fr = fr + ortr(i) * ar(i,j) + orti(i) * ai(i,j)
      fi = fi + ortr(i) * ai(i,j) - orti(i) * ar(i,j)
    END DO

    fr = fr / h
    fi = fi / h

    DO i = m, igh
      ar(i,j) = ar(i,j) - fr * ortr(i) + fi * orti(i)
      ai(i,j) = ai(i,j) - fr * orti(i) - fi * ortr(i)
    END DO

  END DO
!     ********** FORM (I-(U*UT)/H)*A*(I-(U*UT)/H) **********
  DO i = 1, igh
    fr = 0.0_dp
    fi = 0.0_dp
!     ********** FOR J=IGH STEP -1 UNTIL M DO -- **********
    DO j = igh, m, -1
      fr = fr + ortr(j) * ar(i,j) - orti(j) * ai(i,j)
      fi = fi + ortr(j) * ai(i,j) + orti(j) * ar(i,j)
    END DO

    fr = fr / h
    fi = fi / h

    DO j = m, igh
      ar(i,j) = ar(i,j) - fr * ortr(j) - fi * orti(j)
      ai(i,j) = ai(i,j) + fr * orti(j) - fi * ortr(j)
    END DO

  END DO

  ortr(m) = scale * ortr(m)
  orti(m) = scale * orti(m)
  ar(m,m-1) = -g * ar(m,m-1)
  ai(m,m-1) = -g * ai(m,m-1)
END DO

200 RETURN
!     ********** LAST CARD OF DCORTH **********
END SUBROUTINE dcorth



pure SUBROUTINE dcbabk (n, low, igh, scale, m, zr, zi)

INTEGER, INTENT(IN)     :: n
INTEGER, INTENT(IN)     :: low
INTEGER, INTENT(IN)     :: igh
REAL (dp), INTENT(IN)   :: scale(:)
INTEGER, INTENT(IN)     :: m
REAL (dp), INTENT(IN OUT) :: zr(:,:)    ! zr(nm,m)
REAL (dp), INTENT(IN OUT) :: zi(:,:)    ! zi(nm,m)

!-----------------------------------------------------------------------

!     THIS SUBROUTINE IS A TRANSLATION OF THE ALGOL PROCEDURE
!     CBABK2, WHICH IS A COMPLEX VERSION OF BALBAK,
!     NUM. MATH. 13, 293-304(1969) BY PARLETT AND REINSCH.
!     HANDBOOK FOR AUTO. COMP., VOL.II-LINEAR ALGEBRA, 315-326(1971).

!     THIS SUBROUTINE FORMS THE EIGENVECTORS OF A REAL (dp)
!     COMPLEX MATRIX BY BACK TRANSFORMING THOSE OF THE CORRESPONDING
!     BALANCED MATRIX DETERMINED BY DCBAL.

!     ON INPUT-

!        N IS THE ORDER OF THE MATRIX,

!        LOW AND IGH ARE INTEGERS DETERMINED BY DCBAL,

!        SCALE CONTAINS INFORMATION DETERMINING THE PERMUTATIONS
!          AND SCALING FACTORS USED BY DCBAL,

!        M IS THE NUMBER OF EIGENVECTORS TO BE BACK TRANSFORMED,

!        ZR AND ZI CONTAIN THE REAL AND IMAGINARY PARTS, RESPECTIVELY, OF THE
!          EIGENVECTORS TO BE BACK TRANSFORMED IN THEIR FIRST M COLUMNS.

!     ON OUTPUT-

!        ZR AND ZI CONTAIN THE REAL AND IMAGINARY PARTS, RESPECTIVELY, OF THE
!          TRANSFORMED EIGENVECTORS IN THEIR FIRST M COLUMNS.

!-----------------------------------------------------------------------
INTEGER   :: i, j, k, ii
REAL (dp) :: s

IF (m == 0) GO TO 200
IF (igh == low) GO TO 120

DO i = low, igh
  s = scale(i)
!     ********** LEFT HAND EIGENVECTORS ARE BACK TRANSFORMED
!                IF THE FOREGOING STATEMENT IS REPLACED BY
!                S=1.0/SCALE(I). **********
  DO j = 1, m
    zr(i,j) = zr(i,j) * s
    zi(i,j) = zi(i,j) * s
  END DO

END DO

!     ********** FOR I=LOW-1 STEP -1 UNTIL 1,
!                IGH+1 STEP 1 UNTIL N DO -- **********
120 DO ii = 1, n
  i = ii
  IF (i >= low .AND. i <= igh) CYCLE
  IF (i < low) i = low - ii
  k = scale(i)
  IF (k == i) CYCLE

  DO j = 1, m
    s = zr(i,j)
    zr(i,j) = zr(k,j)
    zr(k,j) = s
    s = zi(i,j)
    zi(i,j) = zi(k,j)
    zi(k,j) = s
  END DO

END DO

200 RETURN
!     ********** LAST CARD OF DCBABK **********
END SUBROUTINE dcbabk



pure SUBROUTINE dcmqr2 (n, low, igh, ortr, orti, hr, hi, wr, wi, zr, zi, ierr)

INTEGER, INTENT(IN)       :: n
INTEGER, INTENT(IN)       :: low
INTEGER, INTENT(IN)       :: igh
REAL (dp), INTENT(IN OUT) :: ortr(:)
REAL (dp), INTENT(IN OUT) :: orti(:)
REAL (dp), INTENT(IN OUT) :: hr(:,:)      ! hr(nm,n)
REAL (dp), INTENT(IN OUT) :: hi(:,:)      ! hi(nm,n)
REAL (dp), INTENT(OUT)    :: wr(:)
REAL (dp), INTENT(OUT)    :: wi(:)
REAL (dp), INTENT(OUT)    :: zr(:,:)      ! zr(nm,n)
REAL (dp), INTENT(OUT)    :: zi(:,:)      ! zi(nm,n)
INTEGER, INTENT(OUT)      :: ierr

!-----------------------------------------------------------------------

!   THIS SUBROUTINE IS A TRANSLATION OF A UNITARY ANALOGUE OF THE ALGOL
!   PROCEDURE  COMLR2, NUM. MATH. 16, 181-204(1970) BY PETERS AND WILKINSON.
!   HANDBOOK FOR AUTO. COMP., VOL.II-LINEAR ALGEBRA, 372-395(1971).
!   THE UNITARY ANALOGUE SUBSTITUTES THE QR ALGORITHM OF FRANCIS
!   (COMP. JOUR. 4, 332-345(1962)) FOR THE LR ALGORITHM.

!   THIS SUBROUTINE FINDS THE EIGENVALUES AND EIGENVECTORS OF A REAL (dp)
!   COMPLEX UPPER HESSENBERG MATRIX BY THE QR METHOD.  THE EIGENVECTORS OF A
!   COMPLEX GENERAL MATRIX CAN ALSO BE FOUND IF DCORTH HAS BEEN USED TO
!   REDUCE THIS GENERAL MATRIX TO HESSENBERG FORM.

!   ON INPUT-

!      N IS THE ORDER OF THE MATRIX,

!      LOW AND IGH ARE INTEGERS DETERMINED BY THE BALANCING SUBROUTINE DCBAL.
!        IF DCBAL HAS NOT BEEN USED, SET LOW=1, IGH=N,

!      ORTR AND ORTI CONTAIN INFORMATION ABOUT THE UNITARY TRANSFORMATIONS
!        USED IN THE REDUCTION BY DCORTH, IF PERFORMED.
!        ONLY ELEMENTS LOW THROUGH IGH ARE USED.  IF THE EIGENVECTORS
!        OF THE HESSENBERG MATRIX ARE DESIRED, SET ORTR(J) AND
!        ORTI(J) TO 0.0 FOR THESE ELEMENTS,

!      HR AND HI CONTAIN THE REAL AND IMAGINARY PARTS,
!        RESPECTIVELY, OF THE COMPLEX UPPER HESSENBERG MATRIX.
!        THEIR LOWER TRIANGLES BELOW THE SUBDIAGONAL CONTAIN FURTHER
!        INFORMATION ABOUT THE TRANSFORMATIONS WHICH WERE USED IN THE
!        REDUCTION BY DCORTH, IF PERFORMED.  IF THE EIGENVECTORS OF THE
!        HESSENBERG MATRIX ARE DESIRED, THESE ELEMENTS MAY BE ARBITRARY.

!   ON OUTPUT-

!      ORTR, ORTI, AND THE UPPER HESSENBERG PORTIONS OF HR AND HI
!        HAVE BEEN DESTROYED,

!      WR AND WI CONTAIN THE REAL AND IMAGINARY PARTS, RESPECTIVELY, OF THE
!        EIGENVALUES.  IF AN ERROR EXIT IS MADE, THE EIGENVALUES SHOULD
!        BE CORRECT FOR INDICES IERR+1,...,N,

!      ZR AND ZI CONTAIN THE REAL AND IMAGINARY PARTS, RESPECTIVELY, OF THE
!        EIGENVECTORS.  THE EIGENVECTORS ARE UNNORMALIZED.
!        IF AN ERROR EXIT IS MADE, NONE OF THE EIGENVECTORS HAS BEEN FOUND,

!      IERR IS SET TO
!        ZERO   FOR NORMAL RETURN,
!        J      IF THE J-TH EIGENVALUE HAS NOT BEEN DETERMINED AFTER
!               50 ITERATIONS.

!-----------------------------------------------------------------------
INTEGER   :: en, enm1, i, j, k, l, m, ll, ip1, its, lp1, iend
REAL (dp) :: si, sr, ti, tr, xi, xr, yi, yr, zzi, zzr, norm, machep
REAL (dp) :: r2, w(2), z(2)

!     ********** MACHEP IS A MACHINE DEPENDENT PARAMETER SPECIFYING
!                THE RELATIVE PRECISION OF FLOATING POINT ARITHMETIC.

machep = epsilon(1.0_dp)

!                **********

ierr = 0
!     ********** INITIALIZE EIGENVECTOR MATRIX **********
DO i = 1, n

  DO j = 1, n
    zr(i,j) = 0.0_dp
    zi(i,j) = 0.0_dp
    IF (i == j) zr(i,j) = 1.0_dp
  END DO
END DO
!     ********** FORM THE MATRIX OF ACCUMULATED TRANSFORMATIONS
!                FROM THE INFORMATION LEFT BY DCORTH **********
iend = igh - low - 1
IF (iend < 0) THEN
  GO TO 180
ELSE IF (iend == 0) THEN
  GO TO 150
END IF
!     ********** FOR I=IGH-1 STEP -1 UNTIL LOW+1 DO -- **********
DO i = igh-1, low+1, -1
  IF (ortr(i) == 0.0_dp .AND. orti(i) == 0.0_dp) CYCLE
  IF (hr(i,i-1) == 0.0_dp .AND. hi(i,i-1) == 0.0_dp) CYCLE
!     ********** NORM BELOW IS NEGATIVE OF H FORMED IN DCORTH **********
  norm = hr(i,i-1) * ortr(i) + hi(i,i-1) * orti(i)
  ip1 = i + 1

  DO k = ip1, igh
    ortr(k) = hr(k,i-1)
    orti(k) = hi(k,i-1)
  END DO

  DO j = i, igh
    sr = 0.0_dp
    si = 0.0_dp

    DO k = i, igh
      sr = sr + ortr(k) * zr(k,j) + orti(k) * zi(k,j)
      si = si + ortr(k) * zi(k,j) - orti(k) * zr(k,j)
    END DO

    sr = sr / norm
    si = si / norm

    DO k = i, igh
      zr(k,j) = zr(k,j) + sr * ortr(k) - si * orti(k)
      zi(k,j) = zi(k,j) + sr * orti(k) + si * ortr(k)
    END DO

  END DO

END DO
!     ********** CREATE REAL SUBDIAGONAL ELEMENTS **********
150 l = low + 1

DO i = l, igh
  ll = MIN(i+1, igh)
  IF (hi(i,i-1) == 0.0_dp) CYCLE
  norm = dcpabs(hr(i,i-1), hi(i,i-1))
  yr = hr(i,i-1) / norm
  yi = hi(i,i-1) / norm
  hr(i,i-1) = norm
  hi(i,i-1) = 0.0_dp

  DO j = i, n
    si = yr * hi(i,j) - yi * hr(i,j)
    hr(i,j) = yr * hr(i,j) + yi * hi(i,j)
    hi(i,j) = si
  END DO

  DO j = 1, ll
    si = yr * hi(j,i) + yi * hr(j,i)
    hr(j,i) = yr * hr(j,i) - yi * hi(j,i)
    hi(j,i) = si
  END DO

  DO j = low, igh
    si = yr * zi(j,i) + yi * zr(j,i)
    zr(j,i) = yr * zr(j,i) - yi * zi(j,i)
    zi(j,i) = si
  END DO

END DO
!     ********** STORE ROOTS ISOLATED BY DCBAL **********
180 DO i = 1, n
  IF (i >= low .AND. i <= igh) CYCLE
  wr(i) = hr(i,i)
  wi(i) = hi(i,i)
END DO

en = igh
tr = 0.0_dp
ti = 0.0_dp
!     ********** SEARCH FOR NEXT EIGENVALUE **********
220 IF (en < low) GO TO 680
its = 0
enm1 = en - 1
!     ********** LOOK FOR SINGLE SMALL SUB-DIAGONAL ELEMENT
!                FOR L=EN STEP -1 UNTIL LOW DO -- **********
240 DO ll = low, en
  l = en + low - ll
  IF (l == low) EXIT
  IF (ABS(hr(l,l-1)) <= machep * (ABS(hr(l-1,l-1)) + ABS(hi(l-1,l-1))  &
      + ABS(hr(l,l)) + ABS(hi(l,l)))) EXIT
END DO
!     ********** FORM SHIFT **********
IF (l == en) GO TO 660
IF (its == 50) GO TO 1000
IF (its == 10 .OR. its == 20 .OR. its == 30) GO TO 320
sr = hr(en,en)
si = hi(en,en)
xr = hr(enm1,en) * hr(en,enm1)
xi = hi(enm1,en) * hr(en,enm1)
IF (xr == 0.0_dp .AND. xi == 0.0_dp) GO TO 340
yr = (hr(enm1,enm1) - sr) / 2.0_dp
yi = (hi(enm1,enm1) - si) / 2.0_dp
z(1) = yr*yr - yi*yi + xr
z(2) = 2.0_dp*yr*yi + xi
CALL dcsqrt(z, w)
zzr = w(1)
zzi = w(2)
IF (yr * zzr + yi * zzi >= 0.0_dp) GO TO 310
zzr = -zzr
zzi = -zzi
310 z(1) = yr + zzr
z(2) = yi + zzi
r2 = z(1)**2 + z(2)**2
sr = sr - (xr*z(1) + xi*z(2))/r2
si = si - (xi*z(1) - xr*z(2))/r2
GO TO 340
!     ********** FORM EXCEPTIONAL SHIFT **********
320 sr = ABS(hr(en,enm1)) + ABS(hr(enm1,en-2))
si = 0.0_dp

340 DO i = low, en
  hr(i,i) = hr(i,i) - sr
  hi(i,i) = hi(i,i) - si
END DO

tr = tr + sr
ti = ti + si
its = its + 1
!     ********** REDUCE TO TRIANGLE (ROWS) **********
lp1 = l + 1

DO i = lp1, en
  sr = hr(i,i-1)
  hr(i,i-1) = 0.0_dp
  norm = SQRT(hr(i-1,i-1)*hr(i-1,i-1) + hi(i-1,i-1)*hi(i-1,i-1) + sr*sr)
  xr = hr(i-1,i-1) / norm
  wr(i-1) = xr
  xi = hi(i-1,i-1) / norm
  wi(i-1) = xi
  hr(i-1,i-1) = norm
  hi(i-1,i-1) = 0.0_dp
  hi(i,i-1) = sr / norm

  DO j = i, n
    yr = hr(i-1,j)
    yi = hi(i-1,j)
    zzr = hr(i,j)
    zzi = hi(i,j)
    hr(i-1,j) = xr * yr + xi * yi + hi(i,i-1) * zzr
    hi(i-1,j) = xr * yi - xi * yr + hi(i,i-1) * zzi
    hr(i,j) = xr * zzr - xi * zzi - hi(i,i-1) * yr
    hi(i,j) = xr * zzi + xi * zzr - hi(i,i-1) * yi
  END DO

END DO

si = hi(en,en)
IF (si == 0.0_dp) GO TO 540
norm = dcpabs(hr(en, en), si)
sr = hr(en,en) / norm
si = si / norm
hr(en,en) = norm
hi(en,en) = 0.0_dp
IF (en == n) GO TO 540
ip1 = en + 1

DO j = ip1, n
  yr = hr(en,j)
  yi = hi(en,j)
  hr(en,j) = sr * yr + si * yi
  hi(en,j) = sr * yi - si * yr
END DO
!     ********** INVERSE OPERATION (COLUMNS) **********
540 DO j = lp1, en
  xr = wr(j-1)
  xi = wi(j-1)

  DO i = 1, j
    yr = hr(i,j-1)
    yi = 0.0_dp
    zzr = hr(i,j)
    zzi = hi(i,j)
    IF (i == j) GO TO 560
    yi = hi(i,j-1)
    hi(i,j-1) = xr * yi + xi * yr + hi(j,j-1) * zzi
    560 hr(i,j-1) = xr * yr - xi * yi + hi(j,j-1) * zzr
    hr(i,j) = xr * zzr + xi * zzi - hi(j,j-1) * yr
    hi(i,j) = xr * zzi - xi * zzr - hi(j,j-1) * yi
  END DO

  DO i = low, igh
    yr = zr(i,j-1)
    yi = zi(i,j-1)
    zzr = zr(i,j)
    zzi = zi(i,j)
    zr(i,j-1) = xr * yr - xi * yi + hi(j,j-1) * zzr
    zi(i,j-1) = xr * yi + xi * yr + hi(j,j-1) * zzi
    zr(i,j) = xr * zzr + xi * zzi - hi(j,j-1) * yr
    zi(i,j) = xr * zzi - xi * zzr - hi(j,j-1) * yi
  END DO

END DO

IF (si == 0.0_dp) GO TO 240

DO i = 1, en
  yr = hr(i,en)
  yi = hi(i,en)
  hr(i,en) = sr * yr - si * yi
  hi(i,en) = sr * yi + si * yr
END DO

DO i = low, igh
  yr = zr(i,en)
  yi = zi(i,en)
  zr(i,en) = sr * yr - si * yi
  zi(i,en) = sr * yi + si * yr
END DO

GO TO 240
!     ********** A ROOT FOUND **********
660 hr(en,en) = hr(en,en) + tr
wr(en) = hr(en,en)
hi(en,en) = hi(en,en) + ti
wi(en) = hi(en,en)
en = enm1
GO TO 220
!     ********** ALL ROOTS FOUND.  BACKSUBSTITUTE TO FIND
!                VECTORS OF UPPER TRIANGULAR FORM **********
680 norm = 0.0_dp

DO i = 1, n
  DO j = i, n
    norm = norm + ABS(hr(i,j)) + ABS(hi(i,j))
  END DO
END DO

IF (n == 1 .OR. norm == 0.0_dp) GO TO 1001
!     ********** FOR EN=N STEP -1 UNTIL 2 DO -- **********
DO en = n, 2, -1
  xr = wr(en)
  xi = wi(en)
  enm1 = en - 1
!     ********** FOR I=EN-1 STEP -1 UNTIL 1 DO -- **********
  DO i = enm1, 1, -1
    zzr = hr(i,en)
    zzi = hi(i,en)
    IF (i == enm1) GO TO 760
    ip1 = i + 1

    DO j = ip1, enm1
      zzr = zzr + hr(i,j) * hr(j,en) - hi(i,j) * hi(j,en)
      zzi = zzi + hr(i,j) * hi(j,en) + hi(i,j) * hr(j,en)
    END DO

    760 yr = xr - wr(i)
    yi = xi - wi(i)
    IF (yr == 0.0_dp .AND. yi == 0.0_dp) yr = machep * norm
    r2 = yr*yr + yi*yi
    hr(i,en) = (zzr*yr + zzi*yi) / r2
    hi(i,en) = (zzi*yr - zzr*yi) / r2
  END DO

END DO
!     ********** END BACKSUBSTITUTION **********

!     ********** VECTORS OF ISOLATED ROOTS **********
DO i = 1, n-1
  IF (i >= low .AND. i <= igh) CYCLE
  ip1 = i + 1

  DO j = ip1, n
    zr(i,j) = hr(i,j)
    zi(i,j) = hi(i,j)
  END DO

END DO
!     ********** MULTIPLY BY TRANSFORMATION MATRIX TO GIVE
!                VECTORS OF ORIGINAL FULL MATRIX.
!                FOR J=N STEP -1 UNTIL LOW+1 DO -- **********
DO j = n, low+1, -1
  m = MIN(j-1,igh)

  DO i = low, igh
    zzr = zr(i,j)
    zzi = zi(i,j)

    DO k = low, m
      zzr = zzr + zr(i,k) * hr(k,j) - zi(i,k) * hi(k,j)
      zzi = zzi + zr(i,k) * hi(k,j) + zi(i,k) * hr(k,j)
    END DO

    zr(i,j) = zzr
    zi(i,j) = zzi
  END DO
END DO

GO TO 1001
!     ********** SET ERROR -- NO CONVERGENCE TO AN
!                EIGENVALUE AFTER 50 ITERATIONS **********
1000 ierr = en
1001 RETURN
!     ********** LAST CARD OF DCMQR2 **********
END SUBROUTINE dcmqr2

      pure function where_pair_2d(rows, cols) result(idx)
         integer, intent(in) :: rows(:), cols(:)
         integer, allocatable :: idx(:,:)
         integer :: n, k
         if (size(rows) == size(cols)) then
            n = size(rows)
         else if (size(rows) == 1) then
            n = size(cols)
         else if (size(cols) == 1) then
            n = size(rows)
         else
            error stop "shape mismatch in matrix index arrays"
         end if
         allocate(idx(2,n))
         do k = 1, n
            idx(1,k) = rows(min(k,size(rows)))
            idx(2,k) = cols(min(k,size(cols)))
         end do
      end function where_pair_2d

      pure function where_indices_2d(mask) result(idx)
         logical, intent(in) :: mask(:,:)
         integer :: idx(2,count(mask))
         integer :: i, j, k
         k = 0
         do i = 1, size(mask,1)
            do j = 1, size(mask,2)
               if (.not. mask(i,j)) cycle
               k = k + 1
               idx(:,k) = [i-1, j-1]
            end do
         end do
      end function where_indices_2d

      pure function where_axis_2d(mask, axis) result(idx)
         logical, intent(in) :: mask(:,:)
         integer, intent(in) :: axis
         integer :: idx(count(mask))
         integer :: i, j, k
         k = 0
         do i = 1, size(mask,1)
            do j = 1, size(mask,2)
               if (.not. mask(i,j)) cycle
               k = k + 1
               if (axis == 0) then
                  idx(k) = i-1
               else
                  idx(k) = j-1
               end if
            end do
         end do
      end function where_axis_2d

      pure function gather_where2d_real(a, idx) result(values)
         real(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: idx(:,:)
         real(kind=dp) :: values(size(idx,2))
         integer :: k
         do k = 1, size(idx,2)
            values(k) = a(idx(1,k)+1,idx(2,k)+1)
         end do
      end function gather_where2d_real

      pure function gather_where2d_int(a, idx) result(values)
         integer, intent(in) :: a(:,:)
         integer, intent(in) :: idx(:,:)
         integer :: values(size(idx,2))
         integer :: k
         do k = 1, size(idx,2)
            values(k) = a(idx(1,k)+1,idx(2,k)+1)
         end do
      end function gather_where2d_int

      pure function gather_where2d_complex(a, idx) result(values)
         complex(kind=dp), intent(in) :: a(:,:)
         integer, intent(in) :: idx(:,:)
         complex(kind=dp) :: values(size(idx,2))
         integer :: k
         do k = 1, size(idx,2)
            values(k) = a(idx(1,k)+1,idx(2,k)+1)
         end do
      end function gather_where2d_complex

      pure function gather_where2d_logical(a, idx) result(values)
         logical, intent(in) :: a(:,:)
         integer, intent(in) :: idx(:,:)
         logical :: values(size(idx,2))
         integer :: k
         do k = 1, size(idx,2)
            values(k) = a(idx(1,k)+1,idx(2,k)+1)
         end do
      end function gather_where2d_logical

      pure function lexsort_keys_int(keys, reverse_keys) result(idx)
         integer, intent(in) :: keys(:,:)
         logical, optional, intent(in) :: reverse_keys
         integer, allocatable :: idx(:), work(:)
         integer :: n, nk, i, width, lo, mid, hi, p, q, dest, key, first, last, step
         logical :: left_first
         ! Stable bottom-up merge sort. Key rows are ordered least to most
         ! significant, as in NumPy. Reversing key priority implements
         ! lexsort(matrix.T[::-1]) without subscripting a temporary transpose.
         nk = size(keys,1)
         n = size(keys,2)
         if (nk == 0) error stop "lexsort: need at least one key"
         allocate(idx(n), work(n))
         do i = 1, n
            idx(i) = i - 1
         end do
         first = nk
         last = 1
         step = -1
         if (present(reverse_keys)) then
            if (reverse_keys) then
               first = 1
               last = nk
               step = 1
            end if
         end if
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n)
               mid = min(lo + width, n + 1)
               hi = min(lo + 2*width - 1, n)
               p = lo
               q = mid
               dest = lo
               do while (p < mid .and. q <= hi)
                  left_first = .true.
                  do key = first, last, step
                     if (keys(key,idx(p)+1) < keys(key,idx(q)+1)) exit
                     if (keys(key,idx(p)+1) > keys(key,idx(q)+1)) then
                        left_first = .false.
                        exit
                     end if
                  end do
                  if (left_first) then
                     work(dest) = idx(p)
                     p = p + 1
                  else
                     work(dest) = idx(q)
                     q = q + 1
                  end if
                  dest = dest + 1
               end do
               do while (p < mid)
                  work(dest) = idx(p)
                  p = p + 1
                  dest = dest + 1
               end do
               do while (q <= hi)
                  work(dest) = idx(q)
                  q = q + 1
                  dest = dest + 1
               end do
               lo = hi + 1
            end do
            idx = work
            if (width > n/2) exit
            width = 2*width
         end do
      end function lexsort_keys_int

      pure function lexsort_keys_real(keys, reverse_keys) result(idx)
         use, intrinsic :: ieee_arithmetic, only: ieee_is_nan
         real(dp), intent(in) :: keys(:,:)
         logical, optional, intent(in) :: reverse_keys
         integer, allocatable :: idx(:), work(:)
         integer :: n, nk, i, width, lo, mid, hi, p, q, dest, key, first, last, step
         logical :: left_first
         ! Stable bottom-up merge sort. Key rows are ordered least to most
         ! significant, as in NumPy. Reversing key priority implements
         ! lexsort(matrix.T[::-1]) without subscripting a temporary transpose.
         nk = size(keys,1)
         n = size(keys,2)
         if (nk == 0) error stop "lexsort: need at least one key"
         allocate(idx(n), work(n))
         do i = 1, n
            idx(i) = i - 1
         end do
         first = nk
         last = 1
         step = -1
         if (present(reverse_keys)) then
            if (reverse_keys) then
               first = 1
               last = nk
               step = 1
            end if
         end if
         width = 1
         do while (width < n)
            lo = 1
            do while (lo <= n)
               mid = min(lo + width, n + 1)
               hi = min(lo + 2*width - 1, n)
               p = lo
               q = mid
               dest = lo
               do while (p < mid .and. q <= hi)
                  left_first = .true.
                  do key = first, last, step
                  ! NaNs sort after finite values; two NaNs tie at this key.
                  if (ieee_is_nan(keys(key,idx(p)+1))) then
                     if (.not. ieee_is_nan(keys(key,idx(q)+1))) left_first = .false.
                     if (.not. ieee_is_nan(keys(key,idx(q)+1))) exit
                     cycle
                  else if (ieee_is_nan(keys(key,idx(q)+1))) then
                     exit
                  end if
                     if (keys(key,idx(p)+1) < keys(key,idx(q)+1)) exit
                     if (keys(key,idx(p)+1) > keys(key,idx(q)+1)) then
                        left_first = .false.
                        exit
                     end if
                  end do
                  if (left_first) then
                     work(dest) = idx(p)
                     p = p + 1
                  else
                     work(dest) = idx(q)
                     q = q + 1
                  end if
                  dest = dest + 1
               end do
               do while (p < mid)
                  work(dest) = idx(p)
                  p = p + 1
                  dest = dest + 1
               end do
               do while (q <= hi)
                  work(dest) = idx(q)
                  q = q + 1
                  dest = dest + 1
               end do
               lo = hi + 1
            end do
            idx = work
            if (width > n/2) exit
            width = 2*width
         end do
      end function lexsort_keys_real

      pure function lexsort_packed_int(values, lengths) result(idx)
         integer, intent(in) :: values(:)
         integer, intent(in) :: lengths(:)
         integer, allocatable :: idx(:)
         integer :: nk, n
         nk = size(lengths)
         if (nk == 0) error stop "lexsort: need at least one key"
         n = lengths(1)
         if (any(lengths /= n)) error stop "lexsort: key size mismatch"
         idx = lexsort_keys_int(transpose(reshape(values, [n,nk])))
      end function lexsort_packed_int

      pure function lexsort_packed_real(values, lengths) result(idx)
         real(dp), intent(in) :: values(:)
         integer, intent(in) :: lengths(:)
         integer, allocatable :: idx(:)
         integer :: nk, n
         nk = size(lengths)
         if (nk == 0) error stop "lexsort: need at least one key"
         n = lengths(1)
         if (any(lengths /= n)) error stop "lexsort: key size mismatch"
         idx = lexsort_keys_real(transpose(reshape(values, [n,nk])))
      end function lexsort_packed_real

end module python_mod

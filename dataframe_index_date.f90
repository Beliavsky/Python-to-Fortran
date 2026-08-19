! Vendored from c:\fortran\public_domain\github\DataFrame (MIT license, Beliavsky).
! Bundled into a single file (kind_mod + util_mod + date_mod +
! df_index_date_ops_mod + dataframe_index_date_mod) so xp2f.py's
! auto-helper-discovery (which maps `use dataframe_index_date_mod` to a
! single dataframe_index_date.f90) can find every dependency without
! needing to resolve transitive `use` statements across helper files.
module kind_mod
implicit none
private
public :: dp
integer, parameter :: dp = kind(1.0d0)
end module kind_mod

module util_mod
use iso_fortran_env, only: output_unit
use kind_mod, only: dp
implicit none
private
public :: default, assert_equal, write_merge, split_string, display, &
   print_time_elapsed, read_words_line, str, print_table, exe_name, &
   join, seq, cbind
interface default
   module procedure default_int, default_real, default_logical, &
      default_character
end interface default
interface seq
   module procedure seq_stride, seq_unit_stride
end interface seq
interface cbind
   module procedure cbind_vec_vec, cbind_mat_vec, cbind_mat_mat
end interface cbind
interface display
   module procedure display_matrix, display_vector
end interface display
contains

elemental function default_int(x, xopt) result(y)
! return xopt if present, otherwise x
integer, intent(in) :: x
integer, intent(in), optional :: xopt
integer             :: y
if (present(xopt)) then
   y = xopt
else
   y = x
end if
end function default_int

elemental function default_real(x, xopt) result(y)
! return xopt if present, otherwise x
real(kind=dp), intent(in) :: x
real(kind=dp), intent(in), optional :: xopt
real(kind=dp)             :: y
if (present(xopt)) then
   y = xopt
else
   y = x
end if
end function default_real

elemental function default_logical(x, xopt) result(y)
! return xopt if present, otherwise x
logical, intent(in) :: x
logical, intent(in), optional :: xopt
logical             :: y
if (present(xopt)) then
   y = xopt
else
   y = x
end if
end function default_logical

elemental function default_character(x, xopt) result(y)
! return xopt if present, otherwise x
character (len=*), intent(in) :: x
character (len=*), intent(in), optional :: xopt
character (len=100) :: y
if (present(xopt)) then
   y = xopt
else
   y = x
end if
end function default_character

subroutine assert_equal(k, kreq, msg)
! check that k == kreq
integer, intent(in) :: k, kreq
character (len=*), intent(in) :: msg
if (k /= kreq) then
   print "(a, i0, a, i0)", msg // " = ", k, ", must equal ", kreq
   stop
end if
end subroutine assert_equal

subroutine write_merge(tf, x, y, outu, fmt)
!> Writes either `x` or `y` to the specified output unit using the given format.
!! If `tf` is true, writes `x`; otherwise, writes `y`.
!! @param tf Logical condition determining whether to write `x` or `y`.
!! @param x The first character string to write if `tf` is true.
!! @param y The second character string to write if `tf` is false.
!! @param outu Optional output unit (defaults to a predefined output unit).
!! @param fmt Optional format specifier (defaults to "(a)").
logical, intent(in) :: tf
character (len=*), intent(in) :: x, y
integer, intent(in), optional :: outu
character (len=*), intent(in), optional :: fmt
integer :: outu_
character (len=100) :: fmt_
outu_ = default(output_unit, outu)
if (present(fmt)) then
   fmt_ = fmt
else
   fmt_ = "(a)"
end if
if (tf) then
   write (outu_, fmt_) x
else
   write (outu_, fmt_) y
end if
end subroutine write_merge

!------------------------------------------------------------------
! Utility: split_string
!
! Splits the input string 'str' at each occurrence of the single-
! character delimiter 'delim' and returns the pieces in the allocatable
! array 'tokens'. To allocate each element (with deferred length)
! properly, we use the length of the input string.
!------------------------------------------------------------------
subroutine split_string(str, delim, tokens)
character(len=*), intent(in)           :: str
character(len=*), intent(in)           :: delim
character(:), allocatable, intent(out) :: tokens(:)
integer :: start, pos, i, count, n

n = len_trim(str)
if (n == 0) then
   allocate(character(len=0) :: tokens(1))
   tokens(1) = ""
   return
end if

! First pass: count tokens.
count = 0
start = 1
do
   pos = index(str(start:), delim)
   if (pos == 0) then
      count = count + 1
      exit
   else
      count = count + 1
      start = start + pos
   end if
end do

! Allocate tokens; each token gets the full length of the input.
allocate(character(len=n) :: tokens(count))

! Second pass: extract tokens.
start = 1
i = 1
do
   pos = index(str(start:), delim)
   if (pos == 0) then
      tokens(i) = adjustl(str(start:))
      exit
   else
      tokens(i) = adjustl(str(start:start+pos-2))
      start = start + pos
      i = i + 1
   end if
end do
end subroutine split_string

subroutine display_matrix(x, outu, fmt_r, fmt_header, fmt_trailer, &
   title)
! print a matrix
real(kind=dp)    , intent(in)           :: x(:,:)
integer          , intent(in), optional :: outu
character (len=*), intent(in), optional :: fmt_r, fmt_header, &
                                           fmt_trailer, title
integer                                 :: i, outu_
character (len=100)                     :: fmt_r_
outu_  = default(output_unit, outu)
fmt_r_ = default("(*(1x,f10.4))", fmt_r)
if (present(fmt_header)) write(outu_, fmt_header)
if (present(title)) write (outu_, "(a)") title
do i=1,size(x,1)
   write(outu_,fmt_r_) x(i,:)
end do
if (present(fmt_trailer)) write(outu_, fmt_trailer)
end subroutine display_matrix

subroutine display_vector(x, outu, fmt_r, fmt_header, title)
! print a vector
real(kind=dp)    , intent(in)           :: x(:)
integer          , intent(in), optional :: outu
character (len=*), intent(in), optional :: fmt_r, fmt_header, title
integer                                 :: i, outu_
character (len=100)                     :: fmt_r_
outu_  = default(output_unit, outu)
fmt_r_ = default("(*(1x,f10.4))", fmt_r)
if (present(fmt_header)) write(outu_, fmt_header)
if (present(title)) write (outu_, "(a)") title
do i=1,size(x)
   write(outu_,fmt_r_) x(i)
end do
end subroutine display_vector

subroutine print_time_elapsed(old_time, outu)
real(kind=dp), intent(in) :: old_time ! previously set by call cpu_time(old_time)
real(kind=dp)             :: tt
integer      , intent(in), optional :: outu
integer                             :: outu_
character (len=100) :: fmt_time_
outu_ = default(output_unit, outu)
call cpu_time(tt)
fmt_time_= "('time elapsed (s): ', f0.4)"
write (outu_, fmt_time_) tt - old_time
end subroutine print_time_elapsed

subroutine read_words_line(iu,words)
! read words from line, where the line has the # of words followed by the words
! n word_1 word_2 ... word_n
integer          , intent(in)               :: iu
character (len=*), intent(out), allocatable :: words(:)
integer :: ierr, nwords
character (len=10000) :: text
read (iu,"(a)") text
read (text, *) nwords
allocate (words(nwords))
read (text, *, iostat=ierr) nwords, words
if (ierr /= 0) then
   print*,"could not read ", nwords, " words from '" // trim(text) // "'"
   error stop
end if
end subroutine read_words_line

function str(i) result(text)
! convert integer to string
integer, intent(in) :: i
character (len=20) :: text
write (text,"(i0)") i
end function str

subroutine print_table(x, row_names, col_names, outu, &
   fmt_col_names, fmt_row, fmt_header, fmt_trailer)
! print a table with row and column names
real(kind=dp)    , intent(in) :: x(:,:) ! matrix to be printed
character (len=*), intent(in) :: row_names(:), col_names(:)
integer          , intent(in), optional :: outu ! output unit
character (len=*), intent(in), optional :: fmt_col_names, fmt_row, &
   fmt_header, fmt_trailer
integer                       :: i, n1, n2, outu_
character (len=*), parameter  :: msg="in print_table, "
character (len=100) :: fmt_col_names_, fmt_row_
n1 = size(x, 1)
n2 = size(x, 2)
call assert_equal(size(row_names), n1, msg // "size(row_names)")
call assert_equal(size(col_names), n2, msg // "size(col_names)")
fmt_col_names_ = default("(*(a12,:,1x))", fmt_col_names)
fmt_row_ = default("(a12, *(1x,f12.6))", fmt_row)
outu_ = default(output_unit, outu)
if (present(fmt_header)) write (outu_, fmt_header)
write (outu_, fmt_col_names_) "", (trim(col_names(i)), i=1,n2)
do i=1,n1
   write (outu_, fmt_row_) trim(row_names(i)), x(i,:)
end do
if (present(fmt_trailer)) write (outu_, fmt_trailer)
end subroutine print_table

function exe_name() result(xname)
! return the program name
character (len=1000) :: xname
call get_command_argument(0,xname)
xname = trim(xname)
end function exe_name

function join(words,sep) result(str)
! trim and concatenate a vector of character variables,
! inserting sep between them
character (len=*), intent(in)                                   :: words(:),sep
character (len=(size(words)-1)*len(sep) + sum(len_trim(words))) :: str
integer                                                         :: i,nw
nw  = size(words)
str = ""
if (nw < 1) then
   return
else
   str = words(1)
end if
do i=2,nw
   str = trim(str) // sep // words(i) 
end do
end function join

pure function seq_stride(first, last, stride) result(vec)
!! return an integer sequence from first through last
integer, intent(in) :: first, last, stride
integer, allocatable :: vec(:)
integer :: i, n, idiff
idiff = last - first
n = max(0, 1 + idiff/stride)
allocate (vec(n))
do i=1, n
   vec(i) = first + (i - 1) * stride
end do
end function seq_stride

pure function seq_unit_stride(first, last) result(vec)
!! return an integer sequence from first through last
integer, intent(in) :: first, last
integer, allocatable :: vec(:)
integer :: i, n
n = max(0, last - first + 1)
allocate (vec(n))
do i=1, n
   vec(i) = first + i - 1
end do
end function seq_unit_stride

pure function cbind_vec_vec(x,y) result(xy)
! return a matrix whose columns are x(:) and y(:)
real(kind=dp), intent(in) :: x(:), y(:)
real(kind=dp), allocatable :: xy(:,:)
integer :: n
n = size(x,1)
if (size(y) /= n) error stop "mismatched sizes in cbind"
xy = reshape([x, y], [n, 2])
end function cbind_vec_vec

pure function cbind_mat_vec(x,y) result(xy)
! append vector y(:) to matrix x(:,:)
real(kind=dp), intent(in) :: x(:,:), y(:)
real(kind=dp), allocatable :: xy(:,:)
integer :: n1, n2
n1 = size(x,1)
if (size(y) /= n1) error stop "mismatched sizes in cbind"
n2 = size(x,2)
allocate (xy(n1, n2+1))
xy(:,:n2)  = x
xy(:,n2+1) = y 
end function cbind_mat_vec

pure function cbind_mat_mat(x,y) result(xy)
! append columns of y(:,:) to matrix x(:,:)
real(kind=dp), intent(in) :: x(:,:), y(:,:)
real(kind=dp), allocatable :: xy(:,:)
integer :: n1, n2
n1 = size(x,1)
if (size(y,1) /= n1) error stop "mismatched sizes in cbind"
n2 = size(x,2)
allocate (xy(n1, n2+size(y,2)))
xy(:,:n2)  = x
xy(:,n2+1:) = y 
end function cbind_mat_mat

! function appended_char_vec(x, y) result(xy)
! character (len=*), intent(in) :: x(:)
! character (len=*), intent(in) :: y
! character (len=len(x)), allocatable :: xy(:)
!  
! end function appended_char_vec

end module util_mod

module date_mod
implicit none
private
public :: date, valid, date_from_iso, date_from_basic, &
   operator(+), operator(-), operator(==), operator(/=), &
   operator(<), operator(<=), operator(>), operator(>=)

type :: date
   integer :: year = 0
   integer :: month = 0
   integer :: day = 0
contains
   procedure :: to_str ! return date as yyyy-mm-dd
end type date

interface operator(+)
   module procedure add_days_right
   module procedure add_days_left
end interface

interface operator(-)
   module procedure subtract_days
   module procedure difference_days
end interface

interface operator(==)
   module procedure eq_date
end interface

interface operator(/=)
   module procedure ne_date
end interface

interface operator(<)
   module procedure lt_date
end interface

interface operator(<=)
   module procedure le_date
end interface

interface operator(>)
   module procedure gt_date
end interface

interface operator(>=)
   module procedure ge_date
end interface

contains

pure function to_str(this) result(s) ! return date as yyyy-mm-dd
class(date), intent(in) :: this
character(len=10) :: s
s = zero_pad_4(this%year) // '-' // zero_pad_2(this%month) // '-' // zero_pad_2(this%day)
end function to_str

pure elemental logical function valid(x) ! return true if the date is valid
type(date), intent(in) :: x
valid = .false.
if (x%month < 1 .or. x%month > 12) return
if (x%day < 1) return
if (x%day > days_in_month(x%year, x%month)) return
valid = .true.
end function valid

pure elemental integer function days_in_month(year, month) ! return number of days in a year-month pair
integer, intent(in) :: year, month
select case (month)
case (1,3,5,7,8,10,12)
   days_in_month = 31
case (4,6,9,11)
   days_in_month = 30
case (2)
   if ((mod(year,4) == 0 .and. mod(year,100) /= 0) .or. mod(year,400) == 0) then
      days_in_month = 29
   else
      days_in_month = 28
   end if
case default
   days_in_month = 0
end select
end function days_in_month

pure function date_from_iso(s) result(x) ! convert yyyy-mm-dd to a date
character(len=*), intent(in) :: s
type(date) :: x
character(len=len(s)) :: t
integer :: y, m, d
logical :: ok1, ok2, ok3

x = date(0,0,0)
t = adjustl(s)
if (len_trim(t) /= 10) return
if (t(5:5) /= '-' .or. t(8:8) /= '-') return
call parse_uint(t(1:4), y, ok1)
call parse_uint(t(6:7), m, ok2)
call parse_uint(t(9:10), d, ok3)
if (.not. (ok1 .and. ok2 .and. ok3)) return
x = date(y,m,d)
end function date_from_iso

pure function date_from_basic(s) result(x) ! convert yyyymmdd to a date
character(len=*), intent(in) :: s
type(date) :: x
character(len=len(s)) :: t
integer :: y, m, d
logical :: ok1, ok2, ok3

x = date(0,0,0)
t = adjustl(s)
if (len_trim(t) /= 8) return
call parse_uint(t(1:4), y, ok1)
call parse_uint(t(5:6), m, ok2)
call parse_uint(t(7:8), d, ok3)
if (.not. (ok1 .and. ok2 .and. ok3)) return
x = date(y,m,d)
end function date_from_basic

pure elemental type(date) function add_days_right(x, n) ! return date plus integer number of days
type(date), intent(in) :: x
integer, intent(in) :: n
if (.not. valid(x)) then
   add_days_right = date(0,0,0)
else
   add_days_right = from_day_number(day_number(x) + n)
end if
end function add_days_right

pure elemental type(date) function add_days_left(n, x) ! return integer number of days plus date
integer, intent(in) :: n
type(date), intent(in) :: x
add_days_left = add_days_right(x, n)
end function add_days_left

pure elemental type(date) function subtract_days(x, n) ! return date minus integer number of days
type(date), intent(in) :: x
integer, intent(in) :: n
subtract_days = add_days_right(x, -n)
end function subtract_days

pure elemental integer function difference_days(x, y) ! return number of days between two dates
type(date), intent(in) :: x, y
if (.not. valid(x) .or. .not. valid(y)) then
   difference_days = 0
else
   difference_days = day_number(x) - day_number(y)
end if
end function difference_days

pure elemental logical function eq_date(x, y) ! return true if two dates are equal
type(date), intent(in) :: x, y
eq_date = x%year == y%year .and. x%month == y%month .and. x%day == y%day
end function eq_date

pure elemental logical function ne_date(x, y) ! return true if two dates are not equal
type(date), intent(in) :: x, y
ne_date = .not. eq_date(x, y)
end function ne_date

pure elemental logical function lt_date(x, y) ! return true if left date is earlier than right date
type(date), intent(in) :: x, y
lt_date = x%year < y%year .or. (x%year == y%year .and. (x%month < y%month .or. (x%month == y%month .and. x%day < y%day)))
end function lt_date

pure elemental logical function le_date(x, y) ! return true if left date is earlier than or equal to right date
type(date), intent(in) :: x, y
le_date = lt_date(x, y) .or. eq_date(x, y)
end function le_date

pure elemental logical function gt_date(x, y) ! return true if left date is later than right date
type(date), intent(in) :: x, y
gt_date = .not. le_date(x, y)
end function gt_date

pure elemental logical function ge_date(x, y) ! return true if left date is later than or equal to right date
type(date), intent(in) :: x, y
ge_date = .not. lt_date(x, y)
end function ge_date

pure elemental integer function day_number(x) ! return day count used for arithmetic
type(date), intent(in) :: x
integer :: y, m, d, era, yoe, doy, doe, mp
y = x%year
m = x%month
d = x%day
if (m <= 2) y = y - 1
era = floor_div(y, 400)
yoe = y - era*400
if (m > 2) then
   mp = m - 3
else
   mp = m + 9
end if
doy = (153*mp + 2)/5 + d - 1
doe = yoe*365 + yoe/4 - yoe/100 + doy
day_number = era*146097 + doe - 719468
end function day_number

pure elemental type(date) function from_day_number(z) ! convert internal day count to a date
integer, intent(in) :: z
integer :: zz, era, doe, yoe, y, doy, mp, m, d
zz = z + 719468
era = floor_div(zz, 146097)
doe = zz - era*146097
yoe = (doe - doe/1460 + doe/36524 - doe/146096)/365
y = yoe + era*400
doy = doe - (365*yoe + yoe/4 - yoe/100)
mp = (5*doy + 2)/153
d = doy - (153*mp + 2)/5 + 1
if (mp < 10) then
   m = mp + 3
else
   m = mp - 9
end if
if (m <= 2) y = y + 1
from_day_number = date(y,m,d)
end function from_day_number

pure elemental integer function floor_div(a, b) ! return floor(a/b) for positive b
integer, intent(in) :: a, b
floor_div = a / b
if (mod(a, b) < 0) floor_div = floor_div - 1
end function floor_div

pure function zero_pad_2(n) result(s) ! return a 2-character zero-padded integer string
integer, intent(in) :: n
character(len=2) :: s
if (n < 0 .or. n > 99) then
   s = '**'
   return
end if
s(1:1) = achar(iachar('0') + n/10)
s(2:2) = achar(iachar('0') + mod(n,10))
end function zero_pad_2

pure function zero_pad_4(n) result(s) ! return a 4-character zero-padded integer string
integer, intent(in) :: n
character(len=4) :: s
integer :: m
if (n < 0 .or. n > 9999) then
   s = '****'
   return
end if
m = n
s(4:4) = achar(iachar('0') + mod(m,10))
m = m / 10
s(3:3) = achar(iachar('0') + mod(m,10))
m = m / 10
s(2:2) = achar(iachar('0') + mod(m,10))
m = m / 10
s(1:1) = achar(iachar('0') + mod(m,10))
end function zero_pad_4

pure subroutine parse_uint(s, n, ok) ! parse a nonnegative integer from a string
character(len=*), intent(in) :: s
integer, intent(out) :: n
logical, intent(out) :: ok
integer :: i, m, digit
character(len=len(s)) :: t
n = 0
ok = .false.
t = adjustl(s)
m = len_trim(t)
if (m <= 0) return
do i = 1, m
   if (t(i:i) < '0' .or. t(i:i) > '9') return
   digit = iachar(t(i:i)) - iachar('0')
   n = 10*n + digit
end do
ok = .true.
end subroutine parse_uint

end module date_mod

module df_index_date_ops_mod
use date_mod
use util_mod, only: default
implicit none
private
public :: findloc_index, argsort_index, union_index, intersect_index, &
   is_sorted_index_array, is_unique_index_array, bsearch_exact_index, &
   bsearch_ffill_index, bsearch_bfill_index
contains

pure integer function findloc_index(a, x) result(pos) ! return first location of x in a, or 0 if not found
type(date), intent(in) :: a(:)
type(date), intent(in) :: x
integer :: i
pos = 0
do i = 1, size(a)
   if (a(i) == x) then
      pos = i
      return
   end if
end do
end function findloc_index

subroutine argsort_index(a, perm, ascending) ! return permutation perm such that a(perm) is sorted
 type(date), intent(in) :: a(:)
 integer, allocatable, intent(out) :: perm(:)
 logical, intent(in), optional :: ascending
 logical :: asc
 integer :: n, width, i, left, mid, right, p, q, k
 integer, allocatable :: tmp(:)
 asc = default(.true., ascending)
 n = size(a)
 allocate(perm(n), tmp(n))
 perm = [(i, i=1,n)]
 width = 1
 do while (width < n)
    i = 1
    do while (i <= n)
       left = i
       mid = min(i + width - 1, n)
       right = min(i + 2*width - 1, n)
       p = left
       q = mid + 1
       k = left
       do while (p <= mid .and. q <= right)
          if (asc) then
             if (a(perm(p)) <= a(perm(q))) then
                tmp(k) = perm(p)
                p = p + 1
             else
                tmp(k) = perm(q)
                q = q + 1
             end if
          else
             if (a(perm(p)) >= a(perm(q))) then
                tmp(k) = perm(p)
                p = p + 1
             else
                tmp(k) = perm(q)
                q = q + 1
             end if
          end if
          k = k + 1
       end do
       do while (p <= mid)
          tmp(k) = perm(p)
          p = p + 1
          k = k + 1
       end do
       do while (q <= right)
          tmp(k) = perm(q)
          q = q + 1
          k = k + 1
       end do
       perm(left:right) = tmp(left:right)
       i = i + 2*width
    end do
    width = 2*width
 end do
 deallocate(tmp)
end subroutine argsort_index

pure logical function is_sorted_index_array(a, ascending) result(is_sorted) ! return true if a is sorted
 type(date), intent(in) :: a(:)
 logical, intent(in), optional :: ascending
 logical :: asc
 integer :: i
 asc = default(.true., ascending)
 is_sorted = .true.
 if (size(a) <= 1) return
 if (asc) then
    do i = 2, size(a)
       if (a(i) < a(i-1)) then
          is_sorted = .false.
          return
       end if
    end do
 else
    do i = 2, size(a)
       if (a(i) > a(i-1)) then
          is_sorted = .false.
          return
       end if
    end do
 end if
end function is_sorted_index_array

logical function is_unique_index_array(a) result(is_unique) ! return true if a has no duplicates
 type(date), intent(in) :: a(:)
 integer :: i, n
 integer, allocatable :: perm(:)
 type(date), allocatable :: tmp(:)
 n = size(a)
 is_unique = .true.
 if (n <= 1) return
 allocate(tmp(n))
 tmp = a
 call argsort_index(tmp, perm, ascending=.true.)
 tmp = tmp(perm)
 do i = 2, n
    if (tmp(i) == tmp(i-1)) then
       is_unique = .false.
       exit
    end if
 end do
 deallocate(tmp, perm)
end function is_unique_index_array

function union_index(a, b) result(c) ! return union of a and b preserving first appearance order
 type(date), intent(in) :: a(:), b(:)
 type(date), allocatable :: c(:)
 type(date), allocatable :: tmp(:)
 integer :: n, i
 allocate(tmp(size(a) + size(b)))
 n = 0
 do i = 1, size(a)
    n = n + 1
    tmp(n) = a(i)
 end do
 do i = 1, size(b)
    if (.not. any(tmp(1:n) == b(i))) then
       n = n + 1
       tmp(n) = b(i)
    end if
 end do
 allocate(c(n))
 c = tmp(1:n)
end function union_index

function intersect_index(a, b) result(c) ! return intersection of a and b preserving order from a
 type(date), intent(in) :: a(:), b(:)
 type(date), allocatable :: c(:)
 type(date), allocatable :: tmp(:)
 integer :: n, i
 allocate(tmp(size(a)))
 n = 0
 do i = 1, size(a)
    if (any(b == a(i))) then
      n = n + 1
      tmp(n) = a(i)
    end if
 end do
 allocate(c(n))
 c = tmp(1:n)
end function intersect_index

pure integer function bsearch_exact_index(a, x) result(pos) ! return exact match position in sorted ascending array
 type(date), intent(in) :: a(:)
 type(date), intent(in) :: x
 integer :: lo, hi, mid
 pos = 0
 lo = 1
 hi = size(a)
 do while (lo <= hi)
    mid = (lo + hi)/2
    if (a(mid) == x) then
       pos = mid
       return
    else if (a(mid) < x) then
       lo = mid + 1
    else
       hi = mid - 1
    end if
 end do
end function bsearch_exact_index

pure integer function bsearch_ffill_index(a, x) result(pos) ! return rightmost a(pos) <= x in sorted ascending array
 type(date), intent(in) :: a(:)
 type(date), intent(in) :: x
 integer :: lo, hi, mid
 pos = 0
 lo = 1
 hi = size(a)
 do while (lo <= hi)
    mid = (lo + hi)/2
    if (a(mid) <= x) then
       pos = mid
       lo = mid + 1
    else
       hi = mid - 1
    end if
 end do
end function bsearch_ffill_index

pure integer function bsearch_bfill_index(a, x) result(pos) ! return leftmost a(pos) >= x in sorted ascending array
 type(date), intent(in) :: a(:)
 type(date), intent(in) :: x
 integer :: lo, hi, mid
 pos = 0
 lo = 1
 hi = size(a)
 do while (lo <= hi)
    mid = (lo + hi)/2
    if (a(mid) >= x) then
       pos = mid
       hi = mid - 1
    else
       lo = mid + 1
    end if
 end do
end function bsearch_bfill_index

end module df_index_date_ops_mod

module dataframe_index_date_mod
use kind_mod, only: dp
use util_mod, only: default, split_string, seq, cbind
use iso_fortran_env, only: output_unit
use date_mod
use df_index_date_ops_mod, only: findloc_index, argsort_index, union_index, &
   intersect_index, is_sorted_index_array, is_unique_index_array, &
   bsearch_exact_index, bsearch_ffill_index, bsearch_bfill_index
use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan, ieee_is_nan
implicit none
private
public :: DataFrame_index_date, nrow, ncol, print_summary, random, operator(*), &
   operator(/), operator(+), operator(-), display, allocate_df, &
   operator(**), shape, subset_stride, &
   date, date_from_iso, date_from_basic, valid, &
   operator(==), operator(/=), operator(<), operator(<=), operator(>), operator(>=)
integer, parameter :: nlen_columns = 100, nrows_print = 10 ! number of rows to print by default.
logical, save :: blank_line_before_display = .true.
interface display
   module procedure display_data
end interface display
interface operator (*)
   module procedure mult_x_df, mult_df_x, mult_n_df, mult_df_n
   module procedure mult_df_df
end interface
interface operator (/)
   module procedure div_df_x, div_df_n, div_x_df, div_n_df
   module procedure div_df_df
end interface
interface operator (+)
   module procedure add_x_df, add_df_x, add_n_df, add_df_n
   module procedure add_df_df
end interface
interface operator (-)
   module procedure subtract_x_df, subtract_df_x, &
      subtract_n_df, subtract_df_n, subtract_df_df
end interface
interface operator (**)
   module procedure power_df_n, power_df_x
end interface

type :: DataFrame_index_date
   type(date), allocatable      :: index(:)
   character(len=nlen_columns), allocatable :: columns(:)
   real(kind=dp), allocatable    :: values(:,:)
   contains
      procedure :: read_csv, display=>display_data, write_csv, irow, icol, &
         loc, append_col, append_cols, set_col, col_pos, row_pos, &
         sort_index, is_sorted_index, is_unique_index, at, iat, &
         set_at, set_iat, has_col, has_idx, drop_cols, drop_rows, &
         rename_cols, where_cols, filter_cols, where, filter, iloc, &
         select, add, subtract, multiply, divide, reindex, shift, &
         pct_change, log_change
end type DataFrame_index_date

contains

pure function shape(df) result(ishape)
! return a 2-element array with the number of rows and columns of the dataframe
type(DataFrame_index_date), intent(in) :: df
integer                     :: ishape(2)
ishape = [nrow(df), ncol(df)]
end function shape

pure function icol(df, ivec) result(df_new)
! returns a dataframe with the subset of columns in ivec(:)
class(DataFrame_index_date), intent(in) :: df
integer, intent(in) :: ivec(:)
type(DataFrame_index_date) :: df_new
df_new = DataFrame_index_date(index=df%index, columns=df%columns(ivec), values=df%values(:, ivec))
end function icol

pure function loc(df, rows, columns) result(df_new)
! return a subset of a dataframe with the specified rows (index values) and columns
class(DataFrame_index_date), intent(in) :: df
type(date), intent(in), optional :: rows(:)
character (len=*), intent(in), optional :: columns(:)
type(DataFrame_index_date) :: df_new
type(date), allocatable :: rows_(:)
character (len=nlen_columns), allocatable :: columns_(:)
integer :: i
integer, allocatable :: jrow(:), jcol(:)
if (present(rows)) then
   rows_ = rows
   allocate (jrow(size(rows)))
   do i=1,size(rows)
      jrow(i) = findloc_index(df%index, rows(i))
   end do
else
   rows_ = df%index
   jrow = seq(1, nrow(df))
end if
if (present(columns)) then
   columns_ = columns
   allocate(jcol(size(columns)))
   do i=1,size(columns)
      jcol(i) = findloc(df%columns, columns(i), dim=1)
   end do
else
   columns_ = df%columns
   jcol = seq(1, ncol(df))
end if
df_new = DataFrame_index_date(index=rows_, columns=columns_, values=df%values(jrow, jcol))
end function loc

pure function row_pos(self, idx, assume_sorted, ascending) result(irow)
! return the row position (1..nrow) for index value idx
! if assume_sorted is true, use binary search assuming index is sorted
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in) :: idx
logical, intent(in), optional :: assume_sorted, ascending
integer :: irow
logical :: do_sorted, asc
integer :: lo, hi, mid

do_sorted = default(.false., assume_sorted)
asc = default(.true., ascending)

if (.not. allocated(self%index)) error stop "in row_pos, index is not allocated"

if (do_sorted) then
   ! binary search for first occurrence (like findloc) in a sorted index
   lo = 1
   hi = size(self%index)
   irow = 0
   do while (lo <= hi)
      mid = (lo + hi) / 2
      if (asc) then
         if (self%index(mid) < idx) then
            lo = mid + 1
         else
            if (self%index(mid) == idx) irow = mid
            hi = mid - 1
         end if
      else
         if (self%index(mid) > idx) then
            lo = mid + 1
         else
            if (self%index(mid) == idx) irow = mid
            hi = mid - 1
         end if
      end if
   end do
else
   irow = findloc_index(self%index, idx)
end if

if (irow == 0) error stop "in row_pos, index not found"
end function row_pos

function is_sorted_index(self, ascending) result(is_sorted)
! return true if index is sorted (nondecreasing if ascending, nonincreasing otherwise)
class(DataFrame_index_date), intent(in) :: self
logical, intent(in), optional :: ascending
logical :: is_sorted
logical :: asc
integer :: i, n

asc = default(.true., ascending)

if (.not. allocated(self%index)) then
   is_sorted = .true.
   return
end if

n = size(self%index)
is_sorted = .true.
if (n <= 1) return

if (asc) then
   do i=2,n
      if (self%index(i) < self%index(i-1)) then
         is_sorted = .false.
         exit
      end if
   end do
else
   do i=2,n
      if (self%index(i) > self%index(i-1)) then
         is_sorted = .false.
         exit
      end if
   end do
end if
end function is_sorted_index

function is_unique_index(self) result(is_unique)
! return true if index has no duplicates
class(DataFrame_index_date), intent(in) :: self
logical :: is_unique

if (.not. allocated(self%index)) then
   is_unique = .true.
   return
end if

is_unique = is_unique_index_array(self%index)
end function is_unique_index

subroutine sort_index(self, ascending)
! sort rows by index, permuting values accordingly
class(DataFrame_index_date), intent(inout) :: self
logical, intent(in), optional :: ascending
logical :: asc
integer :: n
integer, allocatable :: perm(:)
real(kind=dp), allocatable :: vtmp(:,:)

asc = default(.true., ascending)

if (.not. allocated(self%index)) return
if (.not. allocated(self%values)) return

n = size(self%index)
if (n <= 1) return

call argsort_index(self%index, perm, ascending=asc)

! reorder index
self%index = self%index(perm)

! reorder values
allocate(vtmp(n, size(self%values,2)))
vtmp = self%values(perm, :)
self%values = vtmp
deallocate(vtmp, perm)
end subroutine sort_index


pure function col_pos(self, column) result(jcol)
! return the column position (1..ncol) for column name
class(DataFrame_index_date), intent(in) :: self
character(len=*), intent(in) :: column
integer :: jcol
jcol = findloc(self%columns, column, dim=1)
if (jcol == 0) error stop "in col_pos, column not found: " // trim(column)
end function col_pos

pure function iat(self, i, j) result(x)
! return a scalar element by 1-based row/column positions
class(DataFrame_index_date), intent(in) :: self
integer, intent(in) :: i, j
real(kind=dp) :: x
if (i < 1 .or. i > nrow(self)) error stop "in iat, row position out of range"
if (j < 1 .or. j > ncol(self)) error stop "in iat, column position out of range"
x = self%values(i, j)
end function iat

pure function at(self, idx, column) result(x)
! return a scalar element by index value and column name
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in) :: idx
character(len=*), intent(in) :: column
real(kind=dp) :: x
integer :: i, j
i = self%row_pos(idx)
j = self%col_pos(column)
x = self%values(i, j)
end function at

pure subroutine set_iat(self, i, j, x)
! set a scalar element by 1-based row/column positions
class(DataFrame_index_date), intent(in out) :: self
integer, intent(in) :: i, j
real(kind=dp), intent(in) :: x
if (i < 1 .or. i > nrow(self)) error stop "in set_iat, row position out of range"
if (j < 1 .or. j > ncol(self)) error stop "in set_iat, column position out of range"
self%values(i, j) = x
end subroutine set_iat

pure subroutine set_at(self, idx, column, x)
! set a scalar element by index value and column name
class(DataFrame_index_date), intent(in out) :: self
type(date), intent(in) :: idx
character(len=*), intent(in) :: column
real(kind=dp), intent(in) :: x
integer :: i, j
i = self%row_pos(idx)
j = self%col_pos(column)
self%values(i, j) = x
end subroutine set_at

logical function has_col(self, name)
! return .true. if dataframe has a column with the given name
class(DataFrame_index_date), intent(in) :: self
character(len=*), intent(in) :: name
integer :: j
character(len=nlen_columns) :: key
key = trim(name)
j = findloc(self%columns, key, dim=1)
has_col = (j > 0)
end function has_col

logical function has_idx(self, idx)
! return .true. if dataframe has a row with the given index value
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in) :: idx
integer :: i
i = findloc_index(self%index, idx)
has_idx = (i > 0)
end function has_idx

function drop_cols(self, names, missing) result(df_new)
! drop columns by name
class(DataFrame_index_date), intent(in) :: self
character(len=*), intent(in) :: names(:)
character(len=*), intent(in), optional :: missing
type(DataFrame_index_date) :: df_new
logical, allocatable :: keep(:)
integer, allocatable :: ivec_keep(:)
integer :: k, j, n
character(len=100) :: miss
character(len=nlen_columns) :: key

miss = trim(default("error", missing))
miss = str_lower(miss)

n = ncol(self)
allocate(keep(n))
keep = .true.

do k = 1, size(names)
   key = trim(names(k))
   j = findloc(self%columns, key, dim=1)
   if (j <= 0) then
      if (miss == "ignore") cycle
      error stop "drop_cols: column not found: "//trim(names(k))
   end if
   keep(j) = .false.
end do

ivec_keep = pack(seq(1, n), keep)
df_new = self%icol(ivec_keep)
end function drop_cols

function drop_rows(self, idx, missing) result(df_new)
! drop rows by index value
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in) :: idx(:)
character(len=*), intent(in), optional :: missing
type(DataFrame_index_date) :: df_new
logical, allocatable :: keep(:)
integer, allocatable :: ivec_keep(:)
integer :: k, i, n
character(len=100) :: miss

miss = trim(default("error", missing))
miss = str_lower(miss)

n = nrow(self)
allocate(keep(n))
keep = .true.

do k = 1, size(idx)
   i = findloc_index(self%index, idx(k))
   if (i <= 0) then
      if (miss == "ignore") cycle
      error stop "drop_rows: index not found"
   end if
   keep(i) = .false.
end do

ivec_keep = pack(seq(1, n), keep)
df_new = self%irow(ivec_keep)
end function drop_rows

subroutine rename_cols(self, old, new, missing)
! rename columns: replace each old(i) with new(i)
class(DataFrame_index_date), intent(in out) :: self
character(len=*), intent(in) :: old(:), new(:)
character(len=*), intent(in), optional :: missing
integer :: k, j
character(len=100) :: miss
character(len=nlen_columns) :: key

if (size(old) /= size(new)) error stop "rename_cols: size(old) /= size(new)"

miss = trim(default("error", missing))
miss = str_lower(miss)

do k = 1, size(old)
   key = trim(old(k))
   j = findloc(self%columns, key, dim=1)
   if (j <= 0) then
      if (miss == "ignore") cycle
      error stop "rename_cols: column not found: "//trim(old(k))
   end if
   self%columns(j) = trim(new(k))
end do
end subroutine rename_cols



function where_cols(self, mask_cols) result(df_new)
! keep columns where mask_cols(j) is .true.
class(DataFrame_index_date), intent(in) :: self
logical, intent(in) :: mask_cols(:)
type(DataFrame_index_date) :: df_new
integer, allocatable :: j_keep(:)
if (size(mask_cols) /= ncol(self)) error stop "where_cols: size(mask_cols) /= ncol(self)"
j_keep = pack(seq(1, ncol(self)), mask_cols)
df_new = self%icol(j_keep)
end function where_cols

function filter_cols(self, mask_cols, drop) result(df_new)
! filter columns by mask; if drop=.true. then drop columns where mask is .true.
class(DataFrame_index_date), intent(in) :: self
logical, intent(in) :: mask_cols(:)
logical, intent(in), optional :: drop
type(DataFrame_index_date) :: df_new
logical :: drop_
logical, allocatable :: keep(:)
drop_ = default(.false., drop)
if (size(mask_cols) /= ncol(self)) error stop "filter_cols: size(mask_cols) /= ncol(self)"
allocate(keep(size(mask_cols)))
if (drop_) then
   keep = .not. mask_cols
else
   keep = mask_cols
end if
df_new = self%where_cols(keep)
end function filter_cols

function where(self, mask_rows, mask_cols) result(df_new)
! keep rows and columns where masks are .true.
class(DataFrame_index_date), intent(in) :: self
logical, intent(in) :: mask_rows(:)
logical, intent(in) :: mask_cols(:)
type(DataFrame_index_date) :: df_new
integer, allocatable :: i_keep(:), j_keep(:)
if (size(mask_rows) /= nrow(self)) error stop "where: size(mask_rows) /= nrow(self)"
if (size(mask_cols) /= ncol(self)) error stop "where: size(mask_cols) /= ncol(self)"
i_keep = pack(seq(1, nrow(self)), mask_rows)
j_keep = pack(seq(1, ncol(self)), mask_cols)
df_new = DataFrame_index_date(index=self%index(i_keep), columns=self%columns(j_keep), values=self%values(i_keep, j_keep))
end function where

function filter(self, mask_rows, mask_cols, drop_rows, drop_cols) result(df_new)
! filter rows and columns by masks; if drop_rows/drop_cols are .true. then drop where mask is .true.
class(DataFrame_index_date), intent(in) :: self
logical, intent(in) :: mask_rows(:)
logical, intent(in) :: mask_cols(:)
logical, intent(in), optional :: drop_rows, drop_cols
type(DataFrame_index_date) :: df_new
logical :: drop_r, drop_c
logical, allocatable :: keep_rows(:), keep_cols(:)

if (size(mask_rows) /= nrow(self)) error stop "filter: size(mask_rows) /= nrow(self)"
if (size(mask_cols) /= ncol(self)) error stop "filter: size(mask_cols) /= ncol(self)"

drop_r = default(.false., drop_rows)
drop_c = default(.false., drop_cols)

allocate(keep_rows(size(mask_rows)))
allocate(keep_cols(size(mask_cols)))

if (drop_r) then
   keep_rows = .not. mask_rows
else
   keep_rows = mask_rows
end if

if (drop_c) then
   keep_cols = .not. mask_cols
else
   keep_cols = mask_cols
end if

df_new = self%where(keep_rows, keep_cols)
end function filter

function iloc(self, rows, cols) result(df_new)
! positional selection by row/column positions (1-based)
class(DataFrame_index_date), intent(in) :: self
integer, intent(in), optional :: rows(:)
integer, intent(in), optional :: cols(:)
type(DataFrame_index_date) :: df_new
if (present(rows) .and. present(cols)) then
   df_new = self%select(irows=rows, icols=cols)
else if (present(rows)) then
   df_new = self%select(irows=rows)
else if (present(cols)) then
   df_new = self%select(icols=cols)
else
   df_new = self%select()
end if
end function iloc

function select(self, rows, columns, irows, icols) result(df_new)
! select a sub-dataframe using label- or position-based selectors on each axis.
! rules:
!  - at most one of rows/irows may be present
!  - at most one of columns/icols may be present
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in), optional :: rows(:)
character(len=*), intent(in), optional :: columns(:)
integer, intent(in), optional :: irows(:)
integer, intent(in), optional :: icols(:)
type(DataFrame_index_date) :: df_new
integer, allocatable :: i_keep(:), j_keep(:)
integer :: k

if (present(rows) .and. present(irows)) error stop "select: both rows and irows are present"
if (present(columns) .and. present(icols)) error stop "select: both columns and icols are present"

if (present(rows)) then
   allocate(i_keep(size(rows)))
   do k = 1, size(rows)
      i_keep(k) = self%row_pos(rows(k))
   end do
else if (present(irows)) then
   i_keep = irows
   do k = 1, size(i_keep)
      if (i_keep(k) < 1 .or. i_keep(k) > nrow(self)) error stop "select: row position out of range"
   end do
else
   i_keep = seq(1, nrow(self))
end if

if (present(columns)) then
   allocate(j_keep(size(columns)))
   do k = 1, size(columns)
      j_keep(k) = self%col_pos(columns(k))
   end do
else if (present(icols)) then
   j_keep = icols
   do k = 1, size(j_keep)
      if (j_keep(k) < 1 .or. j_keep(k) > ncol(self)) error stop "select: column position out of range"
   end do
else
   j_keep = seq(1, ncol(self))
end if

df_new = DataFrame_index_date(index=self%index(i_keep), columns=self%columns(j_keep), values=self%values(i_keep, j_keep))
end function select
pure function str_lower(str) result(out)
! return str converted to lowercase (ASCII)
character(len=*), intent(in) :: str
character(len=len(str))      :: out
integer :: i, c
out = str
do i = 1, len(str)
   c = iachar(out(i:i))
   if (c >= iachar('A') .and. c <= iachar('Z')) out(i:i) = achar(c + 32)
end do
end function str_lower




pure function irow(df, ivec) result(df_new)
! returns a dataframe with the subset of columns in ivec(:)
class(DataFrame_index_date), intent(in) :: df
integer, intent(in) :: ivec(:)
type(DataFrame_index_date) :: df_new
df_new = DataFrame_index_date(index=df%index(ivec), columns=df%columns, values=df%values(ivec, :))
end function irow

pure subroutine set_col(df, column, values)
! append a column with specified values to DataFrame df if column is not in df,
! and set the values of that column if it is already present
class(DataFrame_index_date), intent(in out) :: df
character (len=*), intent(in) :: column
real(kind=dp), intent(in) :: values(:)
integer :: jcol
if (size(values) /= nrow(df)) error stop "in set_col, size(values) /= nrow(df)"
jcol = findloc(df%columns, column, dim=1)
if (jcol == 0) then
   call append_col(df, column, values)
else
   df%values(:,jcol) = values
end if
end subroutine set_col

pure subroutine append_col(df, column, values)
! append a column with specified values to DataFrame df
class(DataFrame_index_date), intent(in out) :: df
character (len=*), intent(in) :: column
real(kind=dp), intent(in) :: values(:)
character (len=nlen_columns) :: column_
if (size(values) /= nrow(df)) error stop "in append_col, size(values) /= nrow(df)"
column_ = column
df%columns = [df%columns, column_]
df%values  = cbind(df%values, values)
end subroutine append_col

pure subroutine append_cols(df, columns, values)
! append a column with specified values to DataFrame df
class(DataFrame_index_date), intent(in out) :: df
character (len=*), intent(in) :: columns(:)
real(kind=dp), intent(in) :: values(:,:)
character (len=nlen_columns), allocatable :: columns_(:)
if (size(values, 1) /= nrow(df)) error stop "in append_cols, size(values) /= nrow(df)"
if (size(values, 2) /= size(columns)) error stop "in append_cols, size(values, 2) /= size(columns)"
columns_ = columns
df%columns = [df%columns, columns_]
df%values  = cbind(df%values, values)
end subroutine append_cols

subroutine allocate_df(df, n1, n2, default_indices, default_columns)
type(DataFrame_index_date), intent(out) :: df
integer        , intent(in)  :: n1, n2
logical        , intent(in), optional :: default_indices, default_columns
integer :: i
allocate (df%index(n1), df%columns(n2), df%values(n1, n2))
if (default(.true., default_indices)) then
   do i=1,n1
      df%index(i) = date(2000,1,1) + (i - 1)
   end do
end if
if (default(.true., default_columns)) then
   do i=1,n2
      write (df%columns(i), "('x',i0)") i
   end do
end if
end subroutine allocate_df

elemental function nrow(df) result(num_rows)
! return the # of rows
type(DataFrame_index_date), intent(in) :: df
integer                     :: num_rows
if (allocated(df%values)) then
   num_rows = size(df%values, 1)
else
   num_rows = -1
end if
end function nrow

elemental function ncol(df) result(num_col)
! return the # of columns
type(DataFrame_index_date), intent(in) :: df
integer                     :: num_col
if (allocated(df%values)) then
   num_col = size(df%values, 2)
else
   num_col = -1
end if
end function ncol

!------------------------------------------------------------------
! read_csv:
!
! Reads from a CSV file with the following format:
!
!      ,Col1,Col2,...
!      index1,val11,val12,...
!      index2,val21,val22,...
!
! The header row begins with an empty token (before the first comma).
!------------------------------------------------------------------
subroutine read_csv(self, filename, max_col, max_rows)
class(DataFrame_index_date), intent(inout) :: self
character(len=*), intent(in)    :: filename
integer, intent(in), optional :: max_col, max_rows
integer :: io, unit, i, j, nrows, ncols
character(len=1024) :: line
character(:), allocatable :: tokens(:)
type(date) :: idx

if (allocated(self%index)) deallocate(self%index)
if (allocated(self%columns)) deallocate(self%columns)
if (allocated(self%values)) deallocate(self%values)

open(newunit=unit, file=filename, status='old', action='read', iostat=io)
if (io /= 0) error stop "Error opening file in read_csv"

read(unit, '(A)', iostat=io) line
if (io /= 0) error stop "Error reading header line in read_csv"

call split_string(line, ",", tokens)
ncols = size(tokens) - 1
if (present(max_col)) ncols = min(ncols, max_col)
if (ncols <= 0) error stop "No columns detected in header in read_csv"

allocate(self%columns(ncols))
do i = 1, ncols
   self%columns(i) = tokens(i+1)
end do

nrows = 0
do
   if (present(max_rows)) then
      if (nrows >= max_rows) exit
   end if
   read(unit, '(A)', iostat=io) line
   if (io /= 0 .or. trim(line) == "") exit
   nrows = nrows + 1
end do
if (nrows == 0) error stop "No data lines detected in read_csv"

rewind(unit)
read(unit, '(A)')

allocate(self%index(nrows), self%values(nrows, ncols))
do i = 1, nrows
   read(unit, '(A)', iostat=io) line
   if (io /= 0) error stop "Error reading data row in read_csv"
   if (trim(line) == "") exit
   call split_string(line, ",", tokens)
   idx = date_from_iso(trim(tokens(1)))
   if (.not. valid(idx)) idx = date_from_basic(trim(tokens(1)))
   if (.not. valid(idx)) error stop "Invalid date in first column in read_csv"
   self%index(i) = idx
   do j = 1, ncols
      read(tokens(j+1), *) self%values(i,j)
   end do
end do

close(unit)
end subroutine read_csv

!------------------------------------------------------------------
! display_data:
!
! Prints the DataFrame to the screen in a CSV-like format.
! If the DataFrame has more than nrows_print observations, by default only
! the first nrows_print/2 and the last (nrows_print - nrows_print/2) rows are
! printed with an indication of omitted rows.
!
! An optional logical argument 'print_all' may be provided. If it is present
! and set to .true., then all rows are printed.
!------------------------------------------------------------------
impure elemental subroutine display_data(self, print_all, fmt_ir, fmt_header, fmt_trailer, title)
class(DataFrame_index_date), intent(in) :: self
logical, intent(in), optional :: print_all
character (len=*), intent(in), optional :: fmt_ir, fmt_header, fmt_trailer, title
integer :: total, i, n_top, n_bottom
logical :: print_all_
character (len=100) :: fmt_ir_, fmt_header_
fmt_ir_ = default("(*(1x,f10.4))", fmt_ir)
fmt_header_ = default("(a10,*(1x,a10))", fmt_header)
print_all_ = default(.false., print_all)
total = size(self%index)
if (blank_line_before_display) write(*,*)
if (present(title)) write(*,"(a)") title
write(*,fmt_header_) "index", (trim(self%columns(i)), i=1,size(self%columns))

if (print_all_) then
   do i = 1, total
      write(*,'(a10)', advance='no') self%index(i)%to_str()
      write(*,fmt_ir_) self%values(i,:)
   end do
else
   if (total <= nrows_print) then
      do i = 1, total
         write(*,'(a10)', advance='no') self%index(i)%to_str()
         write(*,fmt_ir_) self%values(i,:)
      end do
   else
      n_top = nrows_print / 2
      n_bottom = nrows_print - n_top
      do i = 1, n_top
         write(*,'(a10)', advance='no') self%index(i)%to_str()
         write(*,fmt_ir_) self%values(i,:)
      end do
      write(*,*) "   ... (", total - nrows_print, " rows omitted) ..."
      do i = total - n_bottom + 1, total
         write(*,'(a10)', advance='no') self%index(i)%to_str()
         write(*,fmt_ir_) self%values(i,:)
      end do
   end if
end if
if (present(fmt_trailer)) write(*,fmt_trailer)
end subroutine display_data

!------------------------------------------------------------------
! write_csv:
!
! Writes the DataFrame to a CSV file in the same format as read_csv.
!------------------------------------------------------------------
subroutine write_csv(self, filename)
class(DataFrame_index_date), intent(in) :: self
character(len=*), intent(in) :: filename
integer :: i, j, unit, io

open(newunit=unit, file=filename, status='replace', action='write', iostat=io)
if (io /= 0) error stop "Error opening output file in write_csv"

write(unit,'(A)', advance='no') ""
do j = 1, size(self%columns)
   write(unit,'(",", A)', advance='no') trim(self%columns(j))
end do
write(unit,*)

do i = 1, size(self%index)
   write(unit,'(A)', advance='no') trim(self%index(i)%to_str())
   do j = 1, size(self%columns)
      write(unit,'(",", G0.12)', advance='no') self%values(i,j)
   end do
   write(unit,*)
end do
close(unit)
end subroutine write_csv

subroutine print_summary(self, outu, fmt_header, fmt_trailer)
type(DataFrame_index_date), intent(in) :: self
integer, intent(in), optional :: outu
character (len=*), intent(in), optional :: fmt_header, fmt_trailer
integer :: outu_, nr, nc
outu_ = default(output_unit, outu)
if (present(fmt_header)) write (outu_, fmt_header)
nr = nrow(self)
nc = ncol(self)
write(outu_, "('#rows, columns:', 2(1x,i0))") nr, nc
if (nr > 0) write(outu_, "('first, last indices:', 2(1x,a))") trim(self%index(1)%to_str()), trim(self%index(nr)%to_str())
if (nc > 0) write(outu_, "('first, last columns:', 2(1x,a))") trim(self%columns(1)), trim(self%columns(nc))
if (present(fmt_trailer)) write (outu_, fmt_trailer)
end subroutine print_summary

subroutine alloc(self, nr, nc)
type(DataFrame_index_date), intent(out) :: self
integer        , intent(in)  :: nr, nc
allocate (self%index(nr), self%values(nr, nc))
allocate (self%columns(nc))
end subroutine alloc

subroutine random(self, nr, nc)
type(DataFrame_index_date), intent(out) :: self
integer, intent(in) :: nr, nc
integer :: i
call alloc(self, nr, nc)
call random_number(self%values)
do i=1,nr
   self%index(i) = date(2000,1,1) + (i - 1)
end do
do i=1,nc
   write (self%columns(i), "('C',i0)") i
end do
end subroutine random

function mult_x_df(x, df) result(res)
! return x * df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = x*res%values
end function mult_x_df

function mult_df_x(df, x) result(res)
! return df * x
type(DataFrame_index_date), intent(in) :: df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = x*res%values
end function mult_df_x

function add_x_df(x, df) result(res)
! return x * df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = x + res%values
end function add_x_df

function add_df_x(df, x) result(res)
! return df * x
type(DataFrame_index_date), intent(in) :: df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values + x
end function add_df_x

function subtract_x_df(x, df) result(res)
! return x - df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = x - res%values
end function subtract_x_df

function subtract_df_x(df, x) result(res)
! return df - x
type(DataFrame_index_date), intent(in) :: df
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values - x
end function subtract_df_x

function div_df_x(df, x) result(res)
! return df / x
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values/x
end function div_df_x

function div_x_df(x, df) result(res)
! return df / x
real(kind=dp)  , intent(in) :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = x/res%values
end function div_x_df

function div_n_df(n, df) result(res)
! return n / x
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = n/res%values
end function div_n_df

function mult_n_df(n, df) result(res)
! return n * df
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = n*res%values
end function mult_n_df

function mult_df_n(df, n) result(res)
! return df * n
type(DataFrame_index_date), intent(in) :: df
integer        , intent(in) :: n
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = n*res%values
end function mult_df_n

function add_n_df(n, df) result(res)
! return n * df
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = n + res%values
end function add_n_df

function add_df_n(df, n) result(res)
! return df * n
type(DataFrame_index_date), intent(in) :: df
integer        , intent(in) :: n
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values + n
end function add_df_n

function subtract_n_df(n, df) result(res)
! return n - df
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = n - res%values
end function subtract_n_df

function subtract_df_n(df, n) result(res)
! return df - n
type(DataFrame_index_date), intent(in) :: df
integer        , intent(in) :: n
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values - n
end function subtract_df_n

function div_df_n(df, n) result(res)
! return df / n
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values/n
end function div_df_n

subroutine require_unique_labels(df, who)
! error stop if df has duplicate index or duplicate column names
type(DataFrame_index_date), intent(in) :: df
character(len=*), intent(in) :: who
character(len=200) :: msg
integer :: i, j

do i = 1, nrow(df) - 1
   do j = i + 1, nrow(df)
      if (df%index(i) == df%index(j)) then
         write(msg, "(a, a)") trim(who), ": duplicate index"
         error stop msg
      end if
   end do
end do

do i = 1, ncol(df) - 1
   do j = i + 1, ncol(df)
      if (trim(df%columns(i)) == trim(df%columns(j))) then
         write(msg, "(a, a)") trim(who), ": duplicate columns"
         error stop msg
      end if
   end do
end do
end subroutine require_unique_labels

integer function find_col_trim(cols, name) result(pos)
! return position of name in cols using trim() equality, or 0 if not found
character(len=*), intent(in) :: cols(:)
character(len=*), intent(in) :: name
integer :: j
pos = 0
do j = 1, size(cols)
   if (trim(cols(j)) == trim(name)) then
      pos = j
      return
   end if
end do
end function find_col_trim

function union_cols(a, b) result(c)
character(len=nlen_columns), intent(in) :: a(:), b(:)
character(len=nlen_columns), allocatable :: c(:)
character(len=nlen_columns), allocatable :: tmp(:)
integer :: n, i
allocate(tmp(size(a) + size(b)))
n = 0
do i = 1, size(a)
   n = n + 1
   tmp(n) = a(i)
end do
do i = 1, size(b)
   if (find_col_trim(tmp(1:n), b(i)) == 0) then
      n = n + 1
      tmp(n) = b(i)
   end if
end do
allocate(c(n))
c = tmp(1:n)
end function union_cols

function intersect_cols(a, b) result(c)
character(len=nlen_columns), intent(in) :: a(:), b(:)
character(len=nlen_columns), allocatable :: c(:)
character(len=nlen_columns), allocatable :: tmp(:)
integer :: n, i
allocate(tmp(size(a)))
n = 0
do i = 1, size(a)
   if (find_col_trim(b, a(i)) /= 0) then
      n = n + 1
      tmp(n) = a(i)
   end if
end do
allocate(c(n))
c = tmp(1:n)
end function intersect_cols

function aligned_binary(self, other, op, how, fill_value) result(res)
! pandas-like aligned arithmetic on union/intersection of index and columns
class(DataFrame_index_date), intent(in) :: self
type(DataFrame_index_date), intent(in)  :: other
character(len=*), intent(in) :: op
character(len=*), intent(in), optional :: how
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: res

character(len=20) :: how0
type(date), allocatable :: idx_out(:)
character(len=nlen_columns), allocatable :: col_out(:)
real(kind=dp), allocatable :: a(:,:), b(:,:)
real(kind=dp) :: fill
logical :: do_fill
integer :: i, j, ii, jj, n1, n2
real(kind=dp) :: x

call require_unique_labels(self, "aligned_binary self")
call require_unique_labels(other, "aligned_binary other")

how0 = trim(default("outer", how))
select case (how0)
case ("outer")
   idx_out = union_index(self%index, other%index)
   col_out = union_cols(self%columns, other%columns)
case ("inner")
   idx_out = intersect_index(self%index, other%index)
   col_out = intersect_cols(self%columns, other%columns)
case ("left")
   idx_out = self%index
   col_out = self%columns
case ("right")
   idx_out = other%index
   col_out = other%columns
case default
   error stop "aligned_binary: how must be outer/inner/left/right"
end select

n1 = size(idx_out)
n2 = size(col_out)

do_fill = present(fill_value)
if (do_fill) then
   fill = fill_value
else
   fill = ieee_value(0.0_dp, ieee_quiet_nan)
end if

allocate(a(n1, n2), b(n1, n2))
a = fill
b = fill

! place self values into aligned array
do i = 1, nrow(self)
   ii = findloc_index(idx_out, self%index(i))
   if (ii <= 0) cycle
   do j = 1, ncol(self)
      jj = find_col_trim(col_out, self%columns(j))
      if (jj <= 0) cycle
      x = self%values(i, j)
      if (do_fill) then
         if (ieee_is_nan(x)) x = fill
      end if
      a(ii, jj) = x
   end do
end do

! place other values into aligned array
do i = 1, nrow(other)
   ii = findloc_index(idx_out, other%index(i))
   if (ii <= 0) cycle
   do j = 1, ncol(other)
      jj = find_col_trim(col_out, other%columns(j))
      if (jj <= 0) cycle
      x = other%values(i, j)
      if (do_fill) then
         if (ieee_is_nan(x)) x = fill
      end if
      b(ii, jj) = x
   end do
end do

allocate(res%index(n1), res%columns(n2), res%values(n1, n2))
res%index = idx_out
res%columns = col_out

select case (trim(op))
case ("+")
   res%values = a + b
case ("-")
   res%values = a - b
case ("*")
   res%values = a * b
case ("/")
   res%values = a / b
case default
   error stop "aligned_binary: invalid op"
end select
end function aligned_binary

function add(self, other, how, fill_value) result(res)
class(DataFrame_index_date), intent(in) :: self
type(DataFrame_index_date), intent(in) :: other
character(len=*), intent(in), optional :: how
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: res
res = aligned_binary(self, other, "+", how, fill_value)
end function add

function subtract(self, other, how, fill_value) result(res)
class(DataFrame_index_date), intent(in) :: self
type(DataFrame_index_date), intent(in) :: other
character(len=*), intent(in), optional :: how
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: res
res = aligned_binary(self, other, "-", how, fill_value)
end function subtract

function multiply(self, other, how, fill_value) result(res)
class(DataFrame_index_date), intent(in) :: self
type(DataFrame_index_date), intent(in) :: other
character(len=*), intent(in), optional :: how
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: res
res = aligned_binary(self, other, "*", how, fill_value)
end function multiply

function divide(self, other, how, fill_value) result(res)
class(DataFrame_index_date), intent(in) :: self
type(DataFrame_index_date), intent(in) :: other
character(len=*), intent(in), optional :: how
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: res
res = aligned_binary(self, other, "/", how, fill_value)
end function divide


pure function shift(self, periods, fill_value) result(df_new)
! shift the values by 'periods' rows (positive periods shifts down).
class(DataFrame_index_date), intent(in) :: self
integer, intent(in), optional :: periods
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: df_new
integer :: p, k, nr, nc
real(kind=dp) :: fill

p = default(1, periods)
fill = default(ieee_value(0.0_dp, ieee_quiet_nan), fill_value)

df_new = self
nr = nrow(self)
nc = ncol(self)
if (nr <= 0 .or. nc <= 0) return

df_new%values = fill
if (p == 0) then
   df_new%values = self%values
else if (p > 0) then
   if (p < nr) df_new%values(p+1:nr,:) = self%values(1:nr-p,:)
else
   k = -p
   if (k < nr) df_new%values(1:nr-k,:) = self%values(k+1:nr,:)
end if
end function shift

pure function pct_change(self, periods) result(df_new)
! percent change (simple return) over 'periods' rows.
class(DataFrame_index_date), intent(in) :: self
integer, intent(in), optional :: periods
type(DataFrame_index_date) :: df_new
type(DataFrame_index_date) :: lag
integer :: p, nr, nc

p = default(1, periods)
lag = self%shift(p)  ! default fill is NaN

df_new%index = self%index
df_new%columns = self%columns
nr = nrow(self)
nc = ncol(self)
allocate(df_new%values(nr, nc))
if (nr == 0 .or. nc == 0) return

df_new%values = self%values/lag%values - 1.0_dp
end function pct_change

pure function log_change(self, periods) result(df_new)
! log change (log return) over 'periods' rows: ln(x(t)/x(t-periods)).
class(DataFrame_index_date), intent(in) :: self
integer, intent(in), optional :: periods
type(DataFrame_index_date) :: df_new
type(DataFrame_index_date) :: lag
integer :: p, nr, nc
real(kind=dp), allocatable :: ratio(:,:)
real(kind=dp) :: nan

p = default(1, periods)
lag = self%shift(p)  ! default fill is NaN

df_new%index = self%index
df_new%columns = self%columns
nr = nrow(self)
nc = ncol(self)
allocate(df_new%values(nr, nc))
nan = ieee_value(0.0_dp, ieee_quiet_nan)
df_new%values = nan
if (nr == 0 .or. nc == 0) return

allocate(ratio(nr, nc))
ratio = self%values/lag%values
where (ratio > 0.0_dp .and. .not. ieee_is_nan(ratio))
   df_new%values = log(ratio)
end where
end function log_change

pure function reindex(self, new_index, method, fill_value) result(df_new)
! return a dataframe with index replaced by new_index and values reindexed.
! method can be: "none" (exact), "ffill" (forward fill), "bfill" (back fill).
class(DataFrame_index_date), intent(in) :: self
type(date), intent(in) :: new_index(:)
character(len=*), intent(in), optional :: method
real(kind=dp), intent(in), optional :: fill_value
type(DataFrame_index_date) :: df_new
character(len=10) :: method_
integer :: i, j, nr_old, nc, pos
real(kind=dp) :: fill
logical :: old_sorted

method_ = "none"
if (present(method)) method_ = adjustl(method)
fill = default(ieee_value(0.0_dp, ieee_quiet_nan), fill_value)

nr_old = nrow(self)
nc = ncol(self)

df_new%index = new_index
df_new%columns = self%columns
allocate(df_new%values(size(new_index), nc))
df_new%values = fill
if (size(new_index) == 0 .or. nc == 0) return
if (nr_old == 0) return

old_sorted = is_sorted_index_array(self%index, ascending=.true.)

do i = 1, size(new_index)
   select case (trim(method_))
   case ("none")
      if (old_sorted) then
         pos = bsearch_exact_index(self%index, new_index(i))
      else
         pos = findloc_index(self%index, new_index(i))
      end if
   case ("ffill")
      if (old_sorted) then
         pos = bsearch_ffill_index(self%index, new_index(i))
      else
         pos = 0
         do j=1,nr_old
            if (self%index(j) <= new_index(i)) then
               if (pos == 0 .or. self%index(j) > self%index(pos)) pos = j
            end if
         end do
      end if
   case ("bfill")
      if (old_sorted) then
         pos = bsearch_bfill_index(self%index, new_index(i))
      else
         pos = 0
         do j=1,nr_old
            if (self%index(j) >= new_index(i)) then
               if (pos == 0 .or. self%index(j) < self%index(pos)) pos = j
            end if
         end do
      end if
   case default
      error stop "in reindex, invalid method"
   end select
   if (pos > 0) df_new%values(i,:) = self%values(pos,:)
end do
end function reindex


subroutine require_same_df(df0, df1, who)
type(DataFrame_index_date), intent(in) :: df0, df1
character(len=*), intent(in) :: who
character(len=200) :: msg
integer :: j
if (nrow(df0) /= nrow(df1)) then
   write(msg,'("in ",a,", nrow mismatch")') trim(who)
   error stop msg
end if
if (ncol(df0) /= ncol(df1)) then
   write(msg,'("in ",a,", ncol mismatch")') trim(who)
   error stop msg
end if
if (any(df0%index /= df1%index)) then
   write(msg,'("in ",a,", index mismatch")') trim(who)
   error stop msg
end if
do j=1,ncol(df0)
   if (trim(df0%columns(j)) /= trim(df1%columns(j))) then
      write(msg,'("in ",a,", columns mismatch")') trim(who)
      error stop msg
   end if
end do
end subroutine require_same_df

function add_df_df(df0, df1) result(res)
type(DataFrame_index_date), intent(in) :: df0
type(DataFrame_index_date), intent(in) :: df1
type(DataFrame_index_date)             :: res
call require_same_df(df0, df1, "add_df_df")
res = df0
if (allocated(res%values)) res%values = df0%values + df1%values
end function add_df_df

function subtract_df_df(df0, df1) result(res)
type(DataFrame_index_date), intent(in) :: df0
type(DataFrame_index_date), intent(in) :: df1
type(DataFrame_index_date)             :: res
call require_same_df(df0, df1, "subtract_df_df")
res = df0
if (allocated(res%values)) res%values = df0%values - df1%values
end function subtract_df_df

function mult_df_df(df0, df1) result(res)
type(DataFrame_index_date), intent(in) :: df0
type(DataFrame_index_date), intent(in) :: df1
type(DataFrame_index_date)             :: res
call require_same_df(df0, df1, "mult_df_df")
res = df0
if (allocated(res%values)) res%values = df0%values * df1%values
end function mult_df_df

function div_df_df(df0, df1) result(res)
type(DataFrame_index_date), intent(in) :: df0
type(DataFrame_index_date), intent(in) :: df1
type(DataFrame_index_date)             :: res
call require_same_df(df0, df1, "div_df_df")
res = df0
if (allocated(res%values)) res%values = df0%values / df1%values
end function div_df_df



elemental function power_df_n(df, n) result(res)
! return df**n element-wise
integer        , intent(in) :: n
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values**n
end function power_df_n

elemental function power_df_x(df, x) result(res)
! return df**x element-wise
real(kind=dp), intent(in)   :: x
type(DataFrame_index_date), intent(in) :: df
type(DataFrame_index_date)             :: res
res = df
if (allocated(res%values)) res%values = res%values**x
end function power_df_x

elemental function subset_stride(df, stride) result(df_new)
type(DataFrame_index_date), intent(in) :: df
integer, intent(in) :: stride
type(DataFrame_index_date) :: df_new
! print*,"df%index(1:nrow(df):stride)", df%index(1:nrow(df):stride)
! print*,"df%values(1:nrow(df):stride, :)", df%values(1:nrow(df):stride, :)
! in the line below, some parentheses are added to work around
! compiler bugs
if (stride == 0) error stop "in subset_stride, stride must nost equal 0"
df_new = DataFrame_index_date(index=(df%index(1:nrow(df):stride)), &
   columns=df%columns, values = (df%values(1:nrow(df):stride, :)))
end function subset_stride
end module dataframe_index_date_mod


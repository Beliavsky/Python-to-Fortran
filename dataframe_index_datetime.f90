! Lightweight companion to dataframe_index_date.f90, mirroring
! dataframe_str_index.f90's minimal-companion approach: self-contained,
! no `use` of the other file's internal modules, to avoid any risk of a
! module-name collision when a program needs both.
!
! For pd.read_csv(..., parse_dates=[idx], index_col=idx) where the index
! column has a time-of-day component (e.g. "2023-03-28 07:05:00"), which
! dataframe_index_date.f90's date type (year/month/day only) can't
! represent. A trailing timezone offset ("-04:00"), "Z", or fractional
! seconds (".123456"), if present, are tolerated but discarded -- treated
! as naive local time, not normalized/compared across zones.
!
! Deliberately minimal, matching dataframe_str_index.f90's scope:
! construction via read_csv, positional iloc-based selection (head/tail),
! shape/nrow/ncol, and printing -- no label-based .loc, no
! DataFrame-DataFrame arithmetic/alignment, no shift/pct_change/reindex.
! date-indexed frames (the common daily-data case) are entirely
! unaffected by this file -- dataframe_index_date.f90 is untouched.
module dataframe_index_datetime_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan
   implicit none
   private

   integer, parameter :: nlen_columns_dt = 100
   integer, parameter :: nrows_print_dt = 10

   type, public :: datetime
      integer :: year = 0
      integer :: month = 0
      integer :: day = 0
      integer :: hour = 0
      integer :: minute = 0
      integer :: second = 0
   contains
      procedure :: to_str => datetime_to_str
   end type datetime

   type, public :: DataFrame_index_datetime
      type(datetime), allocatable :: index(:)
      character(len=nlen_columns_dt), allocatable :: columns(:)
      real(kind=dp), allocatable :: values(:, :)
   contains
      procedure :: read_csv => read_csv_datetime
      procedure :: iloc => iloc_datetime
      procedure :: display => display_datetime
      procedure :: rename_cols => rename_cols_datetime
      procedure :: col_pos => col_pos_datetime
   end type DataFrame_index_datetime

   public :: nrow, ncol, shape, datetime_from_iso, valid

   ! Self-mapped generic interfaces (not plain functions) so a program
   ! that also `use`s dataframe_index_date_mod's own nrow/ncol/shape
   ! (declared the same way there) can import both under their plain
   ! names in the same scope -- see that file's own comment on this.
   interface nrow
      module procedure nrow
   end interface nrow
   interface ncol
      module procedure ncol
   end interface ncol
   interface shape
      module procedure shape
   end interface shape

contains

   function token_is_numeric(tok) result(ok)
      ! Whether a CSV cell parses as a real number -- used by
      ! read_csv_datetime to silently drop a column (e.g. a redundant text
      ! date/label column) that would otherwise crash the unconditional
      ! numeric read of self%values. A blank cell is treated as numeric
      ! (it becomes NaN elsewhere).
      character(len=*), intent(in) :: tok
      logical :: ok
      real(kind=dp) :: tmp
      integer :: ios
      if (len_trim(tok) == 0) then
         ok = .true.
         return
      end if
      read (tok, *, iostat=ios) tmp
      ok = (ios == 0)
   end function token_is_numeric

   pure function datetime_to_str(this) result(s) ! return "yyyy-mm-dd hh:mm:ss"
      class(datetime), intent(in) :: this
      character(len=19) :: s
      s = zero_pad_4_dt(this%year)//'-'//zero_pad_2_dt(this%month)//'-'//zero_pad_2_dt(this%day)// &
          ' '//zero_pad_2_dt(this%hour)//':'//zero_pad_2_dt(this%minute)//':'//zero_pad_2_dt(this%second)
   end function datetime_to_str

   pure elemental logical function valid(x) ! return true if the datetime is valid
      type(datetime), intent(in) :: x
      valid = .false.
      if (x%month < 1 .or. x%month > 12) return
      if (x%day < 1 .or. x%day > days_in_month_dt(x%year, x%month)) return
      if (x%hour < 0 .or. x%hour > 23) return
      if (x%minute < 0 .or. x%minute > 59) return
      if (x%second < 0 .or. x%second > 59) return
      valid = .true.
   end function valid

   pure elemental integer function days_in_month_dt(year, month)
      integer, intent(in) :: year, month
      select case (month)
      case (1, 3, 5, 7, 8, 10, 12)
         days_in_month_dt = 31
      case (4, 6, 9, 11)
         days_in_month_dt = 30
      case (2)
         if ((mod(year, 4) == 0 .and. mod(year, 100) /= 0) .or. mod(year, 400) == 0) then
            days_in_month_dt = 29
         else
            days_in_month_dt = 28
         end if
      case default
         days_in_month_dt = 0
      end select
   end function days_in_month_dt

   pure function datetime_from_iso(s) result(x)
      ! convert "yyyy-mm-dd hh:mm:ss" (a "T" separator is also accepted, and
      ! any trailing text -- a timezone offset, "Z", fractional seconds --
      ! is ignored) to a datetime.
      character(len=*), intent(in) :: s
      type(datetime) :: x
      character(len=len(s)) :: t
      integer :: y, mo, d, h, mi, se
      logical :: ok1, ok2, ok3, ok4, ok5, ok6

      x = datetime(0, 0, 0, 0, 0, 0)
      t = adjustl(s)
      if (len_trim(t) < 19) return
      if (t(5:5) /= '-' .or. t(8:8) /= '-') return
      if (t(11:11) /= ' ' .and. t(11:11) /= 'T') return
      if (t(14:14) /= ':' .or. t(17:17) /= ':') return
      call parse_uint_dt(t(1:4), y, ok1)
      call parse_uint_dt(t(6:7), mo, ok2)
      call parse_uint_dt(t(9:10), d, ok3)
      call parse_uint_dt(t(12:13), h, ok4)
      call parse_uint_dt(t(15:16), mi, ok5)
      call parse_uint_dt(t(18:19), se, ok6)
      if (.not. (ok1 .and. ok2 .and. ok3 .and. ok4 .and. ok5 .and. ok6)) return
      x = datetime(y, mo, d, h, mi, se)
   end function datetime_from_iso

   pure function zero_pad_2_dt(n) result(s)
      integer, intent(in) :: n
      character(len=2) :: s
      if (n < 0 .or. n > 99) then
         s = '**'
         return
      end if
      s(1:1) = achar(iachar('0') + n/10)
      s(2:2) = achar(iachar('0') + mod(n, 10))
   end function zero_pad_2_dt

   pure function zero_pad_4_dt(n) result(s)
      integer, intent(in) :: n
      character(len=4) :: s
      integer :: m
      if (n < 0 .or. n > 9999) then
         s = '****'
         return
      end if
      m = n
      s(4:4) = achar(iachar('0') + mod(m, 10)); m = m/10
      s(3:3) = achar(iachar('0') + mod(m, 10)); m = m/10
      s(2:2) = achar(iachar('0') + mod(m, 10)); m = m/10
      s(1:1) = achar(iachar('0') + mod(m, 10))
   end function zero_pad_4_dt

   pure subroutine parse_uint_dt(s, n, ok)
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
   end subroutine parse_uint_dt

   subroutine split_string_dt(str, delim, tokens)
      character(len=*), intent(in) :: str
      character(len=*), intent(in) :: delim
      character(:), allocatable, intent(out) :: tokens(:)
      integer :: start, pos, i, count, n

      n = len_trim(str)
      if (n == 0) then
         allocate (character(len=0) :: tokens(1))
         tokens(1) = ""
         return
      end if

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

      allocate (character(len=n) :: tokens(count))

      start = 1
      i = 1
      do
         pos = index(str(start:), delim)
         if (pos == 0) then
            tokens(i) = adjustl(str(start:))
            exit
         else
            tokens(i) = adjustl(str(start:start + pos - 2))
            start = start + pos
            i = i + 1
         end if
      end do
   end subroutine split_string_dt

   pure function shape(df) result(ishape)
      type(DataFrame_index_datetime), intent(in) :: df
      integer :: ishape(2)
      ishape = [nrow(df), ncol(df)]
   end function shape

   elemental function nrow(df) result(num_rows)
      type(DataFrame_index_datetime), intent(in) :: df
      integer :: num_rows
      if (allocated(df%values)) then
         num_rows = size(df%values, 1)
      else
         num_rows = -1
      end if
   end function nrow

   elemental function ncol(df) result(num_col)
      type(DataFrame_index_datetime), intent(in) :: df
      integer :: num_col
      if (allocated(df%values)) then
         num_col = size(df%values, 2)
      else
         num_col = -1
      end if
   end function ncol

   function iloc_datetime(self, rows, cols) result(df_new)
      ! positional selection by row/column positions (1-based) -- no
      ! label-based .loc/select in this minimal companion.
      class(DataFrame_index_datetime), intent(in) :: self
      integer, intent(in), optional :: rows(:)
      integer, intent(in), optional :: cols(:)
      type(DataFrame_index_datetime) :: df_new
      integer, allocatable :: i_keep(:), j_keep(:)
      integer :: k

      if (present(rows)) then
         i_keep = rows
         do k = 1, size(i_keep)
            if (i_keep(k) < 1 .or. i_keep(k) > nrow(self)) error stop "iloc: row position out of range"
         end do
      else
         i_keep = [(k, k=1, nrow(self))]
      end if
      if (present(cols)) then
         j_keep = cols
         do k = 1, size(j_keep)
            if (j_keep(k) < 1 .or. j_keep(k) > ncol(self)) error stop "iloc: column position out of range"
         end do
      else
         j_keep = [(k, k=1, ncol(self))]
      end if
      df_new = DataFrame_index_datetime( &
                index=self%index(i_keep), columns=self%columns(j_keep), values=self%values(i_keep, j_keep))
   end function iloc_datetime

   !------------------------------------------------------------------
   ! read_csv: same format/conventions as dataframe_index_date.f90's --
   ! see that file's read_csv for the fuller comment. Header row begins
   ! with an empty token (before the first comma).
   !------------------------------------------------------------------
   subroutine read_csv_datetime(self, filename, max_col, max_rows, usecols, skiprows)
      class(DataFrame_index_datetime), intent(inout) :: self
      character(len=*), intent(in) :: filename
      integer, intent(in), optional :: max_col, max_rows, skiprows
      character(len=*), intent(in), optional :: usecols(:)
      integer :: io, unit, i, j, k, nrows, ncols, ncols_file
      integer, allocatable :: col_map(:)
      logical :: keep
      character(len=1024) :: line
      character(:), allocatable :: tokens(:), probe_tokens(:)
      type(datetime) :: idx

      if (allocated(self%index)) deallocate (self%index)
      if (allocated(self%columns)) deallocate (self%columns)
      if (allocated(self%values)) deallocate (self%values)

      open (newunit=unit, file=filename, status='old', action='read', iostat=io)
      if (io /= 0) error stop "Error opening file in read_csv"

      if (present(skiprows)) then
         do i = 1, skiprows
            read (unit, '(A)', iostat=io) line
            if (io /= 0) error stop "Error skipping rows in read_csv"
         end do
      end if

      read (unit, '(A)', iostat=io) line
      if (io /= 0) error stop "Error reading header line in read_csv"

      call split_string_dt(line, ",", tokens)
      ncols_file = size(tokens) - 1
      if (present(max_col)) ncols_file = min(ncols_file, max_col)
      if (ncols_file <= 0) error stop "No columns detected in header in read_csv"

      allocate (col_map(ncols_file))
      ncols = 0
      do i = 1, ncols_file
         keep = .true.
         if (present(usecols)) then
            keep = .false.
            do k = 1, size(usecols)
               if (trim(tokens(i + 1)) == trim(usecols(k))) then
                  keep = .true.
                  exit
               end if
            end do
         end if
         if (keep) then
            ncols = ncols + 1
            col_map(ncols) = i
         end if
      end do
      if (ncols <= 0) error stop "No columns selected in read_csv"

      ! Some selected columns (e.g. a text column duplicating the index in
      ! a different format) may not be numeric -- probe the first data
      ! row and drop any such column, since self%values only supports
      ! real data. Matches pandas loosely: an unusable column is dropped
      ! instead of crashing, though pandas would keep it with an object
      ! dtype.
      read (unit, '(A)', iostat=io) line
      if (io == 0 .and. trim(line) /= "") then
         call split_string_dt(line, ",", probe_tokens)
         k = 0
         do i = 1, ncols
            if (token_is_numeric(trim(probe_tokens(col_map(i) + 1)))) then
               k = k + 1
               col_map(k) = col_map(i)
            end if
         end do
         ncols = k
         if (ncols <= 0) error stop "No numeric columns selected in read_csv"
      end if

      allocate (self%columns(ncols))
      do i = 1, ncols
         self%columns(i) = tokens(col_map(i) + 1)
      end do

      rewind (unit)
      if (present(skiprows)) then
         do i = 1, skiprows
            read (unit, '(A)')
         end do
      end if
      read (unit, '(A)')

      nrows = 0
      do
         if (present(max_rows)) then
            if (nrows >= max_rows) exit
         end if
         read (unit, '(A)', iostat=io) line
         if (io /= 0 .or. trim(line) == "") exit
         nrows = nrows + 1
      end do
      if (nrows == 0) error stop "No data lines detected in read_csv"

      rewind (unit)
      if (present(skiprows)) then
         do i = 1, skiprows
            read (unit, '(A)')
         end do
      end if
      read (unit, '(A)')

      allocate (self%index(nrows), self%values(nrows, ncols))
      do i = 1, nrows
         read (unit, '(A)', iostat=io) line
         if (io /= 0) error stop "Error reading data row in read_csv"
         if (trim(line) == "") exit
         call split_string_dt(line, ",", tokens)
         idx = datetime_from_iso(trim(tokens(1)))
         if (.not. valid(idx)) error stop "Invalid datetime in first column in read_csv"
         self%index(i) = idx
         do j = 1, ncols
            if (len_trim(tokens(col_map(j) + 1)) == 0) then
               self%values(i, j) = ieee_value(1.0_dp, ieee_quiet_nan)
            else
               read (tokens(col_map(j) + 1), *) self%values(i, j)
            end if
         end do
      end do

      close (unit)
   end subroutine read_csv_datetime

   subroutine rename_cols_datetime(self, old, new)
      ! rename columns: replace each old(i) with new(i). Ported from
      ! dataframe_index_date.f90's rename_cols, minus its optional
      ! `missing` argument (unconditionally errors on an unknown column,
      ! since no translated caller passes missing= yet) to keep this file
      ! self-contained (no util_mod default()/str_lower() dependency).
      class(DataFrame_index_datetime), intent(inout) :: self
      character(len=*), intent(in) :: old(:), new(:)
      integer :: k, j
      character(len=nlen_columns_dt) :: key

      if (size(old) /= size(new)) error stop "rename_cols: size(old) /= size(new)"

      do k = 1, size(old)
         key = trim(old(k))
         j = findloc(self%columns, key, dim=1)
         if (j <= 0) error stop "rename_cols: column not found: "//trim(old(k))
         self%columns(j) = trim(new(k))
      end do
   end subroutine rename_cols_datetime

   pure function col_pos_datetime(self, column) result(jcol)
      ! return the column position (1..ncol) for column name. Ported from
      ! dataframe_index_date.f90's col_pos.
      class(DataFrame_index_datetime), intent(in) :: self
      character(len=*), intent(in) :: column
      integer :: jcol
      jcol = findloc(self%columns, column, dim=1)
      if (jcol == 0) error stop "in col_pos, column not found: "//trim(column)
   end function col_pos_datetime

   ! pandas-style print(df): index label (yyyy-mm-dd hh:mm:ss) + one
   ! right-justified column per %columns entry, computed at runtime --
   ! see dataframe_str_index.f90's display_str_index for the same idea.
   subroutine display_datetime(self, ndigits)
      class(DataFrame_index_datetime), intent(in) :: self
      integer, intent(in), optional :: ndigits
      integer :: nd, col_width, n_cols, pdf_n, pdf_i
      character(len=:), allocatable :: header_fmt, row_fmt, dots_fmt
      character(len=32) :: nc_str, cw_str, nd_str

      nd = 6
      if (present(ndigits)) nd = ndigits
      col_width = max(10, nd + 8)
      n_cols = size(self%columns)
      pdf_n = nrow(self)

      write (nc_str, '(I0)') n_cols
      write (cw_str, '(I0)') col_width
      write (nd_str, '(I0)') nd

      header_fmt = '(A19,'//trim(nc_str)//'A'//trim(cw_str)//')'
      row_fmt = '(A19,'//trim(nc_str)//'F'//trim(cw_str)//'.'//trim(nd_str)//')'
      dots_fmt = '(A19,'//trim(nc_str)//'A'//trim(cw_str)//')'

      write (*, header_fmt) '', (trim(self%columns(pdf_i)), pdf_i=1, n_cols)
      if (pdf_n <= 10) then
         do pdf_i = 1, pdf_n
            write (*, row_fmt) self%index(pdf_i)%to_str(), self%values(pdf_i, :)
         end do
      else
         do pdf_i = 1, 5
            write (*, row_fmt) self%index(pdf_i)%to_str(), self%values(pdf_i, :)
         end do
         write (*, dots_fmt) '...', ('...', pdf_i=1, n_cols)
         do pdf_i = pdf_n - 4, pdf_n
            write (*, row_fmt) self%index(pdf_i)%to_str(), self%values(pdf_i, :)
         end do
      end if
      write (*, *)
      write (*, '(A,I0,A,I0,A)') '[', pdf_n, ' rows x ', n_cols, ' columns]'
   end subroutine display_datetime

end module dataframe_index_datetime_mod

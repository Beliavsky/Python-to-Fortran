! Lightweight companion to dataframe_index_date.f90 for xp2f.py's
! pd.DataFrame({"col1": arr1, "col2": arr2, ...}, index=str_labels) support --
! a DataFrame whose row index is a plain string label (e.g. a component
! name), not a date. Deliberately minimal: only what xmix.py-style code
! needs (construction from named real-array columns, subtraction between
! two same-shape frames, and printing) -- see dataframe_index_date.f90 for
! the much larger date-indexed sibling this mirrors the nrow/ncol/operator(-)
! naming conventions of.
module dataframe_str_index_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none
   private

   integer, parameter :: nlen_label_str = 64
   integer, parameter :: nlen_columns_str = 64

   type, public :: DataFrame_str_index
      character(len=nlen_label_str), allocatable :: index(:)
      character(len=nlen_columns_str), allocatable :: columns(:)
      real(kind=dp), allocatable :: values(:, :)
   contains
      procedure :: display => display_str_index
   end type DataFrame_str_index

   public :: nrow, ncol
   public :: operator(-)

   interface operator(-)
      module procedure subtract_df_df_str
   end interface

contains

   elemental function nrow(df) result(num_rows)
      type(DataFrame_str_index), intent(in) :: df
      integer :: num_rows
      if (allocated(df%values)) then
         num_rows = size(df%values, 1)
      else
         num_rows = -1
      end if
   end function nrow

   elemental function ncol(df) result(num_col)
      type(DataFrame_str_index), intent(in) :: df
      integer :: num_col
      if (allocated(df%values)) then
         num_col = size(df%values, 2)
      else
         num_col = -1
      end if
   end function ncol

   pure function subtract_df_df_str(a, b) result(c)
      type(DataFrame_str_index), intent(in) :: a, b
      type(DataFrame_str_index) :: c
      c%index = a%index
      c%columns = a%columns
      c%values = a%values - b%values
   end function subtract_df_df_str

   ! pandas-style print(df): index label + one right-justified column per
   ! %columns entry (read at runtime, not baked into a literal format string
   ! per call site -- see xp2f.py's _emit_pandas_df_print, which used to
   ! inline this whole block at every print(df) call).
   subroutine display_str_index(self, ndigits)
      class(DataFrame_str_index), intent(in) :: self
      integer, intent(in), optional :: ndigits
      integer :: nd, col_width, idx_width, n_cols, pdf_n, pdf_i
      character(len=:), allocatable :: header_fmt, row_fmt, dots_fmt
      character(len=32) :: nc_str, cw_str, iw_str, nd_str

      nd = 6
      if (present(ndigits)) nd = ndigits
      col_width = max(10, nd + 8)
      idx_width = 24
      n_cols = size(self%columns)
      pdf_n = nrow(self)

      write (nc_str, '(I0)') n_cols
      write (cw_str, '(I0)') col_width
      write (iw_str, '(I0)') idx_width
      write (nd_str, '(I0)') nd

      header_fmt = '(A'//trim(iw_str)//','//trim(nc_str)//'A'//trim(cw_str)//')'
      row_fmt = '(A'//trim(iw_str)//','//trim(nc_str)//'F'//trim(cw_str)//'.'//trim(nd_str)//')'
      dots_fmt = '(A'//trim(iw_str)//','//trim(nc_str)//'A'//trim(cw_str)//')'

      write (*, header_fmt) '', (trim(self%columns(pdf_i)), pdf_i=1, n_cols)
      if (pdf_n <= 10) then
         do pdf_i = 1, pdf_n
            write (*, row_fmt) trim(self%index(pdf_i)), self%values(pdf_i, :)
         end do
      else
         do pdf_i = 1, 5
            write (*, row_fmt) trim(self%index(pdf_i)), self%values(pdf_i, :)
         end do
         write (*, dots_fmt) '...', ('...', pdf_i=1, n_cols)
         do pdf_i = pdf_n - 4, pdf_n
            write (*, row_fmt) trim(self%index(pdf_i)), self%values(pdf_i, :)
         end do
      end if
      write (*, *)
      write (*, '(A,I0,A,I0,A)') '[', pdf_n, ' rows x ', n_cols, ' columns]'
   end subroutine display_str_index

end module dataframe_str_index_mod

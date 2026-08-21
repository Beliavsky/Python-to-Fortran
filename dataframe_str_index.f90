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

end module dataframe_str_index_mod

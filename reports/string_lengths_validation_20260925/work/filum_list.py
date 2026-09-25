def filename_inc ( filename ):

#*****************************************************************************80
#
## filename_inc() generates the next filename in a series.
#
#  Discussion:
#
#    It is assumed that the digits in the name, whether scattered or
#    connected, represent a number that is to be increased by 1 on
#    each call.  If this number is all 9's on input, the output number
#    is all 0's.  Non-numeric letters of the name are unaffected..
#
#    If the name is empty, then the routine stops.
#
#    If the name contains no digits, the empty string is returned.
#
#  Example:
#
#      Input            Output
#      -----            ------
#      'a7to11.txt'     'a7to12.txt'  (typical case.  Last digit incremented)
#      'a7to99.txt'     'a8to00.txt'  (last digit incremented, with carry.)
#      'a9to99.txt'     'a0to00.txt'  (wrap around)
#      'cat.txt'        ' '           (no digits in input name.)
#      ' '              STOP!         (error.)
#
#  Licensing:
#
#    This code is distributed under the MIT license.
#
#  Modified:
#
#    10 February 2010
#
#  Author:
#
#    John Burkardt
#
#  Input:
#
#    string FILENAME, the string to be incremented.
#
#  Output:
#
#    string FILENAME, the incremented string.
#
  i0 = ord ( '0' )
  i8 = ord ( '8' )
  i9 = ord ( '9' )

  lens = len ( filename )

  if ( lens <= 0 ):
    return None

  change = 0
  filename2 = ''

  for i in range ( lens - 1, -1, -1 ):

    c = filename[i]

    ic = ord ( c )

    if ( change < 2 and i0 <= ic and ic <= i8 ):
      ic = ic + 1
      filename2 = chr ( ic ) + filename2
      change = 2
    elif ( change == 0 and ic == i9 ):
      change = 1
      c = '0'
      filename2 = c + filename2
    else:
      filename2 = c + filename2

  if ( change == 0 ):
    filename2 = None

  return filename2
for filename in ['', 'cat.txt', 'file072.dat', 'a7to99.txt', 'a9to99.txt', '2cat9.dat  ', 'fred99.txt ']:
    result = filename_inc(filename)
    print(result, result is None)
    if result is not None:
        print(len(result))
        print('[', result, ']', sep='')
        for i in range(len(result)):
            print(ord(result[i]))

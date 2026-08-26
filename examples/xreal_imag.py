from numpy import imag, real, array

if __name__ == '__main__':
    arr1 = array([1+1j,2+1j,3+1j,4+1j])
    real_part = real(arr1)
    imag_part = imag(arr1)
    print("real part for arr1: " , real_part, "\nimag part for arr1: ", imag_part)

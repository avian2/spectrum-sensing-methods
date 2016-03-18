import numpy as np
from numpy.lib.stride_tricks import as_strided

def sliding_window(x, w, s):
	
	shape = ((x.shape[0] - w) / s + 1, w)
	strides = (x.strides[0]*s, x.strides[0])
	
	return as_strided(x, shape, strides)

def fam(x, Np, L, N=None):
	
	# input channelization
	xs = sliding_window(x, Np, L)
	
	if N is None:
		Pe = int(np.floor(int(np.log(xs.shape[0])/np.log(2))))
		P = 2**Pe
		N = L*P
	else:
		P = N/L
		
	xs2 = xs[0:P,:]
	
	# windowing
	
	w = np.hamming(Np)
	w /= np.sqrt(np.sum(w**2))

	xw = xs2 * np.tile(w, (P,1))

	del xs2
	del w
	
	# first FFT
	
	XF1 = np.fft.fft(xw, axis=1)
	XF1 = np.fft.fftshift(XF1, axes=1)

	del xw
	
	# calculating complex demodulates
	
	f = np.arange(Np)/float(Np) - .5
	t = np.arange(P)*L

	f = np.tile(f, (P,1))
	t = np.tile(t.reshape(P,1), (1, Np))

	XD = XF1
	XD *= np.exp(-1j*2*np.pi*f*t)

	# calculating conjugate products, second FFT and the final matrix
	Sx = np.zeros((Np, 2*N), dtype=complex)
	Mp = N/Np/2

	for k in range(Np):
		for l in range(Np):
			XF2 = np.fft.fft(XD[:,k]*np.conjugate(XD[:,l]))
			XF2 = np.fft.fftshift(XF2)
			XF2 /= P

			i = (k+l)/2.
			a = ((k-l)/float(Np) + 1.)*N
			Sx[i,a-Mp:a+Mp] = XF2[P/2-Mp:P/2+Mp]

	return Sx

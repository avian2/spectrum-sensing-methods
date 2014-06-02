from vesna.rftest import usbtmc
import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy
import scipy.linalg

class MeasurementProcess(Process):
	def __init__(self, inp):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue(maxsize=2)

		self.gen = usbtmc("/dev/usbtmc3")

	def usrp_measure(self, N, fc, fs, Pgen):

		self.gen.write("freq %d Hz\n" % (fc+fs/4,))

		if Pgen is None:
			self.gen.write("outp off\n")
		else:
			self.gen.write("pow %.1f dBm\n" % (Pgen,))
			self.gen.write("outp on\n")

		handle, path = tempfile.mkstemp()
		os.close(handle)

		args = ["uhd_rx_cfile", "-v",
				"--freq=%d" % (fc,),
				"--nsamples=%d" % (N,),
				"--samp-rate=%f" % (fs,),
				"-ATX/RX",
				path]

		subprocess.check_call(args)

		self.gen.write("outp off\n")

		return path

	def run(self):
		while True:
			kwargs = self.inp.get()
			if kwargs is None:
				return

			kwargs['path'] = self.usrp_measure(**kwargs)
			self.out.put(kwargs)

class GammaProcess(Process):
	def __init__(self, inp, Ns, func):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue()

		self.Ns = Ns
		self.func = func

	def run(self):
		while True:
			kwargs = self.inp.get()
			if kwargs is None:
				return

			path = kwargs.pop('path')

			xl = numpy.fromfile(path,
					dtype=numpy.dtype(numpy.complex64))

			N = len(xl)
			jl = range(0, N, self.Ns)

			Np = len(jl)
			gammal = numpy.empty(Np)

			for i, j in enumerate(jl):
				x = xl.real[j:j+self.Ns]
				gammal[i] = self.func(x)

			os.unlink(path)

			kwargs['gammal'] = gammal
			self.out.put(kwargs)

class EnergyDetector:
	SLUG = 'ed'

	def __init__(self):
		pass

	def __call__(self, x):
		return numpy.sum(x**2)

class CAVDetector:
	SLUG = 'cav'

	def __init__(self, L=10):
		self.L = L

	def __call__(self, x):
		L = self.L
		Ns = len(x)

		lbd = numpy.empty(L)
		for l in xrange(L):
			if l > 0:
				xu = x[:-l]
			else:
				xu = x

			lbd[l] = numpy.dot(xu, x[l:])/(Ns-l)

		R = scipy.linalg.toeplitz(lbd)

		T1 = numpy.sum(numpy.abs(R))/L
		T2 = numpy.abs(lbd[0])

		return T1/T2

def main():
	fc = 864e6
	fs = 1e6

	Ns = 25000
	Np = 1000

	inp = Queue()

	mp = MeasurementProcess(inp)
	mp.start()

	#det = EnergyDetector()
	det = CAVDetector()

	gp = GammaProcess(mp.out, Ns, det)
	gp.start()

	Pgenl = [None] + range(-1100, -750, 10)

	for Pgen in Pgenl:
		inp.put({'N': Ns*Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen/10. if Pgen is not None else None})

	path = '../measurements/usrp/usrp_%s_' % (det.SLUG,)

	for Pgen in Pgenl:
		kwargs = gp.out.get()

		if kwargs['Pgen'] is None:
			n = path + 'off.dat'
		else:
			m = '%.1f' % (kwargs['Pgen'],)
			m = m.replace('-','m')
			m = m.replace('.','_')

			n = path + '%sdbm.dat' % (m,)

		numpy.savetxt(n, kwargs['gammal'])

	mp.inp.put(None)
	mp.join()

	gp.inp.put(None)
	gp.join()

main()

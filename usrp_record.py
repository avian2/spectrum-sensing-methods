from vesna.rftest import usbtmc
import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy
import numpy.linalg
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

class CovarianceDetector:
	def __init__(self, L=10):
		self.L = L

	def R(self, x):
		x0 = x - numpy.mean(x)

		L = self.L
		Ns = len(x0)

		lbd = numpy.empty(L)
		for l in xrange(L):
			if l > 0:
				xu = x0[:-l]
			else:
				xu = x0

			lbd[l] = numpy.dot(xu, x0[l:])/(Ns-l)

		return scipy.linalg.toeplitz(lbd)

class CAVDetector(CovarianceDetector):
	SLUG = 'cav'

	def __call__(self, x):
		R = self.R(x)
		T1 = numpy.sum(numpy.abs(R))/self.L
		T2 = numpy.abs(R[0,0])
		return T1/T2

class CFNDetector(CovarianceDetector):
	SLUG = 'cfn'

	def __call__(self, x):
		R = self.R(x)
		T1 = numpy.sum(R**2.)/self.L
		T2 = R[0,0]**2.
		return T1/T2

class MACDetector(CovarianceDetector):
	SLUG = 'mac'

	def __call__(self, x):
		R = self.R(x)

		T1 = numpy.max(numpy.abs(R[0,1:]))
		T2 = numpy.abs(R[0,0])
		return T1/T2

class EigenvalueDetector(CovarianceDetector):
	def lbd(self, x):
		R = self.R(x)

		lbd = numpy.linalg.eigvalsh(R)
		return lbd.real

class MMEDetector(EigenvalueDetector):
	SLUG = 'mme'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return lbd[-1]/lbd[0]

class EMEDetector(EigenvalueDetector):
	SLUG = 'eme'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return numpy.sum(x**2)/lbd[0]

class AGMDetector(EigenvalueDetector):
	SLUG = 'agm'

	def __call__(self, x):
		lbd = self.lbd(x)

		return numpy.mean(lbd)/(numpy.prod(lbd)**(1/len(lbd)))

class METDetector(EigenvalueDetector):
	SLUG = 'met'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return lbd[-1]/numpy.sum(lbd)

def do_campaign(det, fs, name):
	fc = 864e6

	Ns = 25000
	Np = 1000

	inp = Queue()

	mp = MeasurementProcess(inp)
	mp.start()

	gp = GammaProcess(mp.out, Ns, det)
	gp.start()

	Pgenl = [None] + range(-1000, -700, 10)

	for Pgen in Pgenl:
		inp.put({'N': Ns*Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen/10. if Pgen is not None else None})

	path = '../measurements/usrp/usrp_fs%dmhz_%s_%s_' % (fs/1e6, det.SLUG, name)

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

def main():

	for fs in [1e6, 2e6, 10e6]:
		for L in xrange(5, 25, 5):
			for cls in [MMEDetector, EMEDetector, AGMDetector, METDetector]:
				det = cls(L=L)
				do_campaign(det, fs=fs, name="l%d" % (L,))

main()

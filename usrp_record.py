from vesna.rftest import usbtmc
import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy

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
			self.gen.write("pow %d dBm\n" % (Pgen,))
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
	def __init__(self):
		pass

	def __call__(self, x):
		return numpy.sum(x**2)

def main():
	fc = 864e6
	fs = 1e6

	Ns = 25000
	Np = 1000

	inp = Queue()

	mp = MeasurementProcess(inp)
	mp.start()

	gp = GammaProcess(mp.out, Ns, EnergyDetector())
	gp.start()

	Pgenl = [None] + range(-100, -10, 1)

	for Pgen in Pgenl:
		inp.put({'N': Ns*Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen})

	path = '../measurements/usrp/'

	for Pgen in Pgenl:
		kwargs = gp.out.get()

		if kwargs['Pgen'] is None:
			n = path + 'usrp_off.dat'
		else:
			n = path + 'usrp_%ddbm.dat' % (kwargs['Pgen'],)
			n = n.replace('-','m')

		numpy.savetxt(n, kwargs['gammal'])

	mp.inp.put(None)
	mp.join()

	gp.inp.put(None)
	gp.join()

main()

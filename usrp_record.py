from vesna.rftest import usbtmc
import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy
from sensing.methods import *

class GeneratorControl: pass

class IEEEMicSoftSpeaker(GeneratorControl):
	def __init__(self, path="/dev/usbtmc3"):
		self.gen = usbtmc(path)

	def set(self, f, P):

		self.gen.write("freq %d Hz\n" % (f,))

		if P is None:
			self.gen.write("outp off\n")
		else:
			self.gen.write("pow %.1f dBm\n" % (P,))
			self.gen.write("outp on\n")

	def off(self):
		self.gen.write("outp off\n")

class MeasurementProcess(Process):
	def __init__(self, genc, inp):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue(maxsize=2)
		self.genc = genc

	def usrp_measure(self, N, fc, fs, Pgen):

		self.genc.set(fc+fs/4, Pgen)

		handle, path = tempfile.mkstemp()
		os.close(handle)

		args = ["uhd_rx_cfile", "-v",
				"--freq=%d" % (fc,),
				"--nsamples=%d" % (N,),
				"--samp-rate=%f" % (fs,),
				"-ATX/RX",
				path]

		subprocess.check_call(args)

		self.genc.off()

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

		try:
			self.func = tuple(func)
		except TypeError:
			self.func = (func,)

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
			gammal = numpy.empty(shape=(len(self.func), Np))

			for k, func in enumerate(self.func):
				for i, j in enumerate(jl):
					x = xl.real[j:j+self.Ns]
					gammal[k, i] = func(x)

			os.unlink(path)

			kwargs['gammal'] = gammal
			self.out.put(kwargs)

def do_campaign(genc, det, fs, Ns):
	fc = 864e6

	Np = 1000

	inp = Queue()

	mp = MeasurementProcess(genc, inp)
	mp.start()

	gp = GammaProcess(mp.out, Ns, (d for d, name in det))
	gp.start()

	Pgenl = [None] + range(-1000, -700, 10)

	for Pgen in Pgenl:
		inp.put({'N': Ns*Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen/10. if Pgen is not None else None})

	for Pgen in Pgenl:
		kwargs = gp.out.get()

		if kwargs['Pgen'] is None:
			suf = 'off.dat'
		else:
			m = '%.1f' % (kwargs['Pgen'],)
			m = m.replace('-','m')
			m = m.replace('.','_')

			suf = '%sdbm.dat' % (m,)

		for i, (d, name) in enumerate(det):
			path = '../measurements/usrp3/usrp_fs%dmhz_Ns%dks_' % (fs/1e6, Ns/1000)
			path += '%s_' % (d.SLUG,)
			if name:
				path += name + "_"

			path += suf

			numpy.savetxt(path, kwargs['gammal'][i,:])

	mp.inp.put(None)
	mp.join()

	gp.inp.put(None)
	gp.join()

def main():
	genc = IEEEMicSoftSpeaker()

	det = [	(EnergyDetector(), None) ]

	cls = [	CAVDetector,
		CFNDetector,
		MACDetector,
		MMEDetector,
		EMEDetector,
		AGMDetector,
		METDetector ]

	for L in xrange(5, 25, 5):
		for c in cls:
			det.append((c(L=L), "l%d" % (L,)))

	for fs, Ns in [	(1e6, 25000),
			#(2e6, 25000),
			#(10e6, 100000),
			]:
		do_campaign(genc, det, fs=fs, Ns=Ns)

main()

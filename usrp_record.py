import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy
from sensing.methods import *
from sensing.signals import *

class MeasurementProcess(Process):
	def __init__(self, genc, inp, extra=250000):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue(maxsize=2)
		self.genc = genc

		self.extra = extra

	def usrp_measure(self, N, fc, fs, Pgen):

		self.genc.set(fc+fs/4, Pgen)

		handle, path = tempfile.mkstemp(dir="/tmp/mem")
		os.close(handle)

		args = ["uhd_rx_cfile", "-v",
				"--freq=%d" % (fc,),
				"--nsamples=%d" % (N + self.extra,),
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
	def __init__(self, inp, Ns, func, extra=250000):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue()

		self.Ns = Ns
		self.extra = extra

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

			# skip leading samples - they are typically not useful
			# because they happen while ADC is settling in the receiver
			# and other transition effects.
			xl = xl[self.extra:]

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

def do_campaign(genc, det, fs, Ns, Pgenl, out_path):
	fc = 864e6

	Np = 1000

	extra = Ns*5

	inp = Queue()

	mp = MeasurementProcess(genc, inp, extra=extra)
	mp.start()

	gp = GammaProcess(mp.out, Ns, (d for d, name in det), extra=extra)
	gp.start()

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
			path = '%s/usrp_%s_fs%dmhz_Ns%dks_' % (
					out_path, genc.SLUG, fs/1e6, Ns/1000)
			path += '%s_' % (d.SLUG,)
			if name:
				path += name + "_"

			path += suf

			numpy.savetxt(path, kwargs['gammal'][i,:])

	mp.inp.put(None)
	mp.join()

	gp.inp.put(None)
	gp.join()

def do_campaign_generator(genc, Pgenl):

	out_path = "../measurements/sneismtv"
	try:
		os.mkdir(out_path)
	except OSError:
		pass

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
			(2e6, 25000),
			(10e6, 100000),
			]:
		do_campaign(genc, det, fs=fs, Ns=Ns, Pgenl=Pgenl, out_path=out_path)

def main():
	genc = IEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)

	do_campaign_generator(genc, Pgenl)

	genc = Noise()
	Pgenl = [None] + range(-700, -100, 20)

	do_campaign_generator(genc, Pgenl)

main()

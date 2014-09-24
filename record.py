import subprocess
import datetime
from multiprocessing import Process, Queue
import os
import tempfile
import numpy
from sensing.methods import *
from sensing.signals import *
import sys

TEMPDIR="/tmp/mem"

class MeasurementProcess(Process):
	def __init__(self, genc, inp, extra=250000):
		Process.__init__(self)

		self.inp = inp
		self.out = Queue(maxsize=2)
		self.genc = genc

		self.extra = extra

		self.setup()

	def setup(self):
		pass

	def run(self):
		while True:
			kwargs = self.inp.get()
			if kwargs is None:
				return

			kwargs['path'] = self.measure(**kwargs)
			self.out.put(kwargs)

class USRPMeasurementProcess(MeasurementProcess):

	SLUG = "usrp"

	def measure(self, Ns, Np, fc, fs, Pgen):

		N = Ns*Np

		self.genc.set(fc+fs/4, Pgen)

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
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

import vesna.spectrumsensor

class SNEESHTERMeasurementProcess(MeasurementProcess):

	SLUG = "eshter"

	def setup(self):
		self.sensor = vesna.spectrumsensor.SpectrumSensor("/dev/ttyUSB0")
		self.config_list = self.sensor.get_config_list()

	def measure(self, Ns, Np, fc, fs, Pgen):

		if fs == 1e6:
			device_config = self.config_list.get_config(0, 3)
		elif fs == 2e6:
			device_config = self.config_list.get_config(0, 2)
		else:
			assert False

		Np2 = Np + int(self.extra/Ns) + 1

		sample_config = device_config.get_sample_config(fc, Ns)
		assert fs == sample_config.config.bw*2.

		sys.stdout.write("recording %d samples at %f Hz\n" % (Ns*Np2, fc))
		sys.stdout.write("device config: %s\n" % (sample_config.config.name,))

		x = numpy.empty(shape=Ns*Np2)
		sample_config.i = 0

		def cb(sample_config, data):
			assert len(data.data) == Ns

			x[sample_config.i*Ns:(sample_config.i+1)*Ns] = data.data

			sys.stdout.write('.')
			sys.stdout.flush()

			sample_config.i += 1

			if sample_config.i >= Np2:
				return False
			else:
				return True

		self.genc.set(fc, Pgen)
		self.sensor.sample_run(sample_config, cb)
		self.genc.off()

		sys.stdout.write('\n')

		# ok, this expects [self.extra][Ns*Np]
		N = Ns*Np + self.extra
		xa = numpy.empty(shape=N, dtype=numpy.dtype(numpy.complex64))
		xa[:self.extra] = x[:self.extra]
		xa[self.extra:] = x[-Ns*Np:]

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
		os.close(handle)

		xa.tofile(path)

		return path


class SNEISMTVMeasurementProcess(MeasurementProcess):

	SLUG = "sneismtv"

	def setup(self):
		self.sensor = vesna.spectrumsensor.SpectrumSensor("/dev/ttyUSB0")

		config_list = self.sensor.get_config_list()
		self.config = config_list.get_config(0, 0)

	def measure(self, Ns, Np, fc, fs, Pgen):

		N = Ns*Np
		N += self.extra

		sample_config = self.config.get_sample_config(fc, Ns)

		sys.stdout.write("recording %d samples at %f Hz\n" % (N, fc))
		sys.stdout.write("device config: %s\n" % (sample_config.config.name,))

		x = []
		def cb(sample_config, tdata):
			x.extend(tdata.data)

			sys.stdout.write('.')
			sys.stdout.flush()

			if len(x) >= N:
				return False
			else:
				return True

		self.genc.set(fc, Pgen)
		self.sensor.sample_run(sample_config, cb)
		self.genc.off()

		sys.stdout.write('\n')

		if len(x) > N:
			sys.stdout.write("truncating %d samples\n" % (len(x) - N,))
		x = x[:N]

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
		os.close(handle)

		xa = numpy.array(x, dtype=numpy.dtype(numpy.complex64))
		xa.tofile(path)

		return path

class SimulatedMeasurementProcess(MeasurementProcess):

	SLUG = "sim"

	def measure(self, Ns, Np, fc, fs, Pgen):
		N = Ns*Np

		x = self.genc.get(N, fc, fs, Pgen)

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
		os.close(handle)

		xa = numpy.array(x, dtype=numpy.dtype(numpy.complex64))
		xa.tofile(path)

		return path

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

def do_campaign(genc, det, fc, fs, Ns, Pgenl, out_path, measurement_cls):
	Np = 1000

	extra = Ns*5

	try:
		os.mkdir(out_path)
	except OSError:
		pass

	inp = Queue()

	mp = measurement_cls(genc, inp, extra=extra)
	mp.start()

	gp = GammaProcess(mp.out, Ns, (d for d, name in det), extra=extra)
	gp.start()

	for Pgen in Pgenl:
		inp.put({'Ns': Ns,
			'Np': Np,
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
			path = '%s/%s_%s_fs%dmhz_Ns%dks_' % (
					out_path,
					mp.SLUG,
					genc.SLUG, fs/1e6, Ns/1000)
			path += '%s_' % (d.SLUG,)
			if name:
				path += name + "_"

			path += suf

			numpy.savetxt(path, kwargs['gammal'][i,:])

	mp.inp.put(None)
	mp.join()

	gp.inp.put(None)
	gp.join()

def do_sampling_campaign_generator_det(genc, Pgenl, det, fc, fsNs, measurement_cls):

	out_path = "out"

	for fs, Ns in fsNs:
		do_campaign(genc, det, fc=fc, fs=fs, Ns=Ns, Pgenl=Pgenl, out_path=out_path,
				measurement_cls=measurement_cls)

def do_sampling_campaign_generator(genc, Pgenl, fc, fsNs, measurement_cls):

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

	do_sampling_campaign_generator_det(genc, Pgenl, det, fc, fsNs, measurement_cls)

def do_usrp_sampling_campaign_generator(genc, Pgenl, measurement_cls):
	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]

	fc = 864e6

	do_sampling_campaign_generator(genc, Pgenl, fc, fsNs, measurement_cls)

def do_eshter_sampling_campaign_generator(genc, Pgenl, measurement_cls):
	fsNs = [	(1e6, 20000),
			(2e6, 20000),
		]

	fc = 850e6

	do_sampling_campaign_generator(genc, Pgenl, fc, fsNs, measurement_cls)

def ex_usrp_campaign_dc():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]

	fc = 864e6

	det = [	(EnergyDetector(), None) ]

	Pgenl = [ -600 ]

	for dc in xrange(10, 101, 2):

		dcf = dc * 1e-2
		genc = CW(dc=dcf)

		do_sampling_campaign_generator_det(genc, Pgenl, det, fc, fsNs, USRPMeasurementProcess)


def do_sneismtv_campaign_generator(genc, Pgenl):

	fc = 850e6

	measurement_cls = SNEISMTVMeasurementProcess

	out_path = "out"

	det = []
	Ns_list = [ 3676, 1838, 1471 ]

	for Ns in Ns_list:
		det.append((SNEISMTVDetector(N=Ns), "n%d" % (Ns,)))

	do_campaign(genc, det, fc=fc, fs=0, Ns=max(Ns_list), Pgenl=Pgenl, out_path=out_path,
				measurement_cls=measurement_cls)

def ex_sneismtv_campaign_dc():

	Pgenl = [ -600 ]

	for dc in xrange(10, 100+1, 2):

		dcf = dc * 1e-2
		genc = CW(dc=dcf)

		do_sneismtv_campaign_generator(genc, Pgenl)

def ex_sneismtv_campaign_mic():
	genc = IEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)

	do_sneismtv_campaign_generator(genc, Pgenl)

def ex_usrp_campaign_noise():
	genc = Noise()
	Pgenl = [None] + range(-700, -100, 20)

	do_usrp_sampling_campaign_generator(genc, Pgenl, USRPMeasurementProcess)

def ex_usrp_campaign_mic():
	genc = IEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)

	do_usrp_sampling_campaign_generator(genc, Pgenl, USRPMeasurementProcess)

def ex_sim_campaign_mic():
	genc = SimulatedIEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)

	do_usrp_sampling_campaign_generator(genc, Pgenl, SimulatedMeasurementProcess)

def ex_eshter_campaign_noise():
	genc = Noise()
	Pgenl = [None] + range(-700, -100, 20)

	do_eshter_sampling_campaign_generator(genc, Pgenl, SNEESHTERMeasurementProcess)

def ex_eshter_campaign_mic():
	genc = IEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)

	do_eshter_sampling_campaign_generator(genc, Pgenl, SNEESHTERMeasurementProcess)


def main():

	if len(sys.argv) == 2:
		cmd = sys.argv[1]
		globals()[cmd]()
	else:
		print "USAGE: %s <func>" % (sys.argv[0],)
		print
		print "available functions:"
		funcs = []
		for name, val in globals().iteritems():
			if not callable(val):
				continue
			if name.startswith("ex_"):
				funcs.append(name)

		funcs.sort()

		for name in funcs:
			print "   ", name

main()

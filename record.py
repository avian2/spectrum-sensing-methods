import subprocess
from multiprocessing import Process, Queue
import os
import tempfile
import numpy as np
from sensing.siggen import *
import sys
import time

TEMPDIR="/tmp"

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

		x = np.empty(shape=Ns*Np2)
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
		xa = np.empty(shape=N, dtype=np.dtype(np.complex64))
		xa[:self.extra] = x[:self.extra]
		xa[self.extra:] = x[-Ns*Np:]

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
		os.close(handle)

		xa.tofile(path)

		return path


class SNEISMTVMeasurementProcess(MeasurementProcess):

	SLUG = "sneismtv"

	WARMUP_MIN = 1

	def setup(self):
		self.sensor = vesna.spectrumsensor.SpectrumSensor("/dev/ttyUSB0")

		config_list = self.sensor.get_config_list()
		self.config = config_list.get_config(0, 0)

		self.warmup()

	def warmup(self):
		sample_config = self.config.get_sample_config(850e6, 1000)

		start_time = time.time()
		stop_time = start_time + self.WARMUP_MIN*60.

		def cb(sample_config, data):
			return time.time() < stop_time

		sys.stdout.write("begin warmup\n")
		self.sensor.sample_run(sample_config, cb)
		sys.stdout.write("end warmup\n")

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

		xa = np.array(x, dtype=np.dtype(np.complex64))
		xa.tofile(path)

		return path

class SimulatedMeasurementProcess(MeasurementProcess):

	SLUG = "sim"

	def measure(self, Ns, Np, fc, fs, Pgen):
		N = Ns*Np

		x = self.genc.get(N, fc, fs, Pgen)

		handle, path = tempfile.mkstemp(dir=TEMPDIR)
		os.close(handle)

		xa = np.array(x, dtype=np.dtype(np.complex64))
		xa.tofile(path)

		return path

def do_campaign(genc, fc, fs, Ns, Pgenl, out_path, measurement_cls):
	Np = 1000

	extra = Ns*5

	try:
		os.mkdir(out_path)
	except OSError:
		pass

	inp = Queue()

	mp = measurement_cls(genc, inp, extra=extra)
	mp.start()

	for Pgen in Pgenl:
		inp.put({'Ns': Ns,
			'Np': Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen/10. if Pgen is not None else None})

	for Pgen in Pgenl:
		kwargs = mp.out.get()
		if kwargs['Pgen'] is None:
			suf = 'off.npy'
		else:
			m = '%.1f' % (kwargs['Pgen'],)
			m = m.replace('-','m')
			m = m.replace('.','_')

			suf = '%sdbm.npy' % (m,)

		path = '%s/%s_%s_fs%dmhz_Ns%dks_' % (
				out_path,
				mp.SLUG,
				genc.SLUG, fs/1e6, Ns/1000)
		path += suf

		x = np.fromfile(kwargs['path'],
					dtype=np.dtype(np.complex64))

		# skip leading samples - they are typically not useful
		# because they happen while ADC is settling in the receiver
		# and other transition effects.
		x = x[mp.extra:]

		np.save(path, x.real)

		os.unlink(kwargs['path'])

	mp.inp.put(None)
	mp.join()

def do_sampling_campaign_generator_det(genc, Pgenl, fc, fsNs, measurement_cls):

	out_path = "out"

	for fs, Ns in fsNs:
		do_campaign(genc, fc=fc, fs=fs, Ns=Ns, Pgenl=Pgenl, out_path=out_path,
				measurement_cls=measurement_cls)

def do_sampling_campaign_generator(genc, Pgenl, fc, fsNs, measurement_cls):

	do_sampling_campaign_generator_det(genc, Pgenl, fc, fsNs, measurement_cls)

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

	Pgenl = [ -600 ]

	for dc in xrange(10, 101, 2):

		dcf = dc * 1e-2
		genc = CW(dc=dcf)

		do_sampling_campaign_generator_det(genc, Pgenl, fc, fsNs, USRPMeasurementProcess)


def do_sneismtv_campaign_generator(genc, Pgenl):

	fc = 850e6

	measurement_cls = SNEISMTVMeasurementProcess

	out_path = "out"

	Ns = 3676

	do_campaign(genc, fc=fc, fs=0, Ns=Ns, Pgenl=Pgenl, out_path=out_path,
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

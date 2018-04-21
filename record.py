import subprocess
from multiprocessing import Process, Queue
import os
import tempfile
import numpy as np
from sensing.siggen import *
import sys
import time
import threading

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

	def measure(self, Ns, Np, fc, fs, Pgen, fcgen):

		if fcgen is None:
			fcgen = fc + fs/4.

		N = Ns*Np

		self.genc.set(fcgen, Pgen)

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

sneismtv_do_warmup = True

class AsyncSpectrumSensor:
	WARMUP_MIN = 5

	def __init__(self, device):
		self.sensor = vesna.spectrumsensor.SpectrumSensor("/dev/ttyUSB0")
		self.want_stop = False

		self.worker = None

		self.sample_config = None

		self.work_cv = threading.Condition()

		self.user_cb = None

	def get_config_list(self):
		return self.sensor.get_config_list()

	def start(self, sample_config):
		if self.worker is None:
			self.sample_config = sample_config
			self.worker = threading.Thread(	target=self.sensor.sample_run,
							args=(sample_config, self.cb))

			sys.stdout.write("begin warmup\n")

			self.worker.start()
			time.sleep(self.WARMUP_MIN*60)

			sys.stdout.write("end warmup\n")
		else:
			assert self.sample_config.nsamples == sample_config.nsamples
			assert self.sample_config.config == sample_config.config

	def cb(self, sample_config, data):
		self.work_cv.acquire()
		if self.user_cb is not None:
			r = self.user_cb(sample_config, data)
			if not r:
				self.user_cb = None
				self.work_cv.notify()
			else:
				self.work_cv.release()
				return True

		self.work_cv.release()
		return not self.want_stop

	def record(self, cb):
		self.work_cv.acquire()
		self.user_cb = cb
		self.work_cv.wait()
		self.work_cv.release()

	def stop(self):
		if self.worker is not None:
			self.want_stop = True
			self.worker.join()

			self.worker = None
			self.sample_config = None

class SNEESHTERCovarianceMeasurementProcess(MeasurementProcess):

	SLUG = "eshtercov"

	def setup(self):
		self.sensor = AsyncSpectrumSensor("/dev/ttyUSB0")
		self.config_list = self.sensor.get_config_list()

	def measure(self, Ns, Np, fc, fs, Pgen, fcgen):

		if fcgen is None:
			fcgen = fc

		if fs == 1e6:
			device_config = self.config_list.get_config(0, 3)
		elif fs == 2e6:
			device_config = self.config_list.get_config(0, 2)
		else:
			assert False

		Np2 = Np + int(self.extra/Ns) + 1

		sample_config = device_config.get_sample_config(fc, Ns)
		assert fs == sample_config.config.bw*2.

		sys.stdout.write("recording %d*%d samples at %f Hz\n" % (Ns, Np2, fc))
		sys.stdout.write("device config: %s\n" % (sample_config.config.name,))

		self.sensor.start(sample_config)

		x = np.empty(shape=Ns*Np2)
		i = [0]

		def cb(sample_config, data):
			assert len(data.data) == Ns

			x[i[0]*Ns:(i[0]+1)*Ns] = data.data

			sys.stdout.write('.')
			sys.stdout.flush()

			i[0] += 1

			if i[0] >= Np2:
				return False
			else:
				return True

		self.genc.set(fcgen, Pgen)
		self.sensor.record(cb)
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

	def run(self):
		MeasurementProcess.run(self)
		self.sensor.stop()

class SNEISMTVMeasurementProcess(MeasurementProcess):

	SLUG = "sneismtv"

	WARMUP_MIN = 30

	def setup(self):
		self.sensor = vesna.spectrumsensor.SpectrumSensor("/dev/ttyUSB0")

		config_list = self.sensor.get_config_list()
		self.config = config_list.get_config(0, 0)

		global sneismtv_do_warmup

		if sneismtv_do_warmup:
			self.warmup()
			sneismtv_do_warmup = False
		else:
			print("skipping warmup")

	def warmup(self):
		sample_config = self.config.get_sample_config(850e6, 4000)

		start_time = time.time()
		stop_time = start_time + self.WARMUP_MIN*60.

		i = [0]
		def cb(sample_config, data):
			if (i[0] % 100) == 0:
				print("   %.0f min of warmup left. Sample mean: %.0f" % (
					(stop_time - time.time())/60.,
					np.mean(data.data)))

			i[0] += 1
			return time.time() < stop_time

		sys.stdout.write("begin warmup\n")
		self.sensor.sample_run(sample_config, cb)
		sys.stdout.write("end warmup\n")

	def measure(self, Ns, Np, fc, fs, Pgen, fcgen=None):

		if fcgen is None:
			fcgen = fc

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

		self.genc.set(fcgen, Pgen)
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

def do_campaign(genc, fc, fs, Ns, Pfcgenl, out_path, measurement_cls):
	Np = 1000

	extra = Ns*5

	try:
		os.mkdir(out_path)
	except OSError:
		pass

	inp = Queue()

	mp = measurement_cls(genc, inp, extra=extra)
	mp.start()

	for Pgen, fcgen in Pfcgenl:
		inp.put({'Ns': Ns,
			'Np': Np,
			'fc': fc,
			'fs': fs,
			'Pgen': Pgen/10. if Pgen is not None else None,
			'fcgen': fcgen})

	for Pgen, fcgen in Pfcgenl:
		kwargs = mp.out.get()
		if kwargs['Pgen'] is None:
			suf = 'off.npy'
		else:
			m = '%.1f' % (kwargs['Pgen'],)
			m = m.replace('-','m')
			m = m.replace('.','_')

			suf = '%sdbm.npy' % (m,)

		if kwargs['fcgen'] is None:
			suf2 = ''
		else:
			suf2 = 'fcgen%dkhz_' % (kwargs['fcgen']/1e3,)

		path = '%s/%s_%s_fs%dmhz_Ns%dks_' % (
				out_path,
				mp.SLUG,
				genc.SLUG, fs/1e6, Ns/1000)
		path += suf2 + suf

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

def do_sampling_campaign_generator(genc, Pfcgenl, fc, fsNs, measurement_cls):

	out_path = "samples-usrp"

	for fs, Ns in fsNs:
		do_campaign(genc, fc=fc, fs=fs, Ns=Ns, Pfcgenl=Pfcgenl, out_path=out_path,
				measurement_cls=measurement_cls)

def do_usrp_sampling_campaign_generator(genc, Pfcgenl, measurement_cls):
	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]

	fc = 864e6

	do_sampling_campaign_generator(genc, Pfcgenl, fc, fsNs, measurement_cls)

def do_eshter_sampling_campaign_generator(genc, Pfcgenl, measurement_cls):
	fsNs = [	(1e6, 20000),
			(2e6, 20000),
		]

	fc = 850e6

	do_sampling_campaign_generator(genc, Pfcgenl, fc, fsNs, measurement_cls)

def do_eshtercov_campaign_generator(genc, Pfcgenl, measurement_cls):

	out_path = "samples-eshtercov"

	do_campaign(
		genc,
		fc=700e6,
		fs=2e6,
		Ns=20,
		Pfcgenl=Pfcgenl,
		out_path="samples-eshtercov",
		measurement_cls=measurement_cls)

def ex_usrp_campaign_dc():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]

	fc = 864e6

	Pfcgenl = [ (-600, None) ]

	for dc in xrange(10, 101, 2):

		dcf = dc * 1e-2
		genc = CW(dc=dcf)

		do_sampling_campaign_generator(genc, Pfcgenl, fc, fsNs, USRPMeasurementProcess)


def do_sneismtv_campaign_generator(genc, Pfcgenl):

	fc = 850e6

	measurement_cls = SNEISMTVMeasurementProcess

	out_path = "samples-sneismtv"

	Ns = 3676

	do_campaign(genc, fc=fc, fs=0, Ns=Ns, Pfcgenl=Pfcgenl, out_path=out_path,
				measurement_cls=measurement_cls)

def ex_sneismtv_campaign_dc():

	Pfcgenl = [ (-600, None) ]

	for dc in xrange(10, 100+1, 2):

		dcf = dc * 1e-2
		genc = CW(dc=dcf)

		do_sneismtv_campaign_generator(genc, Pfcgenl)

def ex_sneismtv_campaign_mic_bpsk():
	gencl = [
			IEEE802514BPSK,
			#IEEEMicSilent,
			IEEEMicSoftSpeaker,
			#IEEEMicLoudSpeaker,
	]

	Pgenl = [None] + range(-1000, -700, 10)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	for genc in gencl:
		genci = genc()
		do_sneismtv_campaign_generator(genci, Pfcgenl)

def ex_usrp_campaign_noise():
	genc = Noise()
	Pgenl = [None] + range(-700, -100, 20)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	do_usrp_sampling_campaign_generator(genc, Pfcgenl, USRPMeasurementProcess)

def ex_usrp_campaign_mic_bpsk():
	gencl = [
			IEEEMicSilent,
			IEEEMicSoftSpeaker,
			IEEEMicLoudSpeaker,
			IEEE802514BPSK,
	]

	Pgenl = [None] + range(-1000, -700, 10)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	for genc in gencl:
		genci = genc()
		do_usrp_sampling_campaign_generator(genci, Pfcgenl, USRPMeasurementProcess)

def ex_sim_campaign_mic():
	genc = SimulatedIEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	do_usrp_sampling_campaign_generator(genc, Pfcgenl, SimulatedMeasurementProcess)

def ex_eshter_campaign_noise():
	genc = Noise()
	Pgenl = [None] + range(-700, -100, 20)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	do_eshter_sampling_campaign_generator(genc, Pfcgenl, SNEESHTERMeasurementProcess)

def ex_eshter_campaign_mic():
	genc = IEEEMicSoftSpeaker()
	Pgenl = [None] + range(-1000, -700, 10)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	do_eshter_sampling_campaign_generator(genc, Pfcgenl, SNEESHTERMeasurementProcess)

def ex_eshtercov_campaign_unb():
	genc = UNB()
	Pgenl = [None] + range(-1000, -740, 10)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	do_eshtercov_campaign_generator(genc, Pfcgenl, SNEESHTERCovarianceMeasurementProcess)

def ex_eshtercov_campaign_unb_freq_sweep():
	genc = UNB()

	Pfcgenl = [ (None, 700e6) ]
	Pfcgenl += [ (-900, 700e6 + foff) for foff in np.arange(-1.00e6, .61e6, .05e6) ]

	do_eshtercov_campaign_generator(genc, Pfcgenl, SNEESHTERCovarianceMeasurementProcess)


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

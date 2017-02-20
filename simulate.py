import subprocess
import datetime
from multiprocessing import Pool, Process, Queue
import os
import tempfile
import numpy as np
from sensing.methods import *
from sensing.signals import *
import sys
import progressbar
import itertools
import traceback
from optparse import OptionParser

OUTPATH=datetime.datetime.now().strftime("simout-%Y%m%d-%H%M%S")

Np = 1000

def get_path(genc, func, funcname, Ns, fs, Pgen, fcgen):
	mp_slug = "sim"

	if Pgen is None:
		suf = 'off.dat'
	else:
		m = '%.1f' % (Pgen,)
		m = m.replace('-','m')
		m = m.replace('.','_')

		suf = '%sdbm.dat' % (m,)

	if fcgen is None:
		suf2 = ''
	else:
		suf2 = 'fcgen%dkhz_' % (fcgen/1e3,)

	path = '%s/dat/%s_%s_fs%dmhz_Ns%dks_' % (
				OUTPATH,
				mp_slug,
				genc.SLUG, fs/1e6, Ns/1000)
	path += '%s_' % (func.SLUG,)
	if funcname:
		path += funcname + "_"

	path += suf2 + suf

	return path

def run_simulation(genc, det, Np, Ns, fc, fs, Pgen, fcgen):

	np.random.seed()

	N = Np*Ns

	x = genc.get(N, fc, fs, Pgen, fcgen)
	assert len(x) == N

	jl = range(0, N, Ns)
	assert len(jl) == Np

	gammal = np.empty(shape=Np)
	for func, funcname in det:

		for i, j in enumerate(jl):
			x0 = x[j:j+Ns]
			gammal[i] = func(x0)

		path = get_path(genc, func, funcname, Ns, fs, Pgen, fcgen)

		assert not os.path.exists(path), ("Not overwriting %r" % (path,))
		np.savetxt(path, gammal)

def run_simulation_(kwargs):
	try:
		return run_simulation(**kwargs)
	except Exception:
		traceback.print_exc()
		raise

def make_campaign_det_gencl(fc, det, fsNsl, gencl, Pfcgenl):
	task_list = []
	for Pgen, fcgen in Pfcgenl:
		for fs, Ns in fsNsl:
			for genc in gencl:
				task_list.append({
					'genc': genc,
					'det': det,
					'Np': Np,
					'Ns': Ns,
					'fc': fc,
					'fs': fs,
					'Pgen': Pgen,
					'fcgen': fcgen,
				})

	return task_list

def make_sampling_campaign_gencl(fsNsl, gencl, Pgenl):

	fc = 864e6

	det = [	(EnergyDetector(), None) ]

	cls = [	CAVDetector,
		CFNDetector,
		MACDetector,
		MMEDetector,
		EMEDetector,
		AGMDetector,
		METDetector ]

	#for L in xrange(5, 25, 5):
	#	for c in cls:
	#		det.append((c(L=L), "l%d" % (L,)))

	for scfNp in [64, 128]:
		det += [ (SCFDetector(Np=scfNp, L=scfNp/4), "Np%d" % (scfNp,)) ]

	return make_campaign_det_gencl(fc, det, fsNsl, gencl, Pgenl)

def make_sampling_campaign_gencl_compdet(fsNsl, gencl, Pfcgenl):

	fc = 864e6

	# We can make just one instance for all detectors that do not use
	# noise-compensation. These are stored om "det".
	det = [	(EnergyDetector(), None) ]

	cls = [	CAVDetector,
		CFNDetector,
		MACDetector,
		MMEDetector,
		EMEDetector,
		AGMDetector,
		METDetector,
	]

	Ll = range(5, 25, 5)
	for L in Ll:
		for c in cls:
			det.append((c(L=L), "l%d" % (L,)))

	# Compensated detectors need to be instantiated with a sample of the
	# noise. This sample varies with fs, hence we need to make a separate
	# instance for each of the fs values we use.
	compcls = [	CompCAVDetector,
			CompCFNDetector,
			CompMACDetector,
			CompMMEDetector,
			CompEMEDetector,
			CompAGMDetector,
			CompMETDetector,
	]

	task_list = []

	for fs, Ns in fsNsl:
		# We assume fcgen is not used in this test.
		for Pgen, fcgen in Pfcgenl:
			assert fcgen is None
		fcgen = None

		# We assume only one generator function is used. This is
		# typically true on runs that work on measured data (not
		# simulations)
		assert len(gencl) == 1
		genc = gencl[0]

		# Get a sample of noise for this particular fs.
		N = Np * Ns
		xn = genc.get(N, fc, fs, None, fcgen)

		# Instantiate detectors.
		compdet = list(det)
		for L in Ll:
			for c in compcls:
				compdet.append((c(L=L, xn=xn), "l%d" % (L,)))

		# Create a tasklist using this set of detectors. Accumulate all
		# tasks in a single list to be returned later.
		task_list += make_campaign_det_gencl(fc, compdet, [(fs, Ns)], gencl, Pfcgenl)

	return task_list

def make_sneismtv_campaign_gencl(fsNsl, gencl, Pgenl):

	fc = 850e6

	Ns_list = [ 3676, 1838, 1471 ]

	det = []
	for Ns in Ns_list:
		det.append((SNEISMTVDetector(N=Ns), "n%d" % (Ns,)))

	return make_campaign_det_gencl(fc, det, fsNsl, gencl, Pgenl)

def ex_sim_spurious_campaign_mic():

	fs = 2e6

	fsNs = [ (fs, 25000) ]
	Pgenl = [None] + range(-140, -100, 1)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	fnl = [
#		3.*fs/8.,
#		3.*fs/8.+1e3,
#		fs/4.,
#		fs/4.+1e3,
#		fs/8.,
#		fs/8.+1e3,
#		fs/32.,
#		fs/128.,
		fs * .5 / 2. / np.pi,
	]

	Pngaussian = -110.

	gencl = []
	gencl.append(	AddGaussianNoise(
				SimulatedIEEEMicSoftSpeaker(),
				Pn=Pngaussian)
			)

	Pnl  = range(-130, -100, 2)
	for Pn in Pnl:
		for fn in fnl:
			gencl.append(	AddGaussianNoise(
						AddSpuriousCosine(
							SimulatedIEEEMicSoftSpeaker(),
							fn, Pn=Pn),
						Pn=Pngaussian)
					)

	fc = 864e6

	# ((.45 > x) | (x > .55))
	par = [(0, 0.82756856571986481),
		 (1, -0.15831028724220766),
		 (2, 0.087458757436627538),
		 (3, 0.29820803043768468),
		 (4, 0.19874271896672804),
		 (5, -0.070977333256577443),
		 (6, -0.21485390469941659),
		 (7, -0.20513238974090675),
		 (8, 0.074080499429488814),
		 (9, 0.20674192977716482),
		 (10, 0.1943669121630652),
		 (12, -0.23434520299785008),
		 (13, -0.20237450911860522),
		 (14, -0.080703024390077149),
		 (15, 0.14138738927776159),
		 (16, 0.2068086029136337),
		 (19, -0.15027595786459855),
		 (21, 0.076397717850189617),
		 (22, 0.11485286042247005),
		 (23, 0.060500469017921096),
		 (24, -0.086995844709030004),
		 (25, -0.073499217626501245),
		 (26, -0.08610123749514953),
		 (44, 0.082844411747287433),
		 (48, -0.090986756442279534)]

	par2 = [(0, 1.)]
	L = 25
	for l in xrange(1, L):
		par2.append((l, 2.*(L-l)/L))

	det = [	(EnergyDetector(), None),
		(FSCBD(par), None),
		(FSCBD(par2), 'cav'),
	]

	cls = [	CAVDetector,
		MACDetector ]

	for c in cls:
		L = 25
		det.append((c(L=L), "l%d" % (L,)))

	return make_campaign_det_gencl(fc, det, fsNs, gencl, Pfcgenl)

def ex_sim_gaussian_noise_campaign_mic():

	fsNs = [ (2e6, 25000) ]
	Pgenl = [None] + range(-140, -100, 1)

	gencl = []
	gencl.append(SimulatedIEEEMicSoftSpeaker())

	Pnl  = range(-130, -100, 2)
	for Pn in Pnl:
		gencl.append(AddGaussianNoise(SimulatedIEEEMicSoftSpeaker(), Pn=Pn))

	return make_sampling_campaign_gencl(fsNs, gencl, Pgenl)


def ex_sim_oversample_campaign_mic():

	fsNs = [ (2e6, 25000) ]
	Pgenl = [None] + range(-140, -100, 1)

	#kl = range(1, 9)
	kl = [1]

	gencl = []
	for k in kl:
		gencl.append(Divide(Oversample(SimulatedIEEEMicSoftSpeaker(), k=k), Nb=Ns*4))

	return make_sampling_campaign_gencl(fsNs, gencl, Pgenl)

def ex_sim_campaign_mic():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]
	Pgenl = [None] + range(-140, -100, 1)

	gencl = []
	gencl.append(AddGaussianNoise(SimulatedIEEEMicSoftSpeaker(), Pn=-100))

	return make_sampling_campaign_gencl(fsNs, gencl, Pgenl)

class Serial(object):
	def __init__(self, signal, n):
		self.signal = signal
		self.SLUG = "%s_%04d" % (signal.SLUG, n)

	def get(self, *args, **kwargs):
		return self.signal.get(*args, **kwargs)

# For checking confidence intervals of the calculated Pinmin
def ex_sim_campaign_mic_conf_int():
	fsNsl = [	(1e6, 25000) ]

	# power sweep - for determining the Pin at which to run monte carlo
	#Pgenl = [None] + range(-140, -100, 1)
	Pgenl = [None, -116]

	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	gencl = []
	genc = AddGaussianNoise(SimulatedIEEEMicSoftSpeaker(), Pn=-100)
	for n in range(100):
		gencl.append(Serial(genc, n))

	fc = 864e6
	det = [	(EnergyDetector(), None) ]

	return make_campaign_det_gencl(fc, det, fsNsl, gencl, Pfcgenl)

def ex_calc_campaign_mic():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]
	Pgenl = [None] + range(-100, -70, 1)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	gencl = [ LoadMeasurement("samples-usrp_campaign_mic/usrp_micsoft_fs%(fs)smhz_Ns%(Ns)sks_%(Pgen)s.npy", Np=Np) ]

	return make_sampling_campaign_gencl_compdet(fsNs, gencl, Pfcgenl)

def ex_calc_sneismtv_campaign_mic():

	fsNs = [	(0, 3676),
		]

	Pgenl = [None] + range(-100, -70, 1)

	gencl = [ LoadMeasurement("samples-sneismtv_campaign_mic/sneismtv_micsoft_fs%(fs)smhz_Ns%(Ns)sks_%(Pgen)s.npy", Np=Np) ]

	return make_sneismtv_campaign_gencl(fsNs, gencl, Pgenl)

def ex_sim_campaign_noise():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]
	Pgenl = range(-100, -60, 1)


	gencl = []
	gencl.append(SimulatedNoise())

	return make_sampling_campaign_gencl(fsNs, gencl, Pgenl)

def ex_calc_campaign_noise():

	fsNs = [	(1e6, 25000),
			(2e6, 25000),
			(10e6, 100000),
		]
	Pgenl = [None] + range(-70, -10, 2)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	gencl = [ LoadMeasurement("samples-usrp_campaign_noise/usrp_noise_fs%(fs)smhz_Ns%(Ns)sks_%(Pgen)s.npy", Np=Np) ]

	return make_sampling_campaign_gencl_compdet(fsNs, gencl, Pfcgenl)

def ex_calc_sneeshtercov_campaign_unb():

	fsNs = [	(2e6, 20) ]

	fc = 700e6

	det = [	(SNEESHTEREnergyDetector(), None) ]

	cls = [	SNEESHTERCAVDetector,
		SNEESHTERMACDetector ]

	for L in xrange(5, 25, 5):
		for c in cls:
			det.append((c(L=L), "l%d" % (L,)))

	gencl = [ LoadMeasurement("samples-eshtercov-powersweep/eshtercov_unb_fs%(fs)smhz_Ns%(Ns)sks_%(Pgen)s.npy", Np=Np) ]

	Pgenl = [None] + range(-100, -77, 1)
	Pfcgenl = [ (Pgen, None) for Pgen in Pgenl ]

	return make_campaign_det_gencl(fc, det, fsNs, gencl, Pfcgenl)

def ex_calc_sneeshtercov_campaign_unb_freq_sweep():

	fsNs = [	(2e6, 20) ]

	fc = 700e6

	det = [	(SNEESHTERMACDetector(L=5), 'l5'),
		(SNEESHTERCAVDetector(L=5), 'l5'),
		(SNEESHTERCAVDetector(L=10), 'l10'),
		(SNEESHTERCAVDetector(L=15), 'l15'),
		(SNEESHTERCAVDetector(L=20), 'l20'),
		(SNEESHTEREnergyDetector(), None) ]

	gencl = [ LoadMeasurement("samples-eshtercov-freqsweep/eshtercov_unb_fs%(fs)smhz_Ns%(Ns)sks_fcgen%(fcgen)s_%(Pgen)s.npy", Np=Np) ]

	Pfcgenl = [ (None, 700e6) ]
	Pfcgenl += [ (-90, 700e6 + foff) for foff in np.arange(-1.00e6, .61e6, .05e6) ]

	return make_campaign_det_gencl(fc, det, fsNs, gencl, Pfcgenl)


def cmdline():
	parser = OptionParser()
	parser.add_option("-f", dest="func", metavar="FUNCTION",
			help="function to run")
	parser.add_option("-o", dest="outpath", metavar="PATH",
			help="output directory")
	parser.add_option("-p", dest="nproc", metavar="NPROC", type="int", default=4,
			help="number of processes to run")
	parser.add_option("-s", dest="slice", metavar="SLICE", default="0:1",
			help="slice of tasklist to run (e.g. 1:10 for slice 1 of 10)")

	(options, args) = parser.parse_args()

	return options

def make_slice(task_list, options):
	i, n = map(int, options.slice.split(":"))

	#print "slice %d of %d" % (i, n)

	m = len(task_list)

	#print "task list len", m

	slice_size = m/n
	if m % n > 0:
		slice_size += 1

	#print "slice size", slice_size

	start = slice_size*i

	#print "from %d to %d" % (start, start+slice_size)

	assert(slice_size*n >= m)

	return task_list[start:start+slice_size]

def run(task_list, options):
	pool = Pool(processes=options.nproc)

	task_list = make_slice(task_list, options)
	if not task_list:
		return

	widgets = [ progressbar.Percentage(), ' ', progressbar.Bar(), ' ', progressbar.ETA() ] 
	pbar = progressbar.ProgressBar(widgets=widgets, maxval=len(task_list))
	pbar.start()

	for i, v in enumerate(pool.imap_unordered(run_simulation_, task_list)):
	#for i, v in enumerate(itertools.imap(run_simulation_, task_list)):
		pbar.update(i)

	pbar.finish()
	print

	#run_simulation_(task_list[0])

def main():
	global OUTPATH

	options = cmdline()

	if options.func is not None:

		if options.outpath:
			OUTPATH = options.outpath

		try:
			os.mkdir(OUTPATH)
			os.mkdir(OUTPATH + "/dat")
		except OSError:
			pass

		f = open(OUTPATH + "/args", "w")
		f.write(' '.join(sys.argv) + '\n')
		f.close()

		task_list = globals()[options.func]()
		run(task_list, options)

		open(OUTPATH + "/done", "w")
	else:
		print "Specify function to run with -f"
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

if __name__ == "__main__":
	main()

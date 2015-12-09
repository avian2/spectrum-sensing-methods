import subprocess
import datetime
from multiprocessing import Pool, Process, Queue
import os
import tempfile
import numpy
from sensing.methods import *
from sensing.signals import *
import sys
import progressbar
import itertools
import traceback
from optparse import OptionParser

OUTPATH=datetime.datetime.now().strftime("simout-%Y%m%d-%H%M%S")

def get_path(genc, func, funcname, Ns, fs, Pgen):
	mp_slug = "sim"

	if Pgen is None:
		suf = 'off.dat'
	else:
		m = '%.1f' % (Pgen,)
		m = m.replace('-','m')
		m = m.replace('.','_')

		suf = '%sdbm.dat' % (m,)

	path = '%s/dat/%s_%s_fs%dmhz_Ns%dks_' % (
				OUTPATH,
				mp_slug,
				genc.SLUG, fs/1e6, Ns/1000)
	path += '%s_' % (func.SLUG,)
	if funcname:
		path += funcname + "_"

	path += suf

	return path

def run_simulation(genc, det, Np, Ns, fc, fs, Pgen):

	N = Np*Ns

	x = genc.get(N, fc, fs, Pgen)
	assert len(x) == N

	jl = range(0, N, Ns)
	assert len(jl) == Np

	gammal = numpy.empty(shape=Np)
	for func, funcname in det:

		for i, j in enumerate(jl):
			x0 = x[j:j+Ns]
			gammal[i] = func(x0)

		path = get_path(genc, func, funcname, Ns, fs, Pgen)
		numpy.savetxt(path, gammal)

def run_simulation_(kwargs):
	try:
		return run_simulation(**kwargs)
	except Exception:
		traceback.print_exc()
		raise

def do_sim_campaign_gencl(fs, Ns, gencl, Pgenl):

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

	for Np in [128,]:
		det += [ (CAMDetector(Np=Np, L=Np/4), "Np%d" % (Np,)) ]

	task_list = []
	for Pgen in Pgenl:
		for genc in gencl:
			task_list.append({
				'genc': genc,
				'det': det,
				'Np': 200,
				'Ns': Ns,
				'fc': fc,
				'fs': fs,
				'Pgen': Pgen
			})

	pool = Pool(processes=5)


	widgets = [ progressbar.Percentage(), ' ', progressbar.Bar(), ' ', progressbar.ETA() ] 
	pbar = progressbar.ProgressBar(widgets=widgets, maxval=len(task_list)-1)
	pbar.start()

	for i, v in enumerate(pool.imap_unordered(run_simulation_, task_list)):
	#for i, v in enumerate(itertools.imap(run_simulation_, task_list)):
		pbar.update(i)

	pbar.finish()
	print

	#run_simulation_(task_list[0])

def ex_sim_spurious_campaign_mic():

	Ns = 25000
	fs = 2e6
	Pgenl = [None] + range(-140, -100, 1)

	fnl = [
		3.*fs/8.,
		3.*fs/8.+1e3,
#		fs/4.,
#		fs/4.+1e3,
#		fs/8.,
#		fs/8.+1e3,
#		fs/32.,
#		fs/128.,
	]

	gencl = []
#	gencl.append(SimulatedIEEEMicSoftSpeaker())

	Pnl  = range(-130, -100, 2)
	for Pn in Pnl:
		for fn in fnl:
			gencl.append(AddSpuriousCosine(SimulatedIEEEMicSoftSpeaker(), fn, Pn=Pn))

	do_sim_campaign_gencl(fs, Ns, gencl, Pgenl)

def ex_sim_gaussian_noise_campaign_mic():

	Ns = 25000
	fs = 2e6
	Pgenl = [None] + range(-140, -100, 1)

	gencl = []
	gencl.append(SimulatedIEEEMicSoftSpeaker())

	Pnl  = range(-130, -100, 2)
	for Pn in Pnl:
		gencl.append(AddGaussianNoise(SimulatedIEEEMicSoftSpeaker(), Pn=Pn))

	do_sim_campaign_gencl(fs, Ns, gencl, Pgenl)


def ex_sim_oversample_campaign_mic():

	Ns = 25000
	fs = 2e6
	Pgenl = [None] + range(-140, -100, 1)

	#kl = range(1, 9)
	kl = [1]

	gencl = []
	for k in kl:
		gencl.append(Divide(Oversample(SimulatedIEEEMicSoftSpeaker(), k=k), Nb=Ns*4))

	do_sim_campaign_gencl(fs, Ns, gencl, Pgenl)

def ex_sim_campaign_mic():

	Ns = 25000
	fs = 2e6
	Pgenl = [None] + range(-140, -100, 1)

	gencl = []
	gencl.append(AddGaussianNoise(SimulatedIEEEMicSoftSpeaker(), Pn=-100))

	do_sim_campaign_gencl(fs, Ns, gencl, Pgenl)

def ex_sim_campaign_noise():

	Ns = 25000
	fs = 2e6
	Pgenl = range(-100, -60, 1)


	gencl = []
	gencl.append(SimulatedNoise())

	do_sim_campaign_gencl(fs, Ns, gencl, Pgenl)

def cmdline():
	parser = OptionParser()
	parser.add_option("-f", dest="func", metavar="FUNCTION",
			help="function to run")

	(options, args) = parser.parse_args()

	return options

def main():
	options = cmdline()

	if options.func is not None:
		try:
			os.mkdir(OUTPATH)
			os.mkdir(OUTPATH + "/dat")
		except OSError:
			pass

		f = open(OUTPATH + "/args", "w")
		f.write(' '.join(sys.argv) + '\n')
		f.close()

		globals()[options.func]()

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

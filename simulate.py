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

TEMPDIR="/tmp"

def get_path(genc, func, funcname, Ns, fs, Pgen):
	out_path = "out"
	mp_slug = "sim"

	if Pgen is None:
		suf = 'off.dat'
	else:
		m = '%.1f' % (Pgen,)
		m = m.replace('-','m')
		m = m.replace('.','_')

		suf = '%sdbm.dat' % (m,)

	path = '%s/%s_%s_fs%dmhz_Ns%dks_' % (
				out_path,
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
	return run_simulation(**kwargs)

def do_sim_campaign_gencl(fs, gencl):

	Pgenl = [None] + range(-100, -80, 1)

	fc = 864e6

	det = [	(EnergyDetector(), None) ]

	cls = [	CAVDetector,
		MACDetector ]

	for L in xrange(5, 25, 5):
		for c in cls:
			det.append((c(L=L), "l%d" % (L,)))

	task_list = []
	for Pgen in Pgenl:
		for genc in gencl:
			task_list.append({
				'genc': genc,
				'det': det,
				'Np': 1000,
				'Ns': 25000,
				'fc': fc,
				'fs': fs,
				'Pgen': Pgen
			})

	pool = Pool(processes=4)


	widgets = [ progressbar.Percentage(), ' ', progressbar.Bar(), ' ', progressbar.ETA() ] 
	pbar = progressbar.ProgressBar(widgets=widgets, maxval=len(task_list)-1)
	pbar.start()

	for i, v in enumerate(pool.imap_unordered(run_simulation_, task_list)):
		pbar.update(i)

	pbar.finish()
	print

	#run_simulation_(task_list[0])

def ex_sim_noise_campaign_mic():

	fs = 2e6

	fnl = [
		fs/4.,
		fs/8.,
		fs/32.,
		fs/128.,
	]

	gencl = []
	gencl.append(SimulatedIEEEMicSoftSpeaker())

	Pnl  = range(-130, -100, 2)
	for Pn in Pnl:
		for fn in fnl:
			gencl.append(Spurious(SimulatedIEEEMicSoftSpeaker(), fn, Pn=Pn))

	do_sim_campaign_gencl(fs, gencl)

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

if __name__ == "__main__":
	main()
